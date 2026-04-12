"""BDD-style tests for billing-related forms."""

from __future__ import annotations

from decimal import Decimal

import pytest

from billing.forms import (
    CONTEXT_ADMIN_DASHBOARD,
    CONTEXT_MEMBER_GUILD_PAGE,
    CONTEXT_MEMBER_TAB_PAGE,
    BillingSettingsForm,
    ConnectPlatformSettingsForm,
    TabItemForm,
    VoidTabEntryForm,
)
from billing.models import Product
from tests.billing.factories import BillingSettingsFactory, ProductFactory, TabFactory, UserFactory
from tests.membership.factories import GuildFactory, MemberFactory

pytestmark = pytest.mark.django_db


def _member_user(*, fog_role: str = "member"):
    """Create a User linked to a Member with the requested fog_role.

    The post_save signal on User auto-creates a Member, so we just grab it
    back and set the fog_role directly (skipping the permission-check helper).
    """
    # Need a MembershipPlan for the auto-creation signal to succeed
    from tests.membership.factories import MembershipPlanFactory

    MembershipPlanFactory()
    user = UserFactory()
    member = user.member
    member.fog_role = fog_role
    member.save(update_fields=["fog_role"])
    member.sync_user_permissions()
    user.refresh_from_db()
    return user, member


