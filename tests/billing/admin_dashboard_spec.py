"""BDD-style tests for billing admin dashboard and add-entry views."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from billing.models import BillingSettings, Tab, TabCharge
from tests.billing.factories import BillingSettingsFactory, TabChargeFactory, TabEntryFactory, TabFactory
from tests.membership.factories import MemberFactory

pytestmark = pytest.mark.django_db


def _create_superuser(client: Client) -> User:
    user = User.objects.create_superuser(username="admin", password="pass", email="admin@example.com")
    client.login(username="admin", password="pass")
    return user


def describe_admin_tab_dashboard():
    def it_requires_staff(client: Client):
        response = client.get("/billing/admin/dashboard/")
        assert response.status_code == 302

    def it_renders_for_superuser(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/dashboard/")

        assert response.status_code == 200
        assert "total_outstanding" in response.context

    def it_shows_aggregate_stats(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)
        TabEntryFactory(tab=tab, amount=Decimal("30.00"))
        TabEntryFactory(tab=tab, amount=Decimal("20.00"))
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED, amount=Decimal("10.00"))

        response = client.get("/billing/admin/dashboard/")

        assert response.context["total_outstanding"] == Decimal("50.00")
        assert response.context["failed_count"] == 1

    def it_shows_outstanding_tabs(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)
        TabEntryFactory(tab=tab, amount=Decimal("30.00"))

        response = client.get("/billing/admin/dashboard/")

        # At least our tab with entries shows up
        assert tab in response.context["outstanding_tabs"]

    def it_shows_locked_count(client: Client):
        _create_superuser(client)
        TabFactory(is_locked=True)

        response = client.get("/billing/admin/dashboard/")

        assert response.context["locked_count"] == 1


def describe_admin_tab_dashboard_extended():
    def it_defaults_to_overview_tab(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/dashboard/")
        assert response.context["active_tab"] == "overview"

    def it_sets_active_tab_from_query_param(client: Client):
        _create_superuser(client)
        for tab_name in ["overview", "open-tabs", "history", "settings", "stripe"]:
            response = client.get(f"/billing/admin/dashboard/?tab={tab_name}")
            assert response.context["active_tab"] == tab_name

    def it_unknown_tab_defaults_to_overview(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/dashboard/?tab=bogus")
        assert response.context["active_tab"] == "overview"

    def it_provides_open_tabs_filter_outstanding(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)
        TabEntryFactory(tab=tab, amount=Decimal("10.00"))

        response = client.get("/billing/admin/dashboard/?tab=open-tabs&filter=outstanding")
        assert tab in response.context["open_tabs"]

    def it_provides_open_tabs_filter_all(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)

        response = client.get("/billing/admin/dashboard/?tab=open-tabs&filter=all")
        assert tab in response.context["open_tabs"]

    def it_provides_open_tabs_filter_failed(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)

        response = client.get("/billing/admin/dashboard/?tab=open-tabs&filter=failed")
        assert tab in response.context["open_tabs"]

    def it_provides_history_charges_all(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        charge = TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)

        response = client.get("/billing/admin/dashboard/?tab=history&status=all")
        assert charge in response.context["history_charges"]

    def it_provides_history_charges_filter_succeeded(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        succeeded = TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)

        response = client.get("/billing/admin/dashboard/?tab=history&status=succeeded")
        charges = list(response.context["history_charges"])
        assert succeeded in charges
        assert all(c.status == TabCharge.Status.SUCCEEDED for c in charges)

    def it_provides_history_charges_filter_failed(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        failed = TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)
        TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)

        response = client.get("/billing/admin/dashboard/?tab=history&status=failed")
        charges = list(response.context["history_charges"])
        assert failed in charges
        assert all(c.status == TabCharge.Status.FAILED for c in charges)

    def it_provides_history_charges_filter_needs_retry(client: Client):
        from django.utils import timezone as tz

        _create_superuser(client)
        tab = TabFactory()
        retryable = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            next_retry_at=tz.now() - timedelta(hours=1),
        )
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED, next_retry_at=None)

        response = client.get("/billing/admin/dashboard/?tab=history&status=needs_retry")
        charges = list(response.context["history_charges"])
        assert retryable in charges

    def it_provides_history_month_stats(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED, amount=Decimal("75.00"), charged_at=timezone.now())

        response = client.get("/billing/admin/dashboard/?tab=history")
        assert response.context["history_collected"] == Decimal("75.00")
        assert response.context["history_failed_count"] == 0

    def it_provides_settings_form(client: Client):
        _create_superuser(client)
        BillingSettingsFactory()

        response = client.get("/billing/admin/dashboard/?tab=settings")
        assert "settings_form" in response.context
        from billing.forms import BillingSettingsForm

        assert isinstance(response.context["settings_form"], BillingSettingsForm)

    def it_provides_stripe_context(client: Client):
        _create_superuser(client)
        from tests.billing.factories import ProductFactory, StripeAccountFactory

        StripeAccountFactory()
        ProductFactory()

        response = client.get("/billing/admin/dashboard/?tab=stripe")
        assert "stripe_accounts" in response.context
        assert "products" in response.context
        assert "guilds" in response.context


def describe_billing_admin_tab_detail_api():
    def it_requires_staff(client: Client):
        response = client.get("/billing/admin/tab/999/detail/")
        assert response.status_code == 302

    def it_returns_404_for_missing_tab(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/tab/999999/detail/")
        assert response.status_code == 404

    def it_returns_tab_data_as_json(client: Client):
        _create_superuser(client)
        member = MemberFactory(full_legal_name="Jane Doe")
        tab = TabFactory(
            member=member,
            stripe_payment_method_id="pm_test",
            payment_method_brand="visa",
            payment_method_last4="4242",
            tab_limit=Decimal("150.00"),
        )
        TabEntryFactory(tab=tab, description="Laser time", amount=Decimal("20.00"))

        response = client.get(f"/billing/admin/tab/{tab.pk}/detail/")

        assert response.status_code == 200
        data = response.json()
        assert data["member_name"] == "Jane Doe"
        assert data["balance"] == "20.00"
        assert data["limit"] == "150.00"
        assert data["payment_method"] == "visa 4242"
        assert data["is_locked"] is False
        assert len(data["pending_entries"]) == 1
        assert data["pending_entries"][0]["description"] == "Laser time"
        assert data["pending_entries"][0]["amount"] == "20.00"

    def it_returns_charge_history(client: Client):
        _create_superuser(client)
        member = MemberFactory()
        tab = TabFactory(member=member)
        TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.SUCCEEDED,
            amount=Decimal("50.00"),
            stripe_receipt_url="https://receipt.test",
        )

        response = client.get(f"/billing/admin/tab/{tab.pk}/detail/")
        data = response.json()

        assert len(data["charge_history"]) == 1
        assert data["charge_history"][0]["amount"] == "50.00"
        assert data["charge_history"][0]["status"] == "succeeded"
        assert data["charge_history"][0]["receipt_url"] == "https://receipt.test"

    def it_shows_no_payment_method_when_absent(client: Client):
        _create_superuser(client)
        member = MemberFactory()
        tab = TabFactory(member=member, stripe_payment_method_id="", payment_method_brand="", payment_method_last4="")

        response = client.get(f"/billing/admin/tab/{tab.pk}/detail/")
        data = response.json()

        assert data["payment_method"] == ""


def describe_billing_admin_save_settings():
    def it_requires_staff(client: Client):
        response = client.post("/billing/admin/save-settings/", {})
        assert response.status_code == 302
        assert "/accounts/login/" in response.url or "/admin/login/" in response.url

    def it_saves_valid_settings_and_redirects(client: Client):
        _create_superuser(client)
        BillingSettingsFactory()

        response = client.post(
            "/billing/admin/save-settings/",
            {
                "charge_frequency": "weekly",
                "charge_time": "22:00",
                "charge_day_of_week": "1",
                "charge_day_of_month": "",
                "default_tab_limit": "150.00",
                "max_retry_attempts": "5",
                "retry_interval_hours": "12",
            },
        )

        assert response.status_code == 302
        assert response.url == "/billing/admin/dashboard/?tab=settings"
        settings = BillingSettings.load()
        assert settings.charge_frequency == "weekly"
        assert settings.max_retry_attempts == 5

    def it_redirects_with_error_on_invalid_data(client: Client):
        _create_superuser(client)
        BillingSettingsFactory()

        response = client.post(
            "/billing/admin/save-settings/",
            {
                "charge_frequency": "daily",
                "charge_time": "23:00",
                "charge_day_of_week": "",
                "charge_day_of_month": "",
                "default_tab_limit": "-50.00",
                "max_retry_attempts": "3",
                "retry_interval_hours": "24",
            },
        )

        assert response.status_code == 302
        assert "tab=settings" in response.url
        settings = BillingSettings.load()
        assert settings.default_tab_limit != Decimal("-50.00")

    def it_only_accepts_post(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/save-settings/")
        assert response.status_code == 405


def describe_billing_admin_retry_charge():
    def it_requires_staff(client: Client):
        response = client.post("/billing/admin/retry-charge/999/")
        assert response.status_code == 302

    def it_returns_404_for_missing_charge(client: Client):
        _create_superuser(client)
        response = client.post("/billing/admin/retry-charge/999999/")
        assert response.status_code == 404

    def it_succeeds_when_stripe_succeeds(client: Client):
        _create_superuser(client)
        tab = TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
        charge = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            amount=Decimal("25.00"),
            stripe_account=None,
        )

        mock_result = {"id": "pi_test123", "charge_id": "ch_test123", "receipt_url": "https://receipt.test"}
        with patch("billing.views.stripe_utils.create_payment_intent", return_value=mock_result):
            response = client.post(f"/billing/admin/retry-charge/{charge.pk}/")

        assert response.status_code == 200
        assert response.json()["status"] == "succeeded"
        charge.refresh_from_db()
        assert charge.status == TabCharge.Status.SUCCEEDED
        assert charge.stripe_payment_intent_id == "pi_test123"

    def it_succeeds_destination_charge_when_stripe_account_present(client: Client):
        _create_superuser(client)
        from tests.billing.factories import StripeAccountFactory

        stripe_acct = StripeAccountFactory(stripe_account_id="acct_test")
        tab = TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
        charge = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            amount=Decimal("50.00"),
            stripe_account=stripe_acct,
            application_fee=Decimal("2.50"),
        )

        mock_result = {"id": "pi_dest123", "charge_id": "ch_dest123", "receipt_url": "https://receipt.dest"}
        with patch("billing.views.stripe_utils.create_destination_payment_intent", return_value=mock_result):
            response = client.post(f"/billing/admin/retry-charge/{charge.pk}/")

        assert response.status_code == 200
        assert response.json()["status"] == "succeeded"

    def it_returns_failed_json_when_stripe_raises(client: Client):
        _create_superuser(client)
        tab = TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
        charge = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            amount=Decimal("25.00"),
            stripe_account=None,
        )

        with patch("billing.views.stripe_utils.create_payment_intent", side_effect=Exception("Card declined")):
            response = client.post(f"/billing/admin/retry-charge/{charge.pk}/")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        charge.refresh_from_db()
        assert charge.status == TabCharge.Status.FAILED


def describe_admin_add_tab_entry():
    def it_requires_staff(client: Client):
        response = client.get("/billing/admin/add-entry/")
        assert response.status_code == 302

    def it_renders_form(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/add-entry/")

        assert response.status_code == 200
        assert "form" in response.context

    def it_creates_entry_on_valid_post(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        TabFactory(member=member, stripe_payment_method_id="pm_test123")

        response = client.post(
            "/billing/admin/add-entry/",
            {
                "member": member.pk,
                "description": "Admin charge",
                "amount": "25.00",
            },
        )

        assert response.status_code == 302
        tab = Tab.objects.get(member=member)
        assert tab.entries.count() == 1
        assert tab.entries.first().amount == Decimal("25.00")

    def it_shows_errors_on_invalid_post(client: Client):
        _create_superuser(client)

        response = client.post(
            "/billing/admin/add-entry/",
            {
                "description": "Missing member",
                "amount": "10.00",
            },
        )

        assert response.status_code == 200  # Re-renders form with errors

    def it_shows_error_when_tab_add_entry_raises(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        # Locked tab — add_entry raises TabLockedError
        TabFactory(member=member, is_locked=True, locked_reason="Frozen for testing")

        response = client.post(
            "/billing/admin/add-entry/",
            {
                "member": member.pk,
                "description": "Charge",
                "amount": "10.00",
            },
        )

        assert response.status_code == 200  # Re-renders form with error message
