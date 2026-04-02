"""BDD-style tests for Tab model."""

from decimal import Decimal

import pytest
from django.db.models import ProtectedError

from billing.exceptions import NoPaymentMethodError, TabLimitExceededError, TabLockedError
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
        def it_returns_true_when_unlocked_with_payment_method():
            tab = TabFactory(is_locked=False, stripe_payment_method_id="pm_test_123")
            assert tab.can_add_entry is True

        def it_returns_false_when_locked():
            tab = TabFactory(is_locked=True, stripe_payment_method_id="pm_test_123")
            assert tab.can_add_entry is False

        def it_returns_false_when_no_payment_method():
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

    def describe_add_entry():
        def it_creates_an_entry():
            BillingSettingsFactory(default_tab_limit=Decimal("200.00"))
            tab = TabFactory()
            user = UserFactory()
            entry = tab.add_entry(description="Laser time", amount=Decimal("15.00"), added_by=user)
            assert entry.description == "Laser time"
            assert entry.amount == Decimal("15.00")
            assert entry.added_by == user
            assert entry.tab == tab

        def it_creates_self_service_entry():
            BillingSettingsFactory(default_tab_limit=Decimal("200.00"))
            tab = TabFactory()
            entry = tab.add_entry(description="Self-service item", amount=Decimal("10.00"), is_self_service=True)
            assert entry.is_self_service is True

        def it_raises_TabLockedError_when_locked():
            tab = TabFactory(is_locked=True, locked_reason="Payment failed")
            with pytest.raises(TabLockedError, match="Payment failed"):
                tab.add_entry(description="Test", amount=Decimal("10.00"))

        def it_raises_NoPaymentMethodError_when_no_payment_method():
            tab = TabFactory(stripe_payment_method_id="")
            with pytest.raises(NoPaymentMethodError, match="No payment method"):
                tab.add_entry(description="Test", amount=Decimal("10.00"))

        def it_raises_TabLimitExceededError_when_over_limit():
            BillingSettingsFactory(default_tab_limit=Decimal("50.00"))
            tab = TabFactory(tab_limit=None)
            TabEntryFactory(tab=tab, amount=Decimal("40.00"))
            with pytest.raises(TabLimitExceededError, match="exceed tab limit"):
                tab.add_entry(description="Test", amount=Decimal("20.00"))

        def it_allows_entry_at_exact_limit():
            BillingSettingsFactory(default_tab_limit=Decimal("50.00"))
            tab = TabFactory(tab_limit=None)
            TabEntryFactory(tab=tab, amount=Decimal("40.00"))
            entry = tab.add_entry(description="Exact", amount=Decimal("10.00"))
            assert entry.amount == Decimal("10.00")

        def it_rejects_entry_one_cent_over_limit():
            BillingSettingsFactory(default_tab_limit=Decimal("50.00"))
            tab = TabFactory(tab_limit=None)
            TabEntryFactory(tab=tab, amount=Decimal("40.00"))
            with pytest.raises(TabLimitExceededError):
                tab.add_entry(description="Over", amount=Decimal("10.01"))

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