def describe_TabItemForm_member_tab_page():
    def it_is_valid_with_description_and_amount():
        BillingSettingsFactory()
        form = TabItemForm(
            data={"description": "Laser cutter", "amount": "15.00"},
            context=CONTEXT_MEMBER_TAB_PAGE,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["admin_percent"] == Decimal("20.00")
        assert form.cleaned_data["split_mode"] == Product.SplitMode.SINGLE_GUILD

    def it_rejects_when_no_product_and_no_manual_fields():
        form = TabItemForm(data={}, context=CONTEXT_MEMBER_TAB_PAGE)
        assert not form.is_valid()
        assert form.non_field_errors()

    def it_rejects_zero_amount():
        form = TabItemForm(
            data={"description": "Test", "amount": "0.00"},
            context=CONTEXT_MEMBER_TAB_PAGE,
        )
        assert not form.is_valid()
        assert "amount" in form.errors

    def it_accepts_one_cent_minimum():
        BillingSettingsFactory()
        form = TabItemForm(
            data={"description": "Tiny", "amount": "0.01"},
            context=CONTEXT_MEMBER_TAB_PAGE,
        )
        assert form.is_valid()
        assert form.cleaned_data["amount"] == Decimal("0.01")

    def it_fills_description_and_amount_from_product():
        BillingSettingsFactory()
        product = ProductFactory(name="Laser time", price=Decimal("12.50"))
        form = TabItemForm(data={"product": product.pk}, context=CONTEXT_MEMBER_TAB_PAGE)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["description"] == "Laser time"
        assert form.cleaned_data["amount"] == Decimal("12.50")
        assert form.cleaned_data["guild"] == product.guild

    def it_resolves_admin_percent_from_product_override():
        BillingSettingsFactory(default_admin_percent=Decimal("20.00"))
        product = ProductFactory(admin_percent_override=Decimal("50.00"))
        form = TabItemForm(data={"product": product.pk}, context=CONTEXT_MEMBER_TAB_PAGE)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["admin_percent"] == Decimal("50.00")


def describe_TabItemForm_member_role_gating():
    def it_disables_admin_percent_for_non_staff_members():
        BillingSettingsFactory()
        user, _member = _member_user(fog_role="member")
        form = TabItemForm(
            data={"description": "Tool", "amount": "5.00", "admin_percent": "90"},
            context=CONTEXT_MEMBER_TAB_PAGE,
            user=user,
        )
        assert form.is_valid(), form.errors
        # Disabled field → POST value is discarded, form falls back to the site default
        assert form.cleaned_data["admin_percent"] == Decimal("20.00")

    def it_allows_officer_to_override_admin_percent():
        BillingSettingsFactory()
        user, _member = _member_user(fog_role="guild_officer")
        form = TabItemForm(
            data={"description": "Tool", "amount": "5.00", "admin_percent": "40"},
            context=CONTEXT_MEMBER_TAB_PAGE,
            user=user,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["admin_percent"] == Decimal("40.00")

    def it_disables_split_equally_for_non_staff_members():
        BillingSettingsFactory()
        user, _member = _member_user(fog_role="member")
        form = TabItemForm(
            data={
                "description": "Tool",
                "amount": "5.00",
                "split_equally": "on",
            },
            context=CONTEXT_MEMBER_TAB_PAGE,
            user=user,
        )
        assert form.is_valid()
        assert form.cleaned_data["split_mode"] == Product.SplitMode.SINGLE_GUILD

    def it_allows_officer_to_toggle_split_equally():
        BillingSettingsFactory()
        user, _member = _member_user(fog_role="guild_officer")
        form = TabItemForm(
            data={
                "description": "Tool",
                "amount": "5.00",
                "split_equally": "on",
            },
            context=CONTEXT_MEMBER_TAB_PAGE,
            user=user,
        )
        assert form.is_valid()
        assert form.cleaned_data["split_mode"] == Product.SplitMode.SPLIT_EQUALLY


def describe_TabItemForm_member_guild_page():
    def it_requires_guild_kwarg_in_init():
        import pytest

        with pytest.raises(ValueError, match="requires guild"):
            TabItemForm(context=CONTEXT_MEMBER_GUILD_PAGE)

    def it_fixes_guild_from_constructor():
        BillingSettingsFactory()
        guild = GuildFactory()
        form = TabItemForm(
            data={"description": "Donation", "amount": "5.00"},
            context=CONTEXT_MEMBER_GUILD_PAGE,
            guild=guild,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["guild"] == guild

    def it_requires_description_and_amount():
        guild = GuildFactory()
        form = TabItemForm(
            data={},
            context=CONTEXT_MEMBER_GUILD_PAGE,
            guild=guild,
        )
        assert not form.is_valid()


def describe_TabItemForm_admin_dashboard():
    def it_is_valid_with_member_and_manual_entry():
        BillingSettingsFactory()
        member = MemberFactory()
        form = TabItemForm(
            data={"member": member.pk, "description": "Admin charge", "amount": "50.00"},
            context=CONTEXT_ADMIN_DASHBOARD,
        )
        assert form.is_valid(), form.errors

    def it_rejects_missing_member():
        form = TabItemForm(
            data={"description": "Test", "amount": "10.00"},
            context=CONTEXT_ADMIN_DASHBOARD,
        )
        assert not form.is_valid()
        assert "member" in form.errors

    def it_fills_fields_from_product():
        BillingSettingsFactory()
        member = MemberFactory()
        product = ProductFactory(name="Plasma cutter", price=Decimal("25.00"))
        form = TabItemForm(
            data={"member": member.pk, "product": product.pk},
            context=CONTEXT_ADMIN_DASHBOARD,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["description"] == "Plasma cutter"
        assert form.cleaned_data["amount"] == Decimal("25.00")
        assert form.cleaned_data["guild"] == product.guild


def describe_TabItemForm_apply_to_tab():
    def it_snapshots_the_entry_onto_the_tab():
        BillingSettingsFactory()
        tab = TabFactory()
        guild = GuildFactory()
        form = TabItemForm(
            data={"description": "Clay", "amount": "4.00"},
            context=CONTEXT_MEMBER_GUILD_PAGE,
            guild=guild,
        )
        assert form.is_valid(), form.errors
        entry = form.apply_to_tab(tab, added_by=None, is_self_service=True)
        assert entry.description == "Clay"
        assert entry.amount == Decimal("4.00")
        assert entry.guild == guild
        assert entry.admin_percent == Decimal("20.00")
        assert entry.split_mode == Product.SplitMode.SINGLE_GUILD


def describe_VoidTabEntryForm():
    def it_is_valid_with_reason():
        form = VoidTabEntryForm(data={"reason": "Duplicate charge"})
        assert form.is_valid()

    def it_rejects_empty_reason():
        form = VoidTabEntryForm(data={"reason": ""})
        assert not form.is_valid()
        assert "reason" in form.errors


def describe_BillingSettingsForm():
    def it_is_valid_with_daily_frequency():
        form = BillingSettingsForm(
            data={
                "charge_frequency": "daily",
                "charge_time": "23:00",
                "charge_day_of_week": "",
                "charge_day_of_month": "",
                "default_tab_limit": "200.00",
                "default_admin_percent": "20.00",
                "max_retry_attempts": "3",
                "retry_interval_hours": "24",
            }
        )
        assert form.is_valid(), form.errors

    def it_is_valid_with_weekly_frequency():
        form = BillingSettingsForm(
            data={
                "charge_frequency": "weekly",
                "charge_time": "23:00",
                "charge_day_of_week": "0",
                "charge_day_of_month": "",
                "default_tab_limit": "200.00",
                "default_admin_percent": "20.00",
                "max_retry_attempts": "3",
                "retry_interval_hours": "24",
            }
        )
        assert form.is_valid(), form.errors

    def it_is_valid_with_monthly_frequency():
        form = BillingSettingsForm(
            data={
                "charge_frequency": "monthly",
                "charge_time": "23:00",
                "charge_day_of_week": "",
                "charge_day_of_month": "15",
                "default_tab_limit": "200.00",
                "default_admin_percent": "20.00",
                "max_retry_attempts": "3",
                "retry_interval_hours": "24",
            }
        )
        assert form.is_valid(), form.errors

    def it_populates_from_instance(db):
        settings = BillingSettingsFactory(
            charge_frequency="weekly",
            charge_day_of_week=2,
            default_tab_limit="150.00",
        )
        form = BillingSettingsForm(instance=settings)
        assert form.initial.get("charge_frequency") == "weekly" or form["charge_frequency"].value() == "weekly"
        assert form["default_tab_limit"].value() == "150.00"

    def it_rejects_negative_tab_limit():
        form = BillingSettingsForm(
            data={
                "charge_frequency": "daily",
                "charge_time": "23:00",
                "charge_day_of_week": "",
                "charge_day_of_month": "",
                "default_tab_limit": "-10.00",
                "default_admin_percent": "20.00",
                "max_retry_attempts": "3",
                "retry_interval_hours": "24",
            }
        )
        assert not form.is_valid()
        assert "default_tab_limit" in form.errors


def describe_ConnectPlatformSettingsForm():
    def it_is_valid_when_disabled_with_all_fields_empty():
        form = ConnectPlatformSettingsForm(
            data={
                "connect_enabled": "",
                "connect_client_id": "",
                "connect_platform_publishable_key": "",
                "connect_platform_secret_key": "",
                "connect_platform_webhook_secret": "",
            }
        )
        assert form.is_valid()

    def it_is_valid_when_enabled_with_all_fields():
        form = ConnectPlatformSettingsForm(
            data={
                "connect_enabled": "on",
                "connect_client_id": "ca_test_1",
                "connect_platform_publishable_key": "pk_test_1",
                "connect_platform_secret_key": "sk_test_1",
                "connect_platform_webhook_secret": "whsec_1",
            }
        )
        assert form.is_valid()

    def it_errors_when_enabled_with_missing_secret_key():
        form = ConnectPlatformSettingsForm(
            data={
                "connect_enabled": "on",
                "connect_client_id": "ca_test_1",
                "connect_platform_publishable_key": "pk_test_1",
                "connect_platform_secret_key": "",
                "connect_platform_webhook_secret": "whsec_1",
            }
        )
        assert not form.is_valid()
        assert "connect_platform_secret_key" in form.errors

    def it_errors_on_all_missing_fields_when_enabled():
        form = ConnectPlatformSettingsForm(
            data={
                "connect_enabled": "on",
                "connect_client_id": "",
                "connect_platform_publishable_key": "",
                "connect_platform_secret_key": "",
                "connect_platform_webhook_secret": "",
            }
        )
        assert not form.is_valid()
        assert "connect_client_id" in form.errors
        assert "connect_platform_publishable_key" in form.errors
        assert "connect_platform_secret_key" in form.errors
        assert "connect_platform_webhook_secret" in form.errors
