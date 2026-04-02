"""BDD-style tests for billing admin dashboard and add-entry views."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from billing.models import Tab, TabCharge
from tests.billing.factories import TabChargeFactory, TabEntryFactory, TabFactory
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
