"""Tests for billing models."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError

from billing.models import Invoice, Order, Payout, RevenueSplit
from tests.billing.factories import InvoiceFactory, OrderFactory, PayoutFactory, RevenueSplitFactory
from tests.core.factories import UserFactory


# ---------------------------------------------------------------------------
# RevenueSplit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_revenue_split():
    def it_has_str_representation():
        split = RevenueSplitFactory(name="50/50 House Split")
        assert str(split) == "50/50 House Split"

    def it_stores_splits_json():
        splits_data = [
            {"entity_type": "org", "entity_id": 1, "percentage": 60},
            {"entity_type": "guild", "entity_id": 2, "percentage": 40},
        ]
        split = RevenueSplitFactory(splits=splits_data)
        split.refresh_from_db()
        assert split.splits == splits_data

    def it_enforces_unique_name():
        RevenueSplitFactory(name="Unique Split")
        with pytest.raises(IntegrityError):
            RevenueSplitFactory(name="Unique Split")

    def it_defaults_splits_to_empty_list():
        split = RevenueSplit.objects.create(name="Empty Split")
        split.refresh_from_db()
        assert split.splits == []

    def it_stores_notes():
        split = RevenueSplitFactory(notes="60% to org, 40% to guild")
        split.refresh_from_db()
        assert split.notes == "60% to org, 40% to guild"

    def it_allows_blank_notes():
        split = RevenueSplitFactory(notes="")
        assert split.notes == ""


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_order():
    def it_has_str_representation():
        order = OrderFactory(description="Monthly dues", amount=15000)
        assert str(order) == f"Order #{order.pk} - Monthly dues ($150.00)"

    def it_is_on_tab_when_status_is_on_tab():
        order = OrderFactory(status="on_tab")
        assert order.is_on_tab is True

    def it_is_not_on_tab_when_status_is_paid():
        order = OrderFactory(status="paid")
        assert order.is_on_tab is False

    def it_is_paid_when_status_is_paid():
        order = OrderFactory(status="paid")
        assert order.is_paid is True

    def it_is_not_paid_when_status_is_on_tab():
        order = OrderFactory(status="on_tab")
        assert order.is_paid is False

    def it_is_failed_when_status_is_failed():
        order = OrderFactory(status="failed")
        assert order.is_failed is True

    def it_is_not_failed_when_status_is_paid():
        order = OrderFactory(status="paid")
        assert order.is_failed is False

    def it_formats_amount_in_dollars():
        order = OrderFactory(amount=7550)
        assert order.formatted_amount == "$75.50"

    def it_belongs_to_user():
        user = UserFactory()
        order = OrderFactory(user=user)
        assert order.user == user

    def it_belongs_to_revenue_split():
        split = RevenueSplitFactory(name="Order Split")
        order = OrderFactory(revenue_split=split)
        assert order.revenue_split == split

    def it_supports_generic_fk_orderable():
        """Orders can link to any model via the GenericFK orderable field."""
        split = RevenueSplitFactory(name="Generic FK Target")
        ct = ContentType.objects.get_for_model(RevenueSplit)
        order = OrderFactory(content_type=ct, object_id=split.pk)
        order.refresh_from_db()
        assert order.content_type == ct
        assert order.object_id == split.pk
        assert order.orderable == split

    def it_defaults_status_to_on_tab():
        user = UserFactory()
        order = Order.objects.create(user=user, description="Direct create", amount=1000)
        assert order.status == Order.Status.ON_TAB


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_invoice():
    def it_has_str_representation():
        invoice = InvoiceFactory(amount_due=9999, status="open")
        assert str(invoice) == f"Invoice #{invoice.pk} - $99.99 (open)"

    def it_is_paid_when_status_is_paid():
        invoice = InvoiceFactory(status="paid")
        assert invoice.is_paid is True

    def it_is_not_paid_when_status_is_open():
        invoice = InvoiceFactory(status="open")
        assert invoice.is_paid is False

    def it_formats_amount_due_in_dollars():
        invoice = InvoiceFactory(amount_due=12345)
        assert invoice.formatted_amount_due == "$123.45"

    def it_formats_amount_paid_in_dollars():
        invoice = InvoiceFactory(amount_due=5000, amount_paid=2500)
        assert invoice.formatted_amount_paid == "$25.00"

    def it_belongs_to_user():
        user = UserFactory()
        invoice = InvoiceFactory(user=user)
        assert invoice.user == user

    def it_stores_line_items():
        line_items = [
            {"description": "Monthly dues", "amount": 15000},
            {"description": "Studio rental", "amount": 20000},
        ]
        invoice = InvoiceFactory(line_items=line_items)
        invoice.refresh_from_db()
        assert invoice.line_items == line_items

    def it_has_stripe_invoice_id():
        invoice = InvoiceFactory(stripe_invoice_id="inv_1234567890")
        invoice.refresh_from_db()
        assert invoice.stripe_invoice_id == "inv_1234567890"

    def it_defaults_amount_paid_to_zero():
        user = UserFactory()
        invoice = Invoice.objects.create(user=user, amount_due=5000)
        assert invoice.amount_paid == 0


# ---------------------------------------------------------------------------
# Payout
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_payout():
    def it_has_str_representation():
        payout = PayoutFactory(payee_type="user", payee_id=42, amount=10000)
        assert str(payout) == f"Payout #{payout.pk} - $100.00 (user:42)"

    def it_formats_amount_in_dollars():
        payout = PayoutFactory(amount=25050)
        assert payout.formatted_amount == "$250.50"

    def it_is_distributed_when_status_is_distributed():
        payout = PayoutFactory(status="distributed")
        assert payout.is_distributed is True

    def it_is_not_distributed_when_status_is_pending():
        payout = PayoutFactory(status="pending")
        assert payout.is_distributed is False

    def it_defaults_status_to_pending():
        from django.utils import timezone

        payout = Payout.objects.create(
            payee_type="user",
            payee_id=1,
            amount=5000,
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
        )
        assert payout.status == Payout.Status.PENDING

    def it_has_period_dates():
        from datetime import date

        payout = PayoutFactory(period_start=date(2025, 1, 1), period_end=date(2025, 1, 31))
        payout.refresh_from_db()
        assert payout.period_start == date(2025, 1, 1)
        assert payout.period_end == date(2025, 1, 31)
