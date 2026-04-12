"""BDD-style tests for TabCharge model."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.models import TabCharge
from tests.billing.factories import BillingSettingsFactory, TabChargeFactory, TabEntryFactory, TabFactory

pytestmark = pytest.mark.django_db


def describe_TabCharge():
    def it_has_str_representation():
        charge = TabChargeFactory(amount=Decimal("50.00"), status=TabCharge.Status.SUCCEEDED)
        assert str(charge) == "Charge $50.00 (Succeeded)"

    def it_defaults_to_pending_status():
        charge = TabChargeFactory()
        assert charge.status == TabCharge.Status.PENDING

    def describe_is_retriable():
        def it_is_true_for_failed_with_retries_remaining():
            BillingSettingsFactory(max_retry_attempts=3)
            charge = TabChargeFactory(status=TabCharge.Status.FAILED, retry_count=1)
            assert charge.is_retriable is True

        def it_is_false_for_failed_with_retries_exhausted():
            BillingSettingsFactory(max_retry_attempts=3)
            charge = TabChargeFactory(status=TabCharge.Status.FAILED, retry_count=3)
            assert charge.is_retriable is False

        def it_is_false_for_succeeded_charges():
            charge = TabChargeFactory(status=TabCharge.Status.SUCCEEDED)
            assert charge.is_retriable is False

        def it_is_false_for_pending_charges():
            charge = TabChargeFactory(status=TabCharge.Status.PENDING)
            assert charge.is_retriable is False

        def it_is_false_for_processing_charges():
            charge = TabChargeFactory(status=TabCharge.Status.PROCESSING)
            assert charge.is_retriable is False

    def describe_entry_count():
        def it_returns_zero_with_no_entries():
            charge = TabChargeFactory()
            assert charge.entry_count == 0

        def it_counts_linked_entries():
            tab = TabFactory()
            charge = TabChargeFactory(tab=tab)
            TabEntryFactory(tab=tab, tab_charge=charge)
            TabEntryFactory(tab=tab, tab_charge=charge)
            assert charge.entry_count == 2

    def describe_queryset():
        def it_filters_succeeded_charges():
            tab = TabFactory()
            succeeded = TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)
            TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)

            result = TabCharge.objects.succeeded()
            assert list(result) == [succeeded]

        def it_filters_failed_charges():
            tab = TabFactory()
            TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)
            failed = TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)

            result = TabCharge.objects.failed()
            assert list(result) == [failed]

        def it_filters_needs_retry():
            tab = TabFactory()
            past = timezone.now() - timedelta(hours=1)
            future = timezone.now() + timedelta(hours=1)
            ready = TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED, next_retry_at=past)
            TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED, next_retry_at=future)  # not yet
            TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED, next_retry_at=None)  # no retry
            TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)  # wrong status

            result = TabCharge.objects.needs_retry()
            assert list(result) == [ready]

    def describe_execute_stripe_charge():
        def it_returns_true_and_sets_succeeded_on_success():
            from unittest.mock import patch

            charge = TabChargeFactory(amount=Decimal("50.00"))
            mock_result = {"id": "pi_1", "charge_id": "ch_1", "receipt_url": "https://r.url"}

            with patch("billing.stripe_utils.create_payment_intent", return_value=mock_result) as mock_create:
                result = charge.execute_stripe_charge("idem-key-1")
                mock_create.assert_called_once()

            charge.refresh_from_db()
            assert result is True
            assert charge.status == TabCharge.Status.SUCCEEDED
            assert charge.stripe_payment_intent_id == "pi_1"
            assert charge.stripe_charge_id == "ch_1"
            assert charge.stripe_receipt_url == "https://r.url"
            assert charge.charged_at is not None

        def it_calls_platform_path_with_expected_arguments():
            from unittest.mock import patch

            tab = TabFactory(stripe_customer_id="cus_platform", stripe_payment_method_id="pm_platform")
            charge = TabChargeFactory(tab=tab, amount=Decimal("12.34"))
            mock_result = {"id": "pi_2", "charge_id": "ch_2", "receipt_url": ""}

            with patch("billing.stripe_utils.create_payment_intent", return_value=mock_result) as mock_create:
                charge.execute_stripe_charge("idem-key-2")

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["customer_id"] == "cus_platform"
            assert call_kwargs["payment_method_id"] == "pm_platform"
            assert call_kwargs["amount_cents"] == 1234
            assert call_kwargs["idempotency_key"] == "idem-key-2"
            assert call_kwargs["metadata"]["tab_id"] == str(tab.pk)
            assert call_kwargs["metadata"]["charge_id"] == str(charge.pk)

        def it_returns_false_and_sets_failed_on_stripe_exception():
            from unittest.mock import patch

            charge = TabChargeFactory(amount=Decimal("30.00"))

            with patch("billing.stripe_utils.create_payment_intent", side_effect=Exception("boom")):
                result = charge.execute_stripe_charge("idem-key-3")

            charge.refresh_from_db()
            assert result is False
            assert charge.status == TabCharge.Status.FAILED
            assert charge.failure_reason != ""
