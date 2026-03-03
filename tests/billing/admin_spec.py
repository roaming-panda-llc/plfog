"""Admin changelist HTTP tests for the billing app."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from tests.billing.factories import InvoiceFactory, OrderFactory, PayoutFactory, RevenueSplitFactory

User = get_user_model()


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="billing-admin-test",
        password="billing-admin-pw",
        email="billing-admin@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def describe_admin_revenue_split_views():
    def it_loads_changelist(admin_client):
        RevenueSplitFactory(name="Admin View Split")
        resp = admin_client.get("/admin/billing/revenuesplit/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_order_views():
    def it_loads_changelist(admin_client):
        OrderFactory()
        resp = admin_client.get("/admin/billing/order/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_invoice_views():
    def it_loads_changelist(admin_client):
        InvoiceFactory()
        resp = admin_client.get("/admin/billing/invoice/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_payout_views():
    def it_loads_changelist(admin_client):
        PayoutFactory()
        resp = admin_client.get("/admin/billing/payout/")
        assert resp.status_code == 200
