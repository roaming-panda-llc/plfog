"""Thin wrapper for all Stripe API calls. All Stripe interactions go through here."""

from __future__ import annotations

from typing import Any

import stripe
from django.conf import settings


def _get_stripe_client() -> stripe.StripeClient:
    """Get a Stripe client configured with the secret key."""
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


def create_customer(*, email: str, name: str, member_pk: int) -> str:
    """Create a Stripe customer and return the customer ID.

    Uses an idempotency key based on member_pk to prevent duplicate customers.
    """
    client = _get_stripe_client()
    customer = client.v1.customers.create(
        params={"email": email, "name": name, "metadata": {"member_pk": str(member_pk)}},
        options={"idempotency_key": f"create-customer-member-{member_pk}"},
    )
    return customer.id


def create_setup_intent(*, customer_id: str) -> dict[str, str]:
    """Create a Stripe SetupIntent for collecting a payment method.

    Returns dict with 'client_secret' and 'setup_intent_id'.
    Includes usage='off_session' for future off-session charges (SCA/3DS compliance).
    """
    client = _get_stripe_client()
    intent = client.v1.setup_intents.create(
        params={
            "customer": customer_id,
            "usage": "off_session",
            "payment_method_types": ["card"],
        },
    )
    return {"client_secret": intent.client_secret or "", "setup_intent_id": intent.id}


def retrieve_payment_method(*, payment_method_id: str) -> dict[str, Any]:
    """Retrieve a payment method's details from Stripe.

    Returns dict with 'id', 'brand', 'last4'.
    """
    client = _get_stripe_client()
    pm = client.v1.payment_methods.retrieve(payment_method_id)
    return {
        "id": pm.id,
        "brand": pm.card.brand if pm.card else "",
        "last4": pm.card.last4 if pm.card else "",
    }


def attach_payment_method(*, customer_id: str, payment_method_id: str) -> None:
    """Attach a payment method to a customer and set it as the default."""
    client = _get_stripe_client()
    client.v1.payment_methods.attach(
        payment_method_id,
        params={"customer": customer_id},
    )
    client.v1.customers.update(
        customer_id,
        params={"invoice_settings": {"default_payment_method": payment_method_id}},
    )


def detach_payment_method(*, payment_method_id: str) -> None:
    """Detach a payment method from its customer."""
    client = _get_stripe_client()
    client.v1.payment_methods.detach(payment_method_id)


def create_payment_intent(
    *,
    customer_id: str,
    payment_method_id: str,
    amount_cents: int,
    description: str,
    metadata: dict[str, str],
    idempotency_key: str,
) -> dict[str, Any]:
    """Create a Stripe PaymentIntent for an off-session charge.

    Returns dict with 'id', 'status', 'charge_id', 'receipt_url'.
    The idempotency_key is REQUIRED to prevent duplicate charges.
    """
    client = _get_stripe_client()
    intent = client.v1.payment_intents.create(
        params={
            "customer": customer_id,
            "payment_method": payment_method_id,
            "amount": amount_cents,
            "currency": "usd",
            "description": description,
            "metadata": metadata,
            "off_session": True,
            "confirm": True,
        },
        options={"idempotency_key": idempotency_key},
    )
    # Extract charge details if available
    charge_id = ""
    receipt_url = ""
    if intent.latest_charge:
        charge = client.v1.charges.retrieve(str(intent.latest_charge))
        charge_id = charge.id
        receipt_url = charge.receipt_url or ""

    return {
        "id": intent.id,
        "status": intent.status,
        "charge_id": charge_id,
        "receipt_url": receipt_url,
    }


def create_destination_payment_intent(
    *,
    customer_id: str,
    payment_method_id: str,
    amount_cents: int,
    description: str,
    metadata: dict[str, str],
    idempotency_key: str,
    destination_account_id: str,
    application_fee_cents: int | None = None,
) -> dict[str, Any]:
    """Create a Stripe Connect destination charge."""
    client = _get_stripe_client()
    params: dict[str, Any] = {
        "customer": customer_id,
        "payment_method": payment_method_id,
        "amount": amount_cents,
        "currency": "usd",
        "description": description,
        "metadata": metadata,
        "off_session": True,
        "confirm": True,
        "transfer_data": {"destination": destination_account_id},
    }
    if application_fee_cents is not None:
        params["application_fee_amount"] = application_fee_cents

    intent = client.v1.payment_intents.create(
        params=params,  # type: ignore[arg-type]  # Dynamic params dict for Connect destination charges
        options={"idempotency_key": idempotency_key},
    )
    charge_id = ""
    receipt_url = ""
    if intent.latest_charge:
        charge = client.v1.charges.retrieve(str(intent.latest_charge))
        charge_id = charge.id
        receipt_url = charge.receipt_url or ""
    return {"id": intent.id, "status": intent.status, "charge_id": charge_id, "receipt_url": receipt_url}


def get_connect_oauth_url(*, state: str) -> str:
    """Build the Stripe Connect OAuth URL for linking a Standard account."""
    client_id = settings.STRIPE_CONNECT_CLIENT_ID
    return (
        f"https://connect.stripe.com/oauth/authorize"
        f"?response_type=code&client_id={client_id}"
        f"&scope=read_write&state={state}&stripe_landing=login"
    )


def complete_connect_oauth(*, code: str) -> str:
    """Exchange a Connect OAuth authorization code for a connected account ID."""
    client = _get_stripe_client()
    response = client.v1.oauth.token(params={"grant_type": "authorization_code", "code": code})
    return response.stripe_user_id


def construct_webhook_event(*, payload: bytes, sig_header: str) -> stripe.Event:
    """Verify and construct a Stripe webhook event from the raw payload.

    Uses the raw request body to verify the Stripe signature.

    Raises:
        stripe.SignatureVerificationError: If the signature is invalid.
    """
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=settings.STRIPE_WEBHOOK_SECRET,
    )
