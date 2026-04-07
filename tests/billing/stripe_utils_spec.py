"""BDD-style tests for billing.stripe_utils — all Stripe API calls mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import stripe

from billing import stripe_utils

pytestmark = pytest.mark.django_db


def _mock_client() -> MagicMock:
    """Create a mock StripeClient with common nested attributes."""
    client = MagicMock()
    return client


def describe_get_stripe_client():
    def it_returns_a_stripe_client():
        client = stripe_utils._get_stripe_client()
        assert isinstance(client, stripe.StripeClient)


def describe_create_customer():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_returns_customer_id(mock_get_client):
        client = _mock_client()
        client.v1.customers.create.return_value = MagicMock(id="cus_test_123")
        mock_get_client.return_value = client

        result = stripe_utils.create_customer(email="test@example.com", name="Jane", member_pk=42)

        assert result == "cus_test_123"
        client.v1.customers.create.assert_called_once()
        call_kwargs = client.v1.customers.create.call_args
        assert call_kwargs.kwargs["params"]["email"] == "test@example.com"
        assert call_kwargs.kwargs["options"]["idempotency_key"] == "create-customer-member-42"


def describe_create_setup_intent():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_returns_client_secret_and_id(mock_get_client):
        client = _mock_client()
        client.v1.setup_intents.create.return_value = MagicMock(client_secret="seti_secret_123", id="seti_123")
        mock_get_client.return_value = client

        result = stripe_utils.create_setup_intent(customer_id="cus_test_123")

        assert result == {"client_secret": "seti_secret_123", "setup_intent_id": "seti_123"}
        call_kwargs = client.v1.setup_intents.create.call_args
        assert call_kwargs.kwargs["params"]["usage"] == "off_session"


def describe_retrieve_payment_method():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_returns_card_details(mock_get_client):
        client = _mock_client()
        pm = MagicMock()
        pm.id = "pm_test_456"
        pm.card.brand = "visa"
        pm.card.last4 = "4242"
        client.v1.payment_methods.retrieve.return_value = pm
        mock_get_client.return_value = client

        result = stripe_utils.retrieve_payment_method(payment_method_id="pm_test_456")

        assert result == {"id": "pm_test_456", "brand": "visa", "last4": "4242"}

    @patch("billing.stripe_utils._get_stripe_client")
    def it_handles_no_card(mock_get_client):
        client = _mock_client()
        pm = MagicMock()
        pm.id = "pm_test_789"
        pm.card = None
        client.v1.payment_methods.retrieve.return_value = pm
        mock_get_client.return_value = client

        result = stripe_utils.retrieve_payment_method(payment_method_id="pm_test_789")

        assert result == {"id": "pm_test_789", "brand": "", "last4": ""}


def describe_attach_payment_method():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_attaches_and_sets_default(mock_get_client):
        client = _mock_client()
        mock_get_client.return_value = client

        stripe_utils.attach_payment_method(customer_id="cus_123", payment_method_id="pm_456")

        client.v1.payment_methods.attach.assert_called_once_with("pm_456", params={"customer": "cus_123"})
        client.v1.customers.update.assert_called_once_with(
            "cus_123", params={"invoice_settings": {"default_payment_method": "pm_456"}}
        )


def describe_detach_payment_method():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_detaches(mock_get_client):
        client = _mock_client()
        mock_get_client.return_value = client

        stripe_utils.detach_payment_method(payment_method_id="pm_456")

        client.v1.payment_methods.detach.assert_called_once_with("pm_456")


def describe_create_payment_intent():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_creates_intent_and_returns_details(mock_get_client):
        client = _mock_client()
        intent = MagicMock()
        intent.id = "pi_test_789"
        intent.status = "succeeded"
        intent.latest_charge = "ch_test_001"
        client.v1.payment_intents.create.return_value = intent

        charge = MagicMock()
        charge.id = "ch_test_001"
        charge.receipt_url = "https://stripe.com/receipt/123"
        client.v1.charges.retrieve.return_value = charge
        mock_get_client.return_value = client

        result = stripe_utils.create_payment_intent(
            customer_id="cus_123",
            payment_method_id="pm_456",
            amount_cents=5000,
            description="Tab charge",
            metadata={"tab_id": "1"},
            idempotency_key="test-key-1",
        )

        assert result == {
            "id": "pi_test_789",
            "status": "succeeded",
            "charge_id": "ch_test_001",
            "receipt_url": "https://stripe.com/receipt/123",
        }
        call_kwargs = client.v1.payment_intents.create.call_args
        assert call_kwargs.kwargs["params"]["off_session"] is True
        assert call_kwargs.kwargs["options"]["idempotency_key"] == "test-key-1"

    @patch("billing.stripe_utils._get_stripe_client")
    def it_handles_no_latest_charge(mock_get_client):
        client = _mock_client()
        intent = MagicMock()
        intent.id = "pi_test_no_charge"
        intent.status = "requires_action"
        intent.latest_charge = None
        client.v1.payment_intents.create.return_value = intent
        mock_get_client.return_value = client

        result = stripe_utils.create_payment_intent(
            customer_id="cus_123",
            payment_method_id="pm_456",
            amount_cents=5000,
            description="Tab charge",
            metadata={},
            idempotency_key="test-key-2",
        )

        assert result["charge_id"] == ""
        assert result["receipt_url"] == ""


def describe_construct_webhook_event():
    @patch("billing.stripe_utils.stripe.Webhook.construct_event")
    def it_delegates_to_stripe_sdk(mock_construct):
        mock_event = MagicMock()
        mock_construct.return_value = mock_event

        result = stripe_utils.construct_webhook_event(payload=b"raw_body", sig_header="sig_123")

        assert result == mock_event
        mock_construct.assert_called_once_with(
            payload=b"raw_body",
            sig_header="sig_123",
            secret="whsec_fake_for_testing",
        )


def describe_create_destination_payment_intent():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_creates_destination_charge_with_fee(mock_get_client):
        client = _mock_client()
        intent = MagicMock()
        intent.id = "pi_dest_123"
        intent.status = "succeeded"
        intent.latest_charge = "ch_dest_001"
        client.v1.payment_intents.create.return_value = intent
        charge = MagicMock()
        charge.id = "ch_dest_001"
        charge.receipt_url = "https://stripe.com/receipt/dest"
        client.v1.charges.retrieve.return_value = charge
        mock_get_client.return_value = client

        result = stripe_utils.create_destination_payment_intent(
            customer_id="cus_123",
            payment_method_id="pm_456",
            amount_cents=1200,
            description="Tab charge",
            metadata={"tab_id": "1"},
            idempotency_key="key-1",
            destination_account_id="acct_guild_001",
            application_fee_cents=180,
        )
        assert result["id"] == "pi_dest_123"
        call_kwargs = client.v1.payment_intents.create.call_args.kwargs
        assert call_kwargs["params"]["transfer_data"] == {"destination": "acct_guild_001"}
        assert call_kwargs["params"]["application_fee_amount"] == 180

    @patch("billing.stripe_utils._get_stripe_client")
    def it_omits_fee_when_none(mock_get_client):
        client = _mock_client()
        intent = MagicMock()
        intent.id = "pi_dest_no_fee"
        intent.status = "succeeded"
        intent.latest_charge = None
        client.v1.payment_intents.create.return_value = intent
        mock_get_client.return_value = client

        stripe_utils.create_destination_payment_intent(
            customer_id="cus_123",
            payment_method_id="pm_456",
            amount_cents=800,
            description="Tab",
            metadata={},
            idempotency_key="key-2",
            destination_account_id="acct_guild_002",
            application_fee_cents=None,
        )
        call_kwargs = client.v1.payment_intents.create.call_args.kwargs
        assert "application_fee_amount" not in call_kwargs["params"]


def describe_get_connect_oauth_url():
    def it_builds_url_with_client_id(settings):
        settings.STRIPE_CONNECT_CLIENT_ID = "ca_test_123"
        url = stripe_utils.get_connect_oauth_url(state="guild-42")
        assert "ca_test_123" in url
        assert "guild-42" in url
        assert "stripe_landing=login" in url


def describe_complete_connect_oauth():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_exchanges_code_for_account_id(mock_get_client):
        client = _mock_client()
        client.v1.oauth.token.return_value = MagicMock(stripe_user_id="acct_connected_123")
        mock_get_client.return_value = client
        result = stripe_utils.complete_connect_oauth(code="ac_test_code")
        assert result == "acct_connected_123"


def describe_construct_webhook_event_for_account():
    def it_raises_when_secret_is_empty():
        with pytest.raises(ValueError, match="webhook_secret is required"):
            stripe_utils.construct_webhook_event_for_account(payload=b"{}", sig_header="t=1,v1=foo", webhook_secret="")

    @patch("billing.stripe_utils.stripe.Webhook.construct_event")
    def it_passes_per_account_secret_to_stripe_sdk(mock_construct):
        mock_event = MagicMock()
        mock_construct.return_value = mock_event
        result = stripe_utils.construct_webhook_event_for_account(
            payload=b"{}", sig_header="t=1,v1=foo", webhook_secret="whsec_perguild"
        )
        assert result == mock_event
        mock_construct.assert_called_once_with(payload=b"{}", sig_header="t=1,v1=foo", secret="whsec_perguild")


def describe_verify_account_credentials():
    @patch("billing.stripe_utils.stripe.StripeClient")
    def it_returns_account_metadata(mock_stripe_client_cls):
        mock_account = MagicMock(
            id="acct_verified_001",
            charges_enabled=True,
            country="US",
        )
        mock_account.business_profile.name = "Ceramics Guild"
        client = MagicMock()
        client.v1.accounts.retrieve.return_value = mock_account
        mock_stripe_client_cls.return_value = client

        result = stripe_utils.verify_account_credentials("sk_test_real")
        assert result["stripe_account_id"] == "acct_verified_001"
        assert result["display_name"] == "Ceramics Guild"
        assert result["charges_enabled"] is True
        assert result["country"] == "US"
        client.v1.accounts.retrieve.assert_called_once_with("self")

    @patch("billing.stripe_utils.stripe.StripeClient")
    def it_falls_back_to_account_id_when_no_business_profile_name(mock_stripe_client_cls):
        mock_account = MagicMock(id="acct_no_name", charges_enabled=False, country="")
        mock_account.business_profile = None
        client = MagicMock()
        client.v1.accounts.retrieve.return_value = mock_account
        mock_stripe_client_cls.return_value = client

        result = stripe_utils.verify_account_credentials("sk_test_real")
        assert result["display_name"] == "acct_no_name"
        assert result["charges_enabled"] is False
        assert result["country"] == ""


def describe_create_checkout_session_for_account():
    def it_creates_a_checkout_session_via_account_client(db):
        from tests.billing.factories import DirectKeysStripeAccountFactory

        account = DirectKeysStripeAccountFactory(direct_secret_key="sk_test_clayguild")
        mock_session = MagicMock(id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")
        mock_client = MagicMock()
        mock_client.v1.checkout.sessions.create.return_value = mock_session

        with patch.object(account, "get_stripe_client", return_value=mock_client):
            result = stripe_utils.create_checkout_session_for_account(
                stripe_account=account,
                amount_cents=1500,
                description="Clay (3 lbs)",
                metadata={"tab_id": "1"},
                idempotency_key="charge-1-attempt-1",
            )
        assert result == {"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/cs_test_123"}
        call = mock_client.v1.checkout.sessions.create.call_args
        params = call.kwargs["params"]
        assert params["mode"] == "payment"
        assert params["line_items"][0]["price_data"]["unit_amount"] == 1500
        assert params["line_items"][0]["price_data"]["product_data"]["name"] == "Clay (3 lbs)"
        assert params["metadata"] == {"tab_id": "1"}
        assert call.kwargs["options"]["idempotency_key"] == "charge-1-attempt-1"
