"""BDD specs for the void_tab_entry view."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from tests.billing.factories import TabEntryFactory, TabFactory

pytestmark = pytest.mark.django_db


def describe_void_tab_entry():
    @pytest.fixture()
    def setup(client: Client):
        user = User.objects.create_user(username="member1", password="pass")
        tab = TabFactory(member=user.member)
        entry = TabEntryFactory(tab=tab, description="Laser time", amount=Decimal("10.00"))
        client.login(username="member1", password="pass")
        return {"user": user, "tab": tab, "entry": entry}

    def it_voids_a_pending_entry(client: Client, setup):
        entry = setup["entry"]
        response = client.post(f"/tab/void/{entry.pk}/")
        assert response.status_code == 204
        entry.refresh_from_db()
        assert entry.voided_at is not None
        assert entry.voided_reason == "Removed by member"

    def it_returns_toast_on_success(client: Client, setup):
        entry = setup["entry"]
        response = client.post(f"/tab/void/{entry.pk}/")
        assert response.status_code == 204
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["message"] == "Charge removed."
        assert payload["showToast"]["type"] == "success"

    def it_rejects_void_of_another_users_entry(client: Client, setup):
        other_user = User.objects.create_user(username="other", password="pass")
        other_tab = TabFactory(member=other_user.member)
        other_entry = TabEntryFactory(tab=other_tab, amount=Decimal("5.00"))

        response = client.post(f"/tab/void/{other_entry.pk}/")
        assert response.status_code == 404

    def it_requires_login(client: Client, setup):
        client.logout()
        entry = setup["entry"]
        response = client.post(f"/tab/void/{entry.pk}/")
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def it_returns_error_when_already_voided(client: Client, setup):
        entry = setup["entry"]
        entry.void(user=setup["user"], reason="first void")

        response = client.post(f"/tab/void/{entry.pk}/")
        assert response.status_code == 400
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["type"] == "error"
