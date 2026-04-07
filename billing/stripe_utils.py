"""Thin wrapper for all Stripe API calls. All Stripe interactions go through here.

All platform-account Stripe credentials (used for Connect/OAuth-mode charges,
the global webhook endpoint, and the platform payment-method setup flow) live
in `BillingSettings` rows in the database — no environment variables. Direct-
keys mode reads its credentials from the per-guild `StripeAccount` row instead.
The only Stripe-related env var still in use is `STRIPE_FIELD_ENCRYPTION_KEY`,
which is the Fernet key that encrypts secrets at rest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from billing.models import BillingSettings, StripeAccount


def _billing_settings() -> BillingSettings:
    """Lazy import to avoid circular dependency between models and stripe_utils."""
    from billing.models import BillingSettings as _BS

    return _BS.load()


def _platform_secret_key() -> str:
    bs = _billing_settings()
    if not bs.connect_platform_secret_key:
        raise ImproperlyConfigured(
            "Stripe Connect platform secret key is not set. "
            "Configure it in the admin Payments dashboard → Settings tab."
        )
    return bs.connect_platform_secret_key


def _platform_webhook_secret() -> str:
    bs = _billing_settings()
    if not bs.connect_platform_webhook_secret:
        raise ImproperlyConfigured(
            "Stripe Connect platform webhook secret is not set. "
            "Configure it in the admin Payments dashboard → Settings tab."
        )
    return bs.connect_platform_webhook_secret


def _connect_client_id() -> str:
    bs = _billing_settings()
    if not bs.connect_client_id:
        raise ImproperlyConfigured(
            "Stripe Connect client ID is not set. Configure it in the admin Payments dashboard → Settings tab."
        )
    return bs.connect_client_id


def _get_stripe_client() -> stripe.StripeClient:
    """Get a Stripe client configured with the platform secret key (from DB)."""
    return stripe.StripeClient(_platform_secret_key())


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
    client_id = _connect_client_id()
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

    Uses the raw request body to verify the Stripe signature. The signing
    secret is read from BillingSettings (the global Connect platform secret).

    Raises:
        stripe.SignatureVerificationError: If the signature is invalid.
        ImproperlyConfigured: If the platform webhook secret is not set in BillingSettings.
    """
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=_platform_webhook_secret(),
    )


def construct_webhook_event_for_account(
    *,
    payload: bytes,
    sig_header: str,
    webhook_secret: str,
) -> stripe.Event:
    """Verify a webhook event using a per-account signing secret (direct-keys mode).

    Raises:
        stripe.SignatureVerificationError: If the signature is invalid.
        ValueError: If webhook_secret is empty.
    """
    if not webhook_secret:
        raise ValueError("webhook_secret is required to verify direct-keys webhook events.")
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=webhook_secret,
    )


def verify_account_credentials(secret_key: str) -> dict[str, Any]:
    """Make a test API call against the given secret key to verify it works.

    Calls accounts.retrieve("self") which works on any Stripe account
    (Standard, Express, Custom, or just a regular non-Connect account).

    Returns:
        dict with 'stripe_account_id', 'display_name', 'charges_enabled', 'country'.

    Raises:
        stripe.AuthenticationError: Invalid API key.
        stripe.StripeError: Other Stripe API failures.
    """
    client = stripe.StripeClient(secret_key)
    account = client.v1.accounts.retrieve("self")
    display_name = ""
    if account.business_profile and account.business_profile.name:
        display_name = account.business_profile.name
    return {
        "stripe_account_id": account.id,
        "display_name": display_name or account.id,
        "charges_enabled": bool(account.charges_enabled),
        "country": account.country or "",
    }


def create_checkout_session_for_account(
    *,
    stripe_account: StripeAccount,
    amount_cents: int,
    description: str,
    metadata: dict[str, str],
    idempotency_key: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> dict[str, Any]:
    """Create a hosted Stripe Checkout session on a direct-keys guild's own account.

    No platform fee, no transfer_data — money settles in the guild's balance directly.
    The returned `url` is what the member opens to pay.
    """
    client = stripe_account.get_stripe_client()
    site_url = getattr(settings, "SITE_URL", "https://pastlives.plaza.codes").rstrip("/")
    session = client.v1.checkout.sessions.create(
        params={
            "mode": "payment",
            "line_items": [
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": description},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            "metadata": metadata,
            "payment_intent_data": {"metadata": metadata},
            "success_url": success_url or f"{site_url}/billing/checkout/success/",
            "cancel_url": cancel_url or f"{site_url}/billing/checkout/cancel/",
        },
        options={"idempotency_key": idempotency_key},
    )
    return {"id": session.id, "url": session.url or ""}
