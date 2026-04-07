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

    def it_redirects_on_missing_code(client: Client):
        _create_superuser(client)
        response = client.get("/billing/connect/callback/", {"state": "1"})
        assert response.status_code == 302

    def it_redirects_on_missing_state(client: Client):
        _create_superuser(client)
        response = client.get("/billing/connect/callback/", {"code": "ac_test_code"})
        assert response.status_code == 302


def describe_billing_test_direct_keys():
    def it_requires_staff(client: Client):
        response = client.post("/billing/admin/direct-keys/test/")
        assert response.status_code == 302

    def it_returns_error_when_secret_key_missing(client: Client):
        _create_superuser(client)
        response = client.post("/billing/admin/direct-keys/test/", {"secret_key": ""})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def it_returns_error_for_unrecognized_prefix(client: Client):
        _create_superuser(client)
        response = client.post("/billing/admin/direct-keys/test/", {"secret_key": "garbage"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "sk_test_" in data["error"]

    @patch("billing.views.stripe_utils.verify_account_credentials")
    def it_returns_account_metadata_on_success(mock_verify, client: Client):
        mock_verify.return_value = {
            "stripe_account_id": "acct_verified_001",
            "display_name": "Ceramics Guild",
            "charges_enabled": True,
            "country": "US",
        }
        _create_superuser(client)
        response = client.post("/billing/admin/direct-keys/test/", {"secret_key": "sk_test_real"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["stripe_account_id"] == "acct_verified_001"
        assert data["display_name"] == "Ceramics Guild"

    @patch("billing.views.stripe_utils.verify_account_credentials", side_effect=Exception("invalid key"))
    def it_returns_error_on_stripe_failure(mock_verify, client: Client):
        _create_superuser(client)
        response = client.post("/billing/admin/direct-keys/test/", {"secret_key": "sk_test_bogus"})
        data = response.json()
        assert data["ok"] is False
        assert "invalid key" in data["error"]


def describe_billing_save_direct_keys():
    def it_requires_staff(client: Client):
        response = client.post("/billing/admin/direct-keys/save/")
        assert response.status_code == 302

    def it_redirects_on_missing_guild(client: Client):
        _create_superuser(client)
        response = client.post("/billing/admin/direct-keys/save/", {})
        assert response.status_code == 302

    def it_redirects_on_missing_keys(client: Client):
        _create_superuser(client)
        guild = GuildFactory()
        response = client.post(
            "/billing/admin/direct-keys/save/",
            {"guild_id": str(guild.pk), "secret_key": "", "publishable_key": ""},
        )
        assert response.status_code == 302
        assert not StripeAccount.objects.filter(guild=guild).exists()

    @patch("billing.views.stripe_utils.verify_account_credentials")
    def it_creates_a_direct_keys_stripe_account(mock_verify, client: Client):
        mock_verify.return_value = {
            "stripe_account_id": "acct_save_001",
            "display_name": "Wood Guild",
            "charges_enabled": True,
            "country": "US",
        }
        _create_superuser(client)
        guild = GuildFactory(name="Wood")
        response = client.post(
            "/billing/admin/direct-keys/save/",
            {
                "guild_id": str(guild.pk),
                "secret_key": "sk_test_save",
                "publishable_key": "pk_test_save",
                "webhook_secret": "whsec_save",
            },
        )
        assert response.status_code == 302
        acct = StripeAccount.objects.get(guild=guild)
        assert acct.auth_mode == StripeAccount.AuthMode.DIRECT_KEYS
        assert acct.stripe_account_id == "acct_save_001"
        assert acct.direct_secret_key == "sk_test_save"
        assert acct.direct_publishable_key == "pk_test_save"
        assert acct.direct_webhook_secret == "whsec_save"

    @patch("billing.views.stripe_utils.verify_account_credentials", side_effect=Exception("bad key"))
    def it_redirects_on_stripe_verification_failure(mock_verify, client: Client):
        _create_superuser(client)
        guild = GuildFactory()
        response = client.post(
            "/billing/admin/direct-keys/save/",
            {
                "guild_id": str(guild.pk),
                "secret_key": "sk_test_bad",
                "publishable_key": "pk_test_bad",
            },
        )
        assert response.status_code == 302
        assert not StripeAccount.objects.filter(guild=guild).exists()

    @patch("billing.views.stripe_utils.verify_account_credentials")
    def it_redirects_on_unknown_guild(mock_verify, client: Client):
        mock_verify.return_value = {
            "stripe_account_id": "acct_x",
            "display_name": "X",
            "charges_enabled": True,
            "country": "",
        }
        _create_superuser(client)
        response = client.post(
            "/billing/admin/direct-keys/save/",
            {
                "guild_id": "9999999",
                "secret_key": "sk_test_x",
                "publishable_key": "pk_test_x",
            },
        )
        assert response.status_code == 302


def describe_stripe_webhook_for_guild():
    def it_returns_404_when_no_account_exists(client: Client):
        response = client.post(
            "/billing/webhooks/stripe/guild/9999/",
            data=b"{}",
            content_type="application/json",
        )
        assert response.status_code == 404

    def it_returns_400_when_webhook_secret_is_missing(client: Client):
        from tests.billing.factories import DirectKeysStripeAccountFactory

        guild = GuildFactory()
        DirectKeysStripeAccountFactory(guild=guild, direct_webhook_secret="")
        response = client.post(
            f"/billing/webhooks/stripe/guild/{guild.pk}/",
            data=b"{}",
            content_type="application/json",
        )
        assert response.status_code == 400

    @patch("billing.views.stripe_utils.construct_webhook_event_for_account", side_effect=ValueError("bad sig"))
    def it_returns_400_on_signature_failure(mock_construct, client: Client):
        from tests.billing.factories import DirectKeysStripeAccountFactory

        guild = GuildFactory()
        DirectKeysStripeAccountFactory(guild=guild, direct_webhook_secret="whsec_test")
        response = client.post(
            f"/billing/webhooks/stripe/guild/{guild.pk}/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=foo",
        )
        assert response.status_code == 400

    @patch("billing.views.stripe_utils.construct_webhook_event_for_account")
    def it_dispatches_to_handler_on_success(mock_construct, client: Client):
        from unittest.mock import MagicMock
        from tests.billing.factories import DirectKeysStripeAccountFactory

        guild = GuildFactory()
        DirectKeysStripeAccountFactory(guild=guild, direct_webhook_secret="whsec_ok")
        event = MagicMock()
        event.type = "payment_intent.succeeded"
        event.to_dict.return_value = {"type": "payment_intent.succeeded", "data": {"object": {}}}
        mock_construct.return_value = event

        with patch("billing.views._WEBHOOK_HANDLERS") as mock_handlers:
            handler = MagicMock()
            mock_handlers.get.return_value = handler
            response = client.post(
                f"/billing/webhooks/stripe/guild/{guild.pk}/",
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=foo",
            )
        assert response.status_code == 200
        handler.assert_called_once()

    @patch("billing.views.stripe_utils.construct_webhook_event_for_account")
    def it_returns_200_for_unhandled_event_type(mock_construct, client: Client):
        from unittest.mock import MagicMock
        from tests.billing.factories import DirectKeysStripeAccountFactory

        guild = GuildFactory()
        DirectKeysStripeAccountFactory(guild=guild, direct_webhook_secret="whsec_ok")
        event = MagicMock()
        event.type = "some.unhandled.event"
        event.to_dict.return_value = {}
        mock_construct.return_value = event

        response = client.post(
            f"/billing/webhooks/stripe/guild/{guild.pk}/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=foo",
        )
        assert response.status_code == 200
