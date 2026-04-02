"""Stripe webhook event handlers. Each handler is idempotent."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from billing.models import Tab, TabCharge
from billing.notifications import notify_admin_charge_failed, send_receipt

logger = logging.getLogger(__name__)


def handle_setup_intent_succeeded(event: dict[str, Any]) -> None:
    """Attach the payment method from a completed SetupIntent to the Tab."""
    setup_intent = event["data"]["object"]
    customer_id = setup_intent["customer"]
    payment_method_id = setup_intent["payment_method"]

    try:
        tab = Tab.objects.get(stripe_customer_id=customer_id)
    except Tab.DoesNotExist:
        logger.warning("setup_intent.succeeded: no tab for customer %s", customer_id)
        return

    # Idempotent: skip if already set to this payment method
    if tab.stripe_payment_method_id == payment_method_id:
        return

    from billing.stripe_utils import retrieve_payment_method

    pm = retrieve_payment_method(payment_method_id=payment_method_id)
    tab.stripe_payment_method_id = pm["id"]
    tab.payment_method_last4 = pm["last4"]
    tab.payment_method_brand = pm["brand"]
    tab.save(
        update_fields=[
            "stripe_payment_method_id",
            "payment_method_last4",
            "payment_method_brand",
            "updated_at",
        ]
    )


def handle_payment_intent_succeeded(event: dict[str, Any]) -> None:
    """Mark TabCharge as SUCCEEDED — this is the canonical success path."""
    payment_intent = event["data"]["object"]
    pi_id = payment_intent["id"]

    try:
        charge = TabCharge.objects.get(stripe_payment_intent_id=pi_id)
    except TabCharge.DoesNotExist:
        logger.warning("payment_intent.succeeded: no charge for PI %s", pi_id)
        return

    # Idempotent: skip if already succeeded
    if charge.status == TabCharge.Status.SUCCEEDED:
        return

    charge.status = TabCharge.Status.SUCCEEDED
    charge.charged_at = timezone.now()

    # Extract receipt URL from charges
    charges_data = payment_intent.get("charges", {}).get("data", [])
    if charges_data:
        charge.stripe_charge_id = charges_data[0].get("id", "")
        charge.stripe_receipt_url = charges_data[0].get("receipt_url", "")

    charge.save()
    send_receipt(charge)


def handle_payment_intent_failed(event: dict[str, Any]) -> None:
    """Update TabCharge on payment failure."""
    payment_intent = event["data"]["object"]
    pi_id = payment_intent["id"]

    try:
        charge = TabCharge.objects.get(stripe_payment_intent_id=pi_id)
    except TabCharge.DoesNotExist:
        logger.warning("payment_intent.payment_failed: no charge for PI %s", pi_id)
        return

    # Idempotent: skip if already failed
    if charge.status == TabCharge.Status.FAILED:
        return

    last_error = payment_intent.get("last_payment_error", {})
    charge.status = TabCharge.Status.FAILED
    charge.failure_reason = last_error.get("message", "Payment failed")
    charge.save(update_fields=["status", "failure_reason"])
    notify_admin_charge_failed(charge)


def handle_payment_method_detached(event: dict[str, Any]) -> None:
    """Clear payment method on Tab when card is detached in Stripe."""
    pm = event["data"]["object"]
    pm_id = pm["id"]

    try:
        tab = Tab.objects.get(stripe_payment_method_id=pm_id)
    except Tab.DoesNotExist:
        return  # Not our payment method

    tab.stripe_payment_method_id = ""
    tab.payment_method_last4 = ""
    tab.payment_method_brand = ""
    tab.save(
        update_fields=[
            "stripe_payment_method_id",
            "payment_method_last4",
            "payment_method_brand",
            "updated_at",
        ]
    )


def handle_payment_method_updated(event: dict[str, Any]) -> None:
    """Update card details on Tab when Stripe auto-updates a card."""
    pm = event["data"]["object"]
    pm_id = pm["id"]

    try:
        tab = Tab.objects.get(stripe_payment_method_id=pm_id)
    except Tab.DoesNotExist:
        return

    card = pm.get("card", {})
    tab.payment_method_last4 = card.get("last4", tab.payment_method_last4)
    tab.payment_method_brand = card.get("brand", tab.payment_method_brand)
    tab.save(update_fields=["payment_method_last4", "payment_method_brand", "updated_at"])


def handle_charge_dispute_created(event: dict[str, Any]) -> None:
    """Log and notify admins about a chargeback."""
    dispute = event["data"]["object"]
    charge_id = dispute.get("charge", "")
    logger.warning("Charge dispute created for charge %s. Amount: %s", charge_id, dispute.get("amount", "unknown"))
