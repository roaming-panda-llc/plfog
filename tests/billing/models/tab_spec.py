"""BDD-style tests for Tab model."""

from decimal import Decimal

import pytest
from django.db.models import ProtectedError

from tests.billing.factories import BillingSettingsFactory, TabEntryFactory, TabFactory, UserFactory

pytestmark = pytest.mark.django_db


def describe_Tab():
    def it_has_str_representation():
        tab = TabFactory()
        assert str(tab) == f"Tab for {tab.member}"

    def it_protects_member_on_delete():
        tab = TabFactory()
        with pytest.raises(ProtectedError):
            tab.member.delete()

    def describe_effective_tab_limit():
        def it_returns_per_member_override_when_set():
            tab = TabFactory(tab_limit=Decimal("500.00"))
            assert tab.effective_tab_limit == Decimal("500.00")

        def it_returns_global_default_when_no_override():
            BillingSettingsFactory(default_tab_limit=Decimal("300.00"))
            tab = TabFactory(tab_limit=None)
            assert tab.effective_tab_limit == Decimal("300.00")

    def describe_current_balance():
        def it_returns_zero_with_no_entries():
            tab = TabFactory()
            assert tab.current_balance == Decimal("0.00")

        def it_sums_pending_entries():
            tab = TabFactory()
            TabEntryFactory(tab=tab, amount=Decimal("10.00"))
            TabEntryFactory(tab=tab, amount=Decimal("15.50"))
            assert tab.current_balance == Decimal("25.50")

        def it_excludes_voided_entries():
            tab = TabFactory()
            TabEntryFactory(tab=tab, amount=Decimal("10.00"))
            voided = TabEntryFactory(tab=tab, amount=Decimal("20.00"))
            user = UserFactory()
            voided.void(user=user, reason="test")
            assert tab.current_balance == Decimal("10.00")

        def it_excludes_charged_entries():
            from tests.billing.factories import TabChargeFactory

            tab = TabFactory()
            charge = TabChargeFactory(tab=tab)
            TabEntryFactory(tab=tab, amount=Decimal("10.00"), tab_charge=charge)
            TabEntryFactory(tab=tab, amount=Decimal("5.00"))
            assert tab.current_balance == Decimal("5.00")

    def describe_has_payment_method():
        def it_returns_true_when_set():
            tab = TabFactory(stripe_payment_method_id="pm_test_123")
            assert tab.has_payment_method is True

        def it_returns_false_when_blank():
            tab = TabFactory(stripe_payment_method_id="")
            assert tab.has_payment_method is False

    def describe_can_add_entry():
        def it_returns_true_when_unlocked():
            tab = TabFactory(is_locked=False)
            assert tab.can_add_entry is True

        def it_returns_false_when_locked():
            tab = TabFactory(is_locked=True)
            assert tab.can_add_entry is False

        def it_returns_false_without_a_saved_payment_method():
            # v1.5.0: restored the has_payment_method gate — charges go through the
            # platform account off-session, so a saved card is required up front.
            tab = TabFactory(is_locked=False, stripe_payment_method_id="")
            assert tab.can_add_entry is False

    def describe_remaining_limit():
        def it_returns_full_limit_with_no_entries():
            BillingSettingsFactory(default_tab_limit=Decimal("200.00"))
            tab = TabFactory(tab_limit=None)
            assert tab.remaining_limit == Decimal("200.00")

        def it_subtracts_pending_balance():
            BillingSettingsFactory(default_tab_limit=Decimal("200.00"))
            tab = TabFactory(tab_limit=None)
            TabEntryFactory(tab=tab, amount=Decimal("75.00"))
            assert tab.remaining_limit == Decimal("125.00")

    # TODO(splits): rewrite in Task 4 — Tab.add_entry() now requires a product
    # (with splits) or an explicit splits=[...] payload. The old kwargs
    # (guild=, admin_percent=, split_mode=) are gone. Task 4 reinstates all of
    # these tests against the new signature.
    # def describe_add_entry():
    #     def it_creates_an_entry(): ...
    #     def it_creates_self_service_entry(): ...
    #     def it_raises_TabLockedError_when_locked(): ...
    #     def it_allows_entry_without_a_saved_payment_method(): ...
    #     def it_raises_TabLimitExceededError_when_over_limit(): ...
    #     def it_allows_entry_at_exact_limit(): ...
    #     def it_rejects_entry_one_cent_over_limit(): ...

    def describe_lock():
        def it_locks_the_tab():
            tab = TabFactory(is_locked=False)
            tab.lock("Payment failed")
            tab.refresh_from_db()
            assert tab.is_locked is True
            assert tab.locked_reason == "Payment failed"

    def describe_unlock():
        def it_unlocks_the_tab():
            tab = TabFactory(is_locked=True, locked_reason="Payment failed")
            tab.unlock()
            tab.refresh_from_db()
            assert tab.is_locked is False
            assert tab.locked_reason == ""

    def describe_get_or_create_stripe_customer():
        def it_returns_existing_customer_id_without_calling_stripe():
            from unittest.mock import patch

            tab = TabFactory(stripe_customer_id="cus_existing")
            with patch("billing.stripe_utils.create_customer") as mock_create:
                result = tab.get_or_create_stripe_customer()
            assert result == "cus_existing"
            mock_create.assert_not_called()

        def it_creates_customer_when_none_exists():
            from unittest.mock import patch

            tab = TabFactory(stripe_customer_id="")
            with patch("billing.stripe_utils.create_customer", return_value="cus_new") as mock_create:
                result = tab.get_or_create_stripe_customer()
            assert result == "cus_new"
            mock_create.assert_called_once()
            tab.refresh_from_db()
            assert tab.stripe_customer_id == "cus_new"

    def describe_set_payment_method():
        def it_attaches_and_persists_payment_method_when_customer_exists():
            from unittest.mock import patch

            tab = TabFactory(stripe_customer_id="cus_123", stripe_payment_method_id="")
            pm_details = {"id": "pm_new", "last4": "4242", "brand": "visa"}
            with (
                patch("billing.stripe_utils.attach_payment_method") as mock_attach,
                patch("billing.stripe_utils.retrieve_payment_method", return_value=pm_details),
            ):
                tab.set_payment_method("pm_new")
            mock_attach.assert_called_once_with(customer_id="cus_123", payment_method_id="pm_new")
            tab.refresh_from_db()
            assert tab.stripe_payment_method_id == "pm_new"
            assert tab.payment_method_last4 == "4242"
            assert tab.payment_method_brand == "visa"

        def it_skips_attach_when_no_stripe_customer():
            from unittest.mock import patch

            tab = TabFactory(stripe_customer_id="", stripe_payment_method_id="")
            pm_details = {"id": "pm_noattach", "last4": "9999", "brand": "mastercard"}
            with (
                patch("billing.stripe_utils.attach_payment_method") as mock_attach,
                patch("billing.stripe_utils.retrieve_payment_method", return_value=pm_details),
            ):
                tab.set_payment_method("pm_noattach")
            mock_attach.assert_not_called()
            tab.refresh_from_db()
            assert tab.stripe_payment_method_id == "pm_noattach"

    def describe_clear_payment_method():
        def it_detaches_and_clears_payment_fields():
            from unittest.mock import patch

            tab = TabFactory(
                stripe_payment_method_id="pm_old",
                payment_method_last4="1234",
                payment_method_brand="visa",
            )
            with patch("billing.stripe_utils.detach_payment_method") as mock_detach:
                tab.clear_payment_method()
            mock_detach.assert_called_once_with(payment_method_id="pm_old")
            tab.refresh_from_db()
            assert tab.stripe_payment_method_id == ""
            assert tab.payment_method_last4 == ""
            assert tab.payment_method_brand == ""

        def it_does_nothing_when_no_payment_method():
            from unittest.mock import patch

            tab = TabFactory(stripe_payment_method_id="")
            with patch("billing.stripe_utils.detach_payment_method") as mock_detach:
                tab.clear_payment_method()
            mock_detach.assert_not_called()
