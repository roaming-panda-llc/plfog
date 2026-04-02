"""BDD-style tests for the bill_tabs management command."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from billing.models import BillingSettings, TabCharge
from tests.billing.factories import (
    BillingSettingsFactory,
    ProductFactory,
    StripeAccountFactory,
    TabChargeFactory,
    TabEntryFactory,
    TabFactory,
)
from tests.membership.factories import GuildFactory, MemberFactory

pytestmark = pytest.mark.django_db


def _call_bill_tabs(**kwargs: object) -> str:
    out = StringIO()
    call_command("bill_tabs", stdout=out, **kwargs)
    return out.getvalue()


def describe_bill_tabs():
    def describe_locking():
        @patch("billing.management.commands.bill_tabs.Command._acquire_lock", return_value=False)
        def it_exits_when_lock_not_acquired(mock_lock):
            output = _call_bill_tabs()
            assert "Another billing run" in output

    def describe_schedule():
        def it_exits_when_billing_is_off():
            BillingSettingsFactory(charge_frequency=BillingSettings.ChargeFrequency.OFF)
            output = _call_bill_tabs()
            assert "turned off" in output

        @patch("billing.management.commands.bill_tabs.Command._is_billing_time", return_value=False)
        def it_exits_when_not_billing_time(mock_time):
            BillingSettingsFactory(charge_frequency=BillingSettings.ChargeFrequency.MONTHLY)
            output = _call_bill_tabs()
            assert "Not time" in output

        @patch("billing.management.commands.bill_tabs.Command._is_billing_time", return_value=True)
        def it_runs_when_billing_time(mock_time):
            BillingSettingsFactory()
            output = _call_bill_tabs()
            assert "Billing complete" in output

        def it_runs_with_force_flag():
            BillingSettingsFactory()
            output = _call_bill_tabs(force=True)
            assert "Billing complete" in output

    def describe_is_billing_time():
        def it_returns_true_for_daily():
            settings = BillingSettingsFactory(charge_frequency=BillingSettings.ChargeFrequency.DAILY)
            from billing.management.commands.bill_tabs import Command

            cmd = Command()
            assert cmd._is_billing_time(settings) is True

        @patch("billing.management.commands.bill_tabs.timezone")
        def it_returns_true_for_weekly_on_correct_day(mock_tz):
            mock_tz.localtime.return_value = type("FakeTime", (), {"weekday": lambda self: 2})()
            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.WEEKLY,
                charge_day_of_week=2,
                charge_day_of_month=None,
            )
            from billing.management.commands.bill_tabs import Command

            cmd = Command()
            assert cmd._is_billing_time(settings) is True

        @patch("billing.management.commands.bill_tabs.timezone")
        def it_returns_false_for_weekly_on_wrong_day(mock_tz):
            mock_tz.localtime.return_value = type("FakeTime", (), {"weekday": lambda self: 3})()
            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.WEEKLY,
                charge_day_of_week=2,
                charge_day_of_month=None,
            )
            from billing.management.commands.bill_tabs import Command

            cmd = Command()
            assert cmd._is_billing_time(settings) is False

        @patch("billing.management.commands.bill_tabs.timezone")
        def it_returns_true_for_monthly_on_correct_day(mock_tz):
            mock_tz.localtime.return_value = type("FakeTime", (), {"day": 15})()
            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.MONTHLY,
                charge_day_of_month=15,
                charge_day_of_week=None,
            )
            from billing.management.commands.bill_tabs import Command

            cmd = Command()
            assert cmd._is_billing_time(settings) is True

        @patch("billing.management.commands.bill_tabs.timezone")
        def it_returns_false_for_monthly_on_wrong_day(mock_tz):
            mock_tz.localtime.return_value = type("FakeTime", (), {"day": 14})()
            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.MONTHLY,
                charge_day_of_month=15,
                charge_day_of_week=None,
            )
            from billing.management.commands.bill_tabs import Command

            cmd = Command()
            assert cmd._is_billing_time(settings) is False

        def it_returns_false_for_off():
            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.OFF,
                charge_day_of_week=None,
                charge_day_of_month=None,
            )
            from billing.management.commands.bill_tabs import Command

            cmd = Command()
            assert cmd._is_billing_time(settings) is False

    def describe_processing():
        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_charges_tabs_with_pending_entries(mock_receipt, mock_stripe):
            mock_stripe.return_value = {
                "id": "pi_test",
                "status": "succeeded",
                "charge_id": "ch_test",
                "receipt_url": "https://stripe.com/receipt",
            }
            BillingSettingsFactory()
            member = MemberFactory(status="active")
            tab = TabFactory(
                member=member,
                stripe_customer_id="cus_test",
                stripe_payment_method_id="pm_test",
            )
            TabEntryFactory(tab=tab, amount=Decimal("30.00"))
            TabEntryFactory(tab=tab, amount=Decimal("20.00"))

            output = _call_bill_tabs(force=True)

            assert "1 charged" in output
            charge = TabCharge.objects.get(tab=tab)
            assert charge.status == TabCharge.Status.SUCCEEDED
            assert charge.amount == Decimal("50.00")
            assert charge.stripe_payment_intent_id == "pi_test"
            mock_receipt.assert_called_once()

        def it_skips_inactive_members():
            BillingSettingsFactory()
            member = MemberFactory(status="former")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, amount=Decimal("30.00"))

            output = _call_bill_tabs(force=True)

            assert "0 charged" in output

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_skips_zero_balance(mock_receipt, mock_stripe):
            BillingSettingsFactory()
            member = MemberFactory(status="active")
            TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            # No entries — zero balance

            output = _call_bill_tabs(force=True)

            assert "0 charged" in output
            mock_stripe.assert_not_called()

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_skips_sub_minimum_balance(mock_receipt, mock_stripe):
            BillingSettingsFactory()
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, amount=Decimal("0.25"))

            output = _call_bill_tabs(force=True)

            assert "0 charged" in output

        def it_skips_tabs_without_payment_method():
            BillingSettingsFactory()
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="")
            TabEntryFactory(tab=tab, amount=Decimal("30.00"))

            output = _call_bill_tabs(force=True)

            assert "0 charged" in output

        def it_skips_tabs_without_customer_id():
            BillingSettingsFactory()
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, amount=Decimal("30.00"))

            output = _call_bill_tabs(force=True)

            assert "0 charged" in output

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.notify_admin_charge_failed")
        def it_handles_stripe_failure(mock_notify, mock_stripe):
            mock_stripe.side_effect = Exception("Card declined")
            BillingSettingsFactory(retry_interval_hours=24)
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, amount=Decimal("30.00"))

            output = _call_bill_tabs(force=True)

            assert "0 charged, 1 skipped" in output
            charge = TabCharge.objects.get(tab=tab)
            assert charge.status == TabCharge.Status.FAILED
            assert charge.retry_count == 1
            assert charge.next_retry_at is not None
            mock_notify.assert_called_once()

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_excludes_voided_entries_from_charge(mock_receipt, mock_stripe):
            mock_stripe.return_value = {
                "id": "pi_test",
                "status": "succeeded",
                "charge_id": "ch_test",
                "receipt_url": "",
            }
            BillingSettingsFactory()
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, amount=Decimal("30.00"))
            voided = TabEntryFactory(tab=tab, amount=Decimal("20.00"))
            from tests.billing.factories import UserFactory

            voided.void(user=UserFactory(), reason="test")

            output = _call_bill_tabs(force=True)

            assert "1 charged" in output
            charge = TabCharge.objects.get(tab=tab)
            assert charge.amount == Decimal("30.00")

        def describe_destination_routing():
            @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
            @patch("billing.management.commands.bill_tabs.stripe_utils.create_destination_payment_intent")
            @patch("billing.management.commands.bill_tabs.send_receipt")
            def it_creates_separate_charges_per_guild(mock_receipt, mock_dest, mock_platform):
                mock_dest.return_value = {
                    "id": "pi_dest",
                    "status": "succeeded",
                    "charge_id": "ch_dest",
                    "receipt_url": "https://stripe.com/receipt",
                }
                mock_platform.return_value = {
                    "id": "pi_plat",
                    "status": "succeeded",
                    "charge_id": "ch_plat",
                    "receipt_url": "https://stripe.com/receipt",
                }
                BillingSettingsFactory()
                member = MemberFactory(status="active")
                tab = TabFactory(
                    member=member,
                    stripe_customer_id="cus_test",
                    stripe_payment_method_id="pm_test",
                )
                guild_a = GuildFactory()
                guild_b = GuildFactory()
                StripeAccountFactory(guild=guild_a, is_active=True)
                StripeAccountFactory(guild=guild_b, is_active=True)
                product_a = ProductFactory(guild=guild_a, price=Decimal("12.00"))
                product_b = ProductFactory(guild=guild_b, price=Decimal("8.00"))
                TabEntryFactory(tab=tab, amount=Decimal("12.00"), product=product_a)
                TabEntryFactory(tab=tab, amount=Decimal("8.00"), product=product_b)
                TabEntryFactory(tab=tab, amount=Decimal("5.00"))  # platform (no product)

                output = _call_bill_tabs(force=True)

                assert "3 charged" in output
                assert mock_dest.call_count == 2
                assert mock_platform.call_count == 1

            @patch("billing.management.commands.bill_tabs.stripe_utils.create_destination_payment_intent")
            @patch("billing.management.commands.bill_tabs.send_receipt")
            def it_includes_application_fee(mock_receipt, mock_dest):
                mock_dest.return_value = {
                    "id": "pi_fee",
                    "status": "succeeded",
                    "charge_id": "ch_fee",
                    "receipt_url": "https://stripe.com/receipt",
                }
                BillingSettingsFactory()
                member = MemberFactory(status="active")
                tab = TabFactory(
                    member=member,
                    stripe_customer_id="cus_test",
                    stripe_payment_method_id="pm_test",
                )
                guild = GuildFactory()
                StripeAccountFactory(guild=guild, is_active=True, platform_fee_percent=Decimal("15.00"))
                product = ProductFactory(guild=guild, price=Decimal("100.00"))
                TabEntryFactory(tab=tab, amount=Decimal("100.00"), product=product)

                _call_bill_tabs(force=True)

                assert mock_dest.call_count == 1
                call_kwargs = mock_dest.call_args[1]
                assert call_kwargs["application_fee_cents"] == 1500

            @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
            @patch("billing.management.commands.bill_tabs.send_receipt")
            def it_skips_entries_with_disconnected_guild(mock_receipt, mock_platform):
                mock_platform.return_value = {
                    "id": "pi_plat",
                    "status": "succeeded",
                    "charge_id": "ch_plat",
                    "receipt_url": "https://stripe.com/receipt",
                }
                BillingSettingsFactory()
                guild = GuildFactory()
                StripeAccountFactory(guild=guild, is_active=False)
                product = ProductFactory(guild=guild, price=Decimal("20.00"))

                # Tab 1: only disconnected guild entries — will be skipped entirely
                member1 = MemberFactory(status="active")
                tab1 = TabFactory(
                    member=member1,
                    stripe_customer_id="cus_test1",
                    stripe_payment_method_id="pm_test1",
                )
                TabEntryFactory(tab=tab1, amount=Decimal("20.00"), product=product)

                # Tab 2: platform entry only — will succeed
                member2 = MemberFactory(status="active")
                tab2 = TabFactory(
                    member=member2,
                    stripe_customer_id="cus_test2",
                    stripe_payment_method_id="pm_test2",
                )
                TabEntryFactory(tab=tab2, amount=Decimal("5.00"))  # platform (no product)

                output = _call_bill_tabs(force=True)

                assert "1 charged" in output
                assert "1 skipped" in output

    def describe_retries():
        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_retries_failed_charges(mock_receipt, mock_stripe):
            mock_stripe.return_value = {
                "id": "pi_retry",
                "status": "succeeded",
                "charge_id": "ch_retry",
                "receipt_url": "https://stripe.com/receipt",
            }
            BillingSettingsFactory(max_retry_attempts=3)
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabChargeFactory(
                tab=tab,
                status=TabCharge.Status.FAILED,
                amount=Decimal("50.00"),
                retry_count=1,
                next_retry_at=timezone.now() - timedelta(hours=1),
            )

            output = _call_bill_tabs(force=True)

            assert "1 retried" in output
            charge = TabCharge.objects.get(tab=tab)
            assert charge.status == TabCharge.Status.SUCCEEDED

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.notify_admin_charge_failed")
        def it_locks_tab_after_max_retries(mock_notify, mock_stripe):
            mock_stripe.side_effect = Exception("Still declined")
            BillingSettingsFactory(max_retry_attempts=3)
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabChargeFactory(
                tab=tab,
                status=TabCharge.Status.FAILED,
                amount=Decimal("50.00"),
                retry_count=2,
                next_retry_at=timezone.now() - timedelta(hours=1),
            )

            _call_bill_tabs(force=True)

            tab.refresh_from_db()
            assert tab.is_locked is True
            assert "3 attempts" in tab.locked_reason
            mock_notify.assert_called_once()

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        def it_schedules_next_retry_when_retries_remain(mock_stripe):
            mock_stripe.side_effect = Exception("Declined again")
            BillingSettingsFactory(max_retry_attempts=3, retry_interval_hours=12)
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabChargeFactory(
                tab=tab,
                status=TabCharge.Status.FAILED,
                amount=Decimal("50.00"),
                retry_count=1,
                next_retry_at=timezone.now() - timedelta(hours=1),
            )

            _call_bill_tabs(force=True)

            charge = TabCharge.objects.get(tab=tab)
            assert charge.retry_count == 2
            assert charge.next_retry_at is not None
            tab.refresh_from_db()
            assert tab.is_locked is False

        def it_skips_retry_when_no_payment_method():
            BillingSettingsFactory(max_retry_attempts=3)
            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="")
            TabChargeFactory(
                tab=tab,
                status=TabCharge.Status.FAILED,
                amount=Decimal("50.00"),
                retry_count=1,
                next_retry_at=timezone.now() - timedelta(hours=1),
            )

            output = _call_bill_tabs(force=True)

            assert "0 retried" in output
