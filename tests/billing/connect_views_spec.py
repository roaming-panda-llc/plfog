"""BDD-style tests for Stripe Connect OAuth views."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client

from billing.models import StripeAccount
from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db


def _create_superuser(client: Client) -> User:
    user = User.objects.create_superuser(username="connect_admin", password="pass", email="admin@test.com")
    client.login(username="connect_admin", password="pass")
    return user


def describe_initiate_connect():
    def it_requires_staff(client: Client):
        response = client.get("/billing/connect/initiate/1/")
        assert response.status_code == 302

    def it_redirects_to_stripe(client: Client, settings):
        settings.STRIPE_CONNECT_CLIENT_ID = "ca_test_abc"
        _create_superuser(client)
        guild = GuildFactory()
        response = client.get(f"/billing/connect/initiate/{guild.pk}/")
        assert response.status_code == 302
        assert "connect.stripe.com" in response.url


def describe_connect_callback():
    @patch("billing.views.stripe_utils.complete_connect_oauth")
    def it_creates_stripe_account_on_success(mock_oauth, client: Client):
        mock_oauth.return_value = "acct_new_123"
        _create_superuser(client)
        guild = GuildFactory()
        response = client.get("/billing/connect/callback/", {"code": "ac_test_code", "state": str(guild.pk)})
        assert response.status_code == 302
        acct = StripeAccount.objects.get(guild=guild)
        assert acct.stripe_account_id == "acct_new_123"

    def it_handles_error_from_stripe(client: Client):
        _create_superuser(client)
        response = client.get("/billing/connect/callback/", {"error": "access_denied", "error_description": "Denied"})
        assert response.status_code == 302

    @patch("billing.views.stripe_utils.complete_connect_oauth")
    def it_updates_existing_stripe_account(mock_oauth, client: Client):
        mock_oauth.return_value = "acct_updated_456"
        _create_superuser(client)
        guild = GuildFactory()
        StripeAccount.objects.create(guild=guild, stripe_account_id="acct_old", display_name=guild.name)
        response = client.get("/billing/connect/callback/", {"code": "ac_test_code", "state": str(guild.pk)})
        assert response.status_code == 302
        acct = StripeAccount.objects.get(guild=guild)
        assert acct.stripe_account_id == "acct_updated_456"
