"""Tests for stripe_utils and the bill_tabs management command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
import stripe as stripe_lib
from django.core.management import call_command
from django.utils import timezone

from billing.models import Invoice, Order, Payout
from billing.stripe_utils import (
    _create_local_invoice,
    create_invoice_for_user,
    get_stripe_key,
    process_payout_report,
)
from tests.billing.factories import OrderFactory, RevenueSplitFactory
from tests.core.factories import UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# get_stripe_key
# ---------------------------------------------------------------------------


def describe_get_stripe_key():
    def it_returns_test_key_when_not_live_mode(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = "sk_test_abc123"
        settings.STRIPE_LIVE_SECRET_KEY = "sk_live_xyz789"

        assert get_stripe_key() == "sk_test_abc123"

    def it_returns_live_key_when_live_mode(settings):
        settings.STRIPE_LIVE_MODE = True
        settings.STRIPE_TEST_SECRET_KEY = "sk_test_abc123"
        settings.STRIPE_LIVE_SECRET_KEY = "sk_live_xyz789"

        assert get_stripe_key() == "sk_live_xyz789"

    def it_returns_empty_string_when_no_key_configured(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        assert get_stripe_key() == ""


# ---------------------------------------------------------------------------
# _create_local_invoice
# ---------------------------------------------------------------------------


def describe_create_local_invoice():
    def it_creates_an_invoice_record():
        user = UserFactory()
        orders = Order.objects.filter(pk__in=[OrderFactory(user=user).pk, OrderFactory(user=user).pk])

        invoice = _create_local_invoice(user, orders)

        assert invoice.pk is not None
        assert Invoice.objects.filter(pk=invoice.pk).exists()

    def it_calculates_total_from_orders():
        user = UserFactory()
        o1 = OrderFactory(user=user, amount=3000)
        o2 = OrderFactory(user=user, amount=7000)
        orders = Order.objects.filter(pk__in=[o1.pk, o2.pk])

        invoice = _create_local_invoice(user, orders)

        assert invoice.amount_due == 10000

    def it_stores_line_items():
        user = UserFactory()
        order = OrderFactory(user=user, description="Monthly dues", amount=5000)
        orders = Order.objects.filter(pk=order.pk)

        invoice = _create_local_invoice(user, orders)

        assert invoice.line_items == [{"description": "Monthly dues", "amount": 5000}]

    def it_sets_status_to_open():
        user = UserFactory()
        order = OrderFactory(user=user)
        orders = Order.objects.filter(pk=order.pk)

        invoice = _create_local_invoice(user, orders)

        assert invoice.status == "open"

    def it_links_invoice_to_user():
        user = UserFactory()
        order = OrderFactory(user=user)
        orders = Order.objects.filter(pk=order.pk)

        invoice = _create_local_invoice(user, orders)

        assert invoice.user == user

    def it_does_not_set_stripe_invoice_id():
        user = UserFactory()
        order = OrderFactory(user=user)
        orders = Order.objects.filter(pk=order.pk)

        invoice = _create_local_invoice(user, orders)

        assert invoice.stripe_invoice_id == ""


# ---------------------------------------------------------------------------
# create_invoice_for_user
# ---------------------------------------------------------------------------


def describe_create_invoice_for_user():
    def it_falls_back_to_local_invoice_when_no_api_key(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        user = UserFactory()
        order = OrderFactory(user=user, amount=4000)
        orders = Order.objects.filter(pk=order.pk)

        invoice = create_invoice_for_user(user, orders)

        assert invoice is not None
        assert invoice.stripe_invoice_id == ""
        assert invoice.amount_due == 4000

    def it_returns_none_on_stripe_error(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = "sk_test_fakekeyfortesting"

        user = UserFactory()
        order = OrderFactory(user=user, amount=2000)
        orders = Order.objects.filter(pk=order.pk)

        with patch("billing.stripe_utils.stripe.Customer") as mock_customer:
            mock_customer.list.side_effect = stripe_lib.StripeError("API error")
            result = create_invoice_for_user(user, orders)

        assert result is None

    def it_creates_stripe_invoice_when_api_key_present(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = "sk_test_fakekeyfortesting"

        user = UserFactory()
        order = OrderFactory(user=user, amount=5000)
        orders = Order.objects.filter(pk=order.pk)

        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"

        mock_stripe_invoice = MagicMock()
        mock_stripe_invoice.id = "in_test456"
        mock_stripe_invoice.invoice_pdf = "https://stripe.com/invoice.pdf"

        with (
            patch("billing.stripe_utils.stripe.Customer") as mock_cust_cls,
            patch("billing.stripe_utils.stripe.InvoiceItem"),
            patch("billing.stripe_utils.stripe.Invoice") as mock_inv_cls,
        ):
            mock_cust_cls.list.return_value.data = [mock_customer]
            mock_inv_cls.create.return_value = mock_stripe_invoice
            mock_inv_cls.finalize_invoice.return_value = mock_stripe_invoice

            invoice = create_invoice_for_user(user, orders)

        assert invoice is not None
        assert invoice.stripe_invoice_id == "in_test456"
        assert invoice.amount_due == 5000
        assert invoice.pdf_url == "https://stripe.com/invoice.pdf"

    def it_creates_new_stripe_customer_when_none_exists(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = "sk_test_fakekeyfortesting"

        user = UserFactory()
        order = OrderFactory(user=user, amount=3000)
        orders = Order.objects.filter(pk=order.pk)

        mock_new_customer = MagicMock()
        mock_new_customer.id = "cus_new456"

        mock_stripe_invoice = MagicMock()
        mock_stripe_invoice.id = "in_new789"
        mock_stripe_invoice.invoice_pdf = ""

        with (
            patch("billing.stripe_utils.stripe.Customer") as mock_cust_cls,
            patch("billing.stripe_utils.stripe.InvoiceItem"),
            patch("billing.stripe_utils.stripe.Invoice") as mock_inv_cls,
        ):
            mock_cust_cls.list.return_value.data = []  # no existing customer
            mock_cust_cls.create.return_value = mock_new_customer
            mock_inv_cls.create.return_value = mock_stripe_invoice
            mock_inv_cls.finalize_invoice.return_value = mock_stripe_invoice

            invoice = create_invoice_for_user(user, orders)

        mock_cust_cls.create.assert_called_once()
        assert invoice is not None
        assert invoice.stripe_invoice_id == "in_new789"


# ---------------------------------------------------------------------------
# bill_tabs management command
# ---------------------------------------------------------------------------


def describe_bill_tabs_command():
    def it_does_nothing_when_no_tabs_exist(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        out = StringIO()
        call_command("bill_tabs", stdout=out)

        assert "No outstanding tabs" in out.getvalue()

    def it_bills_user_with_on_tab_orders(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        user = UserFactory()
        OrderFactory(user=user, status="on_tab", amount=3000)

        out = StringIO()
        call_command("bill_tabs", stdout=out)

        assert Invoice.objects.filter(user=user).exists()

    def it_updates_order_status_to_billed(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        user = UserFactory()
        order = OrderFactory(user=user, status="on_tab", amount=5000)

        call_command("bill_tabs", stdout=StringIO())

        order.refresh_from_db()
        assert order.status == Order.Status.BILLED

    def it_sets_billed_at_timestamp(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        before = timezone.now()
        user = UserFactory()
        order = OrderFactory(user=user, status="on_tab", amount=5000)

        call_command("bill_tabs", stdout=StringIO())

        order.refresh_from_db()
        assert order.billed_at is not None
        assert order.billed_at >= before

    def it_handles_multiple_users(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        user_a = UserFactory()
        user_b = UserFactory()
        OrderFactory(user=user_a, status="on_tab", amount=1000)
        OrderFactory(user=user_b, status="on_tab", amount=2000)

        out = StringIO()
        call_command("bill_tabs", stdout=out)

        assert Invoice.objects.filter(user=user_a).exists()
        assert Invoice.objects.filter(user=user_b).exists()
        assert "2 users total" in out.getvalue()

    def it_is_idempotent_second_run_finds_no_tabs(settings):
        """Running twice does not double-bill: first run bills orders, second run finds none."""
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        user = UserFactory()
        OrderFactory(user=user, status="on_tab", amount=5000)

        call_command("bill_tabs", stdout=StringIO())
        invoice_count_after_first = Invoice.objects.filter(user=user).count()

        out = StringIO()
        call_command("bill_tabs", stdout=out)
        invoice_count_after_second = Invoice.objects.filter(user=user).count()

        assert invoice_count_after_first == 1
        assert invoice_count_after_second == 1
        assert "No outstanding tabs" in out.getvalue()

    def it_prints_error_when_invoice_creation_fails(settings):
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        user = UserFactory()
        OrderFactory(user=user, status="on_tab", amount=1000)

        with patch("billing.management.commands.bill_tabs.create_invoice_for_user", return_value=None):
            out = StringIO()
            call_command("bill_tabs", stdout=out)

        assert f"Failed to bill {user.username}" in out.getvalue()

    def it_skips_user_whose_orders_were_already_billed(settings):
        """Cover the `continue` branch when a user's tab orders disappear between queries."""
        settings.STRIPE_LIVE_MODE = False
        settings.STRIPE_TEST_SECRET_KEY = ""

        user = UserFactory()
        order = OrderFactory(user=user, status="on_tab", amount=2000)

        # Bill the order before the command iterates, simulating a race
        original_filter = Order.objects.filter

        call_count = {"n": 0}

        def patched_filter(**kwargs):
            qs = original_filter(**kwargs)
            # On the per-user filter call, change order status so exists() returns False
            if kwargs.get("user") == user and kwargs.get("status") == Order.Status.ON_TAB:
                call_count["n"] += 1
                if call_count["n"] == 1:
                    order.status = Order.Status.BILLED
                    order.save()
            return qs

        with patch.object(Order.objects, "filter", side_effect=patched_filter):
            out = StringIO()
            call_command("bill_tabs", stdout=out)

        assert "0 users total" in out.getvalue()


