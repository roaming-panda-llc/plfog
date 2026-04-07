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
        def it_returns_true_and_sets_succeeded_on_success_without_stripe_account():
            from unittest.mock import patch

            charge = TabChargeFactory(amount=Decimal("50.00"), stripe_account=None)
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

        def it_returns_true_and_calls_destination_intent_when_stripe_account_set():
            from unittest.mock import patch

            from tests.billing.factories import StripeAccountFactory

            stripe_account = StripeAccountFactory(stripe_account_id="acct_dest_123")
            tab = TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            charge = TabChargeFactory(tab=tab, amount=Decimal("75.00"), stripe_account=stripe_account)
            mock_result = {"id": "pi_2", "charge_id": "ch_2", "receipt_url": "https://r2.url"}

            with patch("billing.stripe_utils.create_destination_payment_intent", return_value=mock_result) as mock_dest:
                result = charge.execute_stripe_charge("idem-key-2")

            assert result is True
            mock_dest.assert_called_once()
            call_kwargs = mock_dest.call_args[1]
            assert call_kwargs["destination_account_id"] == "acct_dest_123"

        def it_returns_false_and_sets_failed_on_stripe_exception():
            from unittest.mock import patch

            charge = TabChargeFactory(amount=Decimal("30.00"), stripe_account=None)

            with patch("billing.stripe_utils.create_payment_intent", side_effect=Exception("boom")):
                result = charge.execute_stripe_charge("idem-key-3")

            charge.refresh_from_db()
            assert result is False
            assert charge.status == TabCharge.Status.FAILED
            assert charge.failure_reason != ""

        def it_computes_fee_cents_from_application_fee():
            from unittest.mock import patch

            from tests.billing.factories import StripeAccountFactory

            stripe_account = StripeAccountFactory(stripe_account_id="acct_fee_456")
            tab = TabFactory(stripe_customer_id="cus_fee", stripe_payment_method_id="pm_fee")
            charge = TabChargeFactory(
                tab=tab,
                amount=Decimal("100.00"),
                stripe_account=stripe_account,
                application_fee=Decimal("2.50"),
            )
            mock_result = {"id": "pi_3", "charge_id": "ch_3", "receipt_url": ""}

            with patch("billing.stripe_utils.create_destination_payment_intent", return_value=mock_result) as mock_dest:
                charge.execute_stripe_charge("idem-key-4")

            call_kwargs = mock_dest.call_args[1]
            assert call_kwargs["application_fee_cents"] == 250

        def it_passes_none_fee_when_no_application_fee():
            from unittest.mock import patch

            from tests.billing.factories import StripeAccountFactory

            stripe_account = StripeAccountFactory(stripe_account_id="acct_nofee_789")
            tab = TabFactory(stripe_customer_id="cus_nofee", stripe_payment_method_id="pm_nofee")
            charge = TabChargeFactory(
                tab=tab,
                amount=Decimal("40.00"),
                stripe_account=stripe_account,
                application_fee=None,
            )
            mock_result = {"id": "pi_4", "charge_id": "ch_4", "receipt_url": ""}

            with patch("billing.stripe_utils.create_destination_payment_intent", return_value=mock_result) as mock_dest:
                charge.execute_stripe_charge("idem-key-5")

            call_kwargs = mock_dest.call_args[1]
            assert call_kwargs["application_fee_cents"] is None

        def context_with_direct_keys_account():
            def it_creates_a_checkout_session_and_marks_pending_checkout():
                from unittest.mock import patch

                from tests.billing.factories import DirectKeysStripeAccountFactory

                stripe_account = DirectKeysStripeAccountFactory()
                tab = TabFactory()
                charge = TabChargeFactory(tab=tab, amount=Decimal("15.00"), stripe_account=stripe_account)
                mock_session = {"id": "cs_test_clay", "url": "https://checkout.stripe.com/c/pay/cs_test_clay"}

                with (
                    patch(
                        "billing.stripe_utils.create_checkout_session_for_account",
                        return_value=mock_session,
                    ) as mock_checkout,
                    patch("billing.stripe_utils.create_destination_payment_intent") as mock_dest,
                ):
                    result = charge.execute_stripe_charge("idem-direct-1")

                charge.refresh_from_db()
                assert result is True
                assert charge.status == TabCharge.Status.PENDING_CHECKOUT
                assert charge.stripe_checkout_session_id == "cs_test_clay"
                assert charge.stripe_checkout_url == "https://checkout.stripe.com/c/pay/cs_test_clay"
                # Did NOT use the OAuth destination charge path
                mock_dest.assert_not_called()
                # Did call the direct-keys checkout helper with the right account
                mock_checkout.assert_called_once()
                assert mock_checkout.call_args.kwargs["stripe_account"] == stripe_account
                assert mock_checkout.call_args.kwargs["amount_cents"] == 1500
