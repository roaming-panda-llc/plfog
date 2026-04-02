"""BDD specs for hub tab views (tab_detail, tab_history)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import Client

from billing.models import TabCharge
from membership.models import Member
from membership.signals import ensure_user_has_member
from tests.billing.factories import BillingSettingsFactory, TabChargeFactory, TabEntryFactory, TabFactory

pytestmark = pytest.mark.django_db


def describe_tab_detail():
    def it_requires_login(client: Client):
        response = client.get("/tab/")
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def it_renders_for_member_with_no_tab(client: Client):
        User.objects.create_user(username="u1", password="pass")
        client.login(username="u1", password="pass")

        response = client.get("/tab/")

        assert response.status_code == 200
        assert response.context["tab"] is not None  # Tab created lazily

    def it_handles_user_with_no_member_linked(client: Client):
        """When user has no Member, _get_member returns None → tab is None."""
        post_save.disconnect(ensure_user_has_member, sender=User)
        try:
            user = User.objects.create_user(username="orphan", password="pass")
            client.login(username="orphan", password="pass")
            response = client.get("/tab/")
            assert response.status_code == 200
            assert response.context["tab"] is None
        finally:
            post_save.connect(ensure_user_has_member, sender=User)

    def it_shows_pending_entries(client: Client):
        user = User.objects.create_user(username="has_entries", password="pass")
        tab = TabFactory(member=user.member)
        TabEntryFactory(tab=tab, description="Laser cutter", amount=Decimal("15.00"))
        client.login(username="has_entries", password="pass")

        response = client.get("/tab/")

        assert response.status_code == 200
        assert len(response.context["entries"]) == 1
        assert b"Laser cutter" in response.content

    def describe_add_entry_form():
        @pytest.fixture()
        def setup(client: Client):
            BillingSettingsFactory(default_tab_limit=Decimal("200.00"))
            user = User.objects.create_user(username="adder", password="pass")
            tab = TabFactory(member=user.member, stripe_payment_method_id="pm_test_123")
            client.login(username="adder", password="pass")
            return tab

        def it_adds_entry_on_valid_post(client: Client, setup):
            response = client.post(
                "/tab/",
                {"description": "Wood glue", "amount": "5.50"},
            )

            assert response.status_code == 302
            assert response.url == "/tab/"
            assert setup.entries.count() == 1

        def it_rejects_empty_description(client: Client, setup):
            response = client.post("/tab/", {"description": "", "amount": "5.50"})

            assert response.status_code == 200
            assert setup.entries.count() == 0

        def it_rejects_zero_amount(client: Client, setup):
            response = client.post("/tab/", {"description": "Test", "amount": "0.00"})

            assert response.status_code == 200
            assert setup.entries.count() == 0

        def it_shows_error_when_tab_locked(client: Client):
            BillingSettingsFactory(default_tab_limit=Decimal("200.00"))
            user = User.objects.create_user(username="locked_user", password="pass")
            TabFactory(
                member=user.member,
                is_locked=True,
                locked_reason="Payment failed",
                stripe_payment_method_id="pm_test",
            )
            client.login(username="locked_user", password="pass")

            response = client.post("/tab/", {"description": "Test", "amount": "10.00"}, follow=True)

            assert b"locked" in response.content.lower()

        def it_shows_error_when_no_payment_method(client: Client):
            BillingSettingsFactory(default_tab_limit=Decimal("200.00"))
            user = User.objects.create_user(username="no_pm", password="pass")
            TabFactory(member=user.member, stripe_payment_method_id="")
            client.login(username="no_pm", password="pass")

            response = client.post("/tab/", {"description": "Test", "amount": "10.00"}, follow=True)

            assert b"payment method" in response.content.lower()

        def it_shows_error_when_limit_exceeded(client: Client):
            BillingSettingsFactory(default_tab_limit=Decimal("20.00"))
            user = User.objects.create_user(username="over_limit", password="pass")
            tab = TabFactory(member=user.member, tab_limit=None, stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, amount=Decimal("15.00"))
            client.login(username="over_limit", password="pass")

            response = client.post("/tab/", {"description": "Big item", "amount": "10.00"}, follow=True)

            assert b"tab limit" in response.content.lower()


def describe_tab_history():
    def it_requires_login(client: Client):
        response = client.get("/tab/history/")
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def it_renders_empty_history(client: Client):
        User.objects.create_user(username="empty_hist", password="pass")
        client.login(username="empty_hist", password="pass")

        response = client.get("/tab/history/")

        assert response.status_code == 200
        assert len(response.context["charges"]) == 0

    def it_handles_user_with_no_member(client: Client):
        post_save.disconnect(ensure_user_has_member, sender=User)
        try:
            user = User.objects.create_user(username="orphan2", password="pass")
            client.login(username="orphan2", password="pass")
            response = client.get("/tab/history/")
            assert response.status_code == 200
            assert list(response.context["charges"]) == []
        finally:
            post_save.connect(ensure_user_has_member, sender=User)

    def it_shows_past_charges(client: Client):
        user = User.objects.create_user(username="with_charges", password="pass")
        tab = TabFactory(member=user.member)
        TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED, amount=Decimal("50.00"))
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED, amount=Decimal("25.00"))
        client.login(username="with_charges", password="pass")

        response = client.get("/tab/history/")

        assert response.status_code == 200
        assert len(response.context["charges"]) == 2

    def it_excludes_pending_charges(client: Client):
        user = User.objects.create_user(username="pending_only", password="pass")
        tab = TabFactory(member=user.member)
        TabChargeFactory(tab=tab, status=TabCharge.Status.PENDING, amount=Decimal("10.00"))
        TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED, amount=Decimal("30.00"))
        client.login(username="pending_only", password="pass")

        response = client.get("/tab/history/")

        assert len(response.context["charges"]) == 1