# ---------------------------------------------------------------------------
# process_payout_report
# ---------------------------------------------------------------------------


def describe_process_payout_report():
    def it_creates_payout_records_from_paid_orders():
        user = UserFactory()
        split = RevenueSplitFactory(
            splits=[
                {"entity_type": "guild", "entity_id": 1, "percentage": 70},
                {"entity_type": "org", "entity_id": 1, "percentage": 30},
            ],
        )
        today = timezone.localtime(timezone.now()).date()
        OrderFactory(
            user=user,
            amount=10000,
            status="paid",
            revenue_split=split,
            issued_at=timezone.now(),
        )

        payouts = process_payout_report(today, today)

        assert len(payouts) == 2
        amounts = {(p.payee_type, p.payee_id): p.amount for p in payouts}
        assert amounts[("guild", 1)] == 7000
        assert amounts[("org", 1)] == 3000

    def it_returns_empty_list_when_no_paid_orders():
        today = timezone.localtime(timezone.now()).date()
        payouts = process_payout_report(today, today)
        assert payouts == []

    def it_aggregates_across_multiple_orders():
        user = UserFactory()
        split = RevenueSplitFactory(
            splits=[{"entity_type": "org", "entity_id": 1, "percentage": 100}],
        )
        today = timezone.localtime(timezone.now()).date()
        OrderFactory(user=user, amount=5000, status="paid", revenue_split=split, issued_at=timezone.now())
        OrderFactory(user=user, amount=3000, status="paid", revenue_split=split, issued_at=timezone.now())

        payouts = process_payout_report(today, today)

        assert len(payouts) == 1
        assert payouts[0].amount == 8000

    def it_ignores_unpaid_orders():
        user = UserFactory()
        split = RevenueSplitFactory(
            splits=[{"entity_type": "org", "entity_id": 1, "percentage": 100}],
        )
        today = timezone.localtime(timezone.now()).date()
        OrderFactory(user=user, amount=5000, status="on_tab", revenue_split=split, issued_at=timezone.now())

        payouts = process_payout_report(today, today)
        assert payouts == []

    def it_sets_payout_period_dates():
        user = UserFactory()
        split = RevenueSplitFactory(
            splits=[{"entity_type": "org", "entity_id": 1, "percentage": 100}],
        )
        today = timezone.localtime(timezone.now()).date()
        OrderFactory(user=user, amount=5000, status="paid", revenue_split=split, issued_at=timezone.now())

        payouts = process_payout_report(today, today)

        assert payouts[0].period_start == today
        assert payouts[0].period_end == today
        assert payouts[0].status == Payout.Status.PENDING
