"""Admin changelist tests for the tools app."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from tests.tools.factories import DocumentFactory, RentableFactory, RentalFactory, ToolFactory, ToolReservationFactory

User = get_user_model()


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="tools-admin-test",
        password="tools-admin-pw",
        email="tools-admin@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def describe_tool_admin_changelist():
    def it_loads_with_200(admin_client):
        ToolFactory(name="Changelist Tool")
        resp = admin_client.get("/admin/tools/tool/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_tool_reservation_admin_changelist():
    def it_loads_with_200(admin_client):
        ToolReservationFactory()
        resp = admin_client.get("/admin/tools/toolreservation/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_rentable_admin_changelist():
    def it_loads_with_200(admin_client):
        RentableFactory()
        resp = admin_client.get("/admin/tools/rentable/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_rental_admin_changelist():
    def it_loads_with_200(admin_client):
        RentalFactory()
        resp = admin_client.get("/admin/tools/rental/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_document_admin_changelist():
    def it_loads_with_200(admin_client):
        DocumentFactory()
        resp = admin_client.get("/admin/tools/document/")
        assert resp.status_code == 200
