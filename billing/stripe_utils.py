from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import stripe
from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from datetime import date

    from django.contrib.auth.models import User
    from django.db.models import QuerySet

    from billing.models import Invoice, Order, Payout

logger = logging.getLogger(__name__)


def get_stripe_key() -> str:
    """Return the appropriate Stripe secret key based on STRIPE_LIVE_MODE."""
    if getattr(settings, "STRIPE_LIVE_MODE", False):
        return getattr(settings, "STRIPE_LIVE_SECRET_KEY", "")
    return getattr(settings, "STRIPE_TEST_SECRET_KEY", "")


def create_invoice_for_user(user: User, orders: QuerySet[Order]) -> Invoice | None:
    """Create a Stripe invoice for a user's tab orders.

    Returns the Invoice model instance if successful, None if no API key configured.
    """
    from billing.models import Invoice

    api_key = get_stripe_key()
    if not api_key:
        logger.warning("No Stripe API key configured — creating local invoice only")
        return _create_local_invoice(user, orders)

    try:
        stripe.api_key = api_key
        customers = stripe.Customer.list(email=user.email, limit=1)
        if customers.data:
            customer = customers.data[0]
        else:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.get_full_name() or user.username,
            )

        for order in orders:
            stripe.InvoiceItem.create(
                customer=customer.id,
                amount=order.amount,
                currency="usd",
                description=order.description,
            )

        stripe_invoice = stripe.Invoice.create(
            customer=customer.id,
            auto_advance=True,
        )
        stripe.Invoice.finalize_invoice(stripe_invoice.id)

        total_amount = sum(o.amount for o in orders)
        line_items = [{"description": o.description, "amount": o.amount} for o in orders]

        invoice = Invoice.objects.create(
            user=user,
            stripe_invoice_id=stripe_invoice.id,
            amount_due=total_amount,
            status="open",
            line_items=line_items,
            pdf_url=stripe_invoice.invoice_pdf or "",
            issued_at=timezone.now(),
        )
        return invoice

    except stripe.StripeError:
        logger.exception("Stripe error creating invoice for user %s", user.pk)
        return None


def _create_local_invoice(user: User, orders: QuerySet[Order]) -> Invoice:
    """Create a local-only invoice when no Stripe key is configured."""
    from billing.models import Invoice

    total_amount = sum(o.amount for o in orders)
    line_items = [{"description": o.description, "amount": o.amount} for o in orders]

    return Invoice.objects.create(
        user=user,
        amount_due=total_amount,
        status="open",
        line_items=line_items,
        issued_at=timezone.now(),
    )


def process_payout_report(period_start: date, period_end: date) -> list[Payout]:
    """Generate payout records from paid invoices in the period.

    Iterates through paid orders in the period, groups by revenue split entities,
    and creates Payout records.
    """
    from billing.models import Order, Payout

    orders = Order.objects.filter(
        status=Order.Status.PAID,
        issued_at__date__gte=period_start,
        issued_at__date__lte=period_end,
        revenue_split__isnull=False,
    ).select_related("revenue_split")

    payouts: dict[tuple[str, int], int] = {}

    for order in orders:
        if not order.revenue_split:  # pragma: no cover
            continue
        for split in order.revenue_split.splits:
            entity_type = split.get("entity_type", "org")
            entity_id = split.get("entity_id", 0)
            percentage = split.get("percentage", 0)
            amount = int(order.amount * percentage / 100)
            key = (entity_type, entity_id)
            payouts[key] = payouts.get(key, 0) + amount

    created_payouts = []
    for (payee_type, payee_id), amount in payouts.items():
        payout = Payout.objects.create(
            payee_type=payee_type,
            payee_id=payee_id,
            amount=amount,
            status=Payout.Status.PENDING,
            period_start=period_start,
            period_end=period_end,
        )
        created_payouts.append(payout)

    return created_payouts
