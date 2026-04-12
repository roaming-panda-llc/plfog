"""BDD-style tests for the billing reports module + admin reports views."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from billing.models import Product, TabCharge
from billing.reports import CSV_HEADERS, build_report, stream_report_csv
from tests.billing.factories import (
    BillingSettingsFactory,
    ProductFactory,
    TabChargeFactory,
    TabEntryFactory,
    TabFactory,
)
from tests.membership.factories import GuildFactory, MemberFactory

pytestmark = pytest.mark.django_db

User = get_user_model()


def _create_superuser(client: Client) -> User:
    user = User.objects.create_superuser("reports_admin", "admin@example.com", "pass")
    client.force_login(user)
    return user


def describe_build_report():
    def it_returns_empty_results_when_no_entries():
        rows, payouts, admin_total = build_report()
        assert rows == []
        assert payouts == []
        assert admin_total == Decimal("0.00")

    def it_produces_one_row_per_single_guild_entry():
        BillingSettingsFactory()
        guild = GuildFactory(name="Clay")
        member = MemberFactory(full_legal_name="Alice")
        tab = TabFactory(member=member)
        TabEntryFactory(
            tab=tab,
            description="1 lb clay",
            amount=Decimal("10.00"),
            admin_percent=Decimal("20.00"),
            guild=guild,
        )

        rows, payouts, admin_total = build_report()

        assert len(rows) == 1
        assert rows[0].member_name == "Alice"
        assert rows[0].guild_name == "Clay"
        assert rows[0].admin_amount == Decimal("2.00")
        assert rows[0].guild_amount == Decimal("8.00")
        assert len(payouts) == 1
        assert payouts[0].guild_amount == Decimal("8.00")
        assert admin_total == Decimal("2.00")

    def it_expands_split_equally_into_one_row_per_guild():
        BillingSettingsFactory()
        guilds = [GuildFactory() for _ in range(4)]
        gids = sorted(g.pk for g in guilds)
        member = MemberFactory()
        tab = TabFactory(member=member)
        TabEntryFactory(
            tab=tab,
            amount=Decimal("10.00"),
            admin_percent=Decimal("20.00"),
            split_mode=Product.SplitMode.SPLIT_EQUALLY,
            guild=None,
            split_guild_ids=gids,
        )

        rows, payouts, admin_total = build_report()

        assert len(rows) == 4
        # First row carries the admin share
        assert rows[0].admin_amount == Decimal("2.00")
        for row in rows[1:]:
            assert row.admin_amount == Decimal("0.00")
        # Each guild gets $2.00
        for row in rows:
            assert row.guild_amount == Decimal("2.00")
        assert admin_total == Decimal("2.00")
        assert len(payouts) == 4
        total = sum((p.guild_amount for p in payouts), Decimal("0.00"))
        assert total == Decimal("8.00")

    def it_filters_by_date_range_inclusively():
        BillingSettingsFactory()
        guild = GuildFactory()
        member = MemberFactory()
        tab = TabFactory(member=member)
        old = TabEntryFactory(
            tab=tab,
            amount=Decimal("5.00"),
            admin_percent=Decimal("20.00"),
            guild=guild,
        )
        # Use update() to set created_at without touching auto_now_add
        from django.utils import timezone

        TabEntryFactory.__qualname__  # silence
        from billing.models import TabEntry

        TabEntry.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))
        TabEntryFactory(
            tab=tab,
            amount=Decimal("7.00"),
            admin_percent=Decimal("20.00"),
            guild=guild,
        )

        today = date.today()
        rows, _, _ = build_report(start_date=today - timedelta(days=3), end_date=today)
        assert len(rows) == 1
        assert rows[0].amount == Decimal("7.00")

    def it_filters_by_guild_and_drops_non_matching_split_rows():
        BillingSettingsFactory()
        g1, g2, g3 = GuildFactory(name="Alpha"), GuildFactory(name="Beta"), GuildFactory(name="Gamma")
        member = MemberFactory()
        tab = TabFactory(member=member)
        TabEntryFactory(
            tab=tab,
            amount=Decimal("30.00"),
            admin_percent=Decimal("0.00"),
            split_mode=Product.SplitMode.SPLIT_EQUALLY,
            guild=None,
            split_guild_ids=sorted([g1.pk, g2.pk, g3.pk]),
        )

        rows, payouts, _ = build_report(guild_ids=[g1.pk])
        # Only the split row that maps to g1 survives
        assert len(rows) == 1
        assert rows[0].guild_id == g1.pk
        assert len(payouts) == 1
        assert payouts[0].guild_id == g1.pk

    def it_filters_by_charge_type_product_vs_custom():
        BillingSettingsFactory()
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        member = MemberFactory()
        tab = TabFactory(member=member)
        TabEntryFactory(tab=tab, product=product, guild=guild, amount=Decimal("4.00"))
        TabEntryFactory(tab=tab, product=None, guild=None, amount=Decimal("5.00"))

        rows, _, _ = build_report(charge_types=["product"])
        assert len(rows) == 1
        assert rows[0].charge_type == "product"

        rows, _, _ = build_report(charge_types=["custom"])
        assert len(rows) == 1
        assert rows[0].charge_type == "custom"

    def it_filters_by_status():
        BillingSettingsFactory()
        guild = GuildFactory()
        member = MemberFactory()
        tab = TabFactory(member=member)
        pending = TabEntryFactory(tab=tab, guild=guild, amount=Decimal("3.00"))
        charge = TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED, amount=Decimal("5.00"))
        charged = TabEntryFactory(tab=tab, guild=guild, amount=Decimal("5.00"), tab_charge=charge)

        rows, _, _ = build_report(statuses=["pending"])
        amounts = sorted(r.amount for r in rows)
        assert amounts == [Decimal("3.00")]
        assert pending.pk  # silence unused

        rows, _, _ = build_report(statuses=[TabCharge.Status.SUCCEEDED])
        amounts = sorted(r.amount for r in rows)
        assert amounts == [Decimal("5.00")]
        assert charged.pk  # silence unused

    def it_reconciles_admin_plus_guilds_to_entry_amount():
        BillingSettingsFactory()
        guilds = [GuildFactory() for _ in range(3)]
        gids = sorted(g.pk for g in guilds)
        member = MemberFactory()
        tab = TabFactory(member=member)
        TabEntryFactory(
            tab=tab,
            amount=Decimal("10.00"),
            admin_percent=Decimal("33.00"),
            split_mode=Product.SplitMode.SPLIT_EQUALLY,
            guild=None,
            split_guild_ids=gids,
        )

        rows, payouts, admin_total = build_report()
        guild_total = sum((p.guild_amount for p in payouts), Decimal("0.00"))
        assert admin_total + guild_total == Decimal("10.00")


def describe_stream_report_csv():
    def it_writes_the_expected_header_row():
        response = stream_report_csv()
        body = b"".join(response.streaming_content).decode()
        header_line = body.splitlines()[0]
        assert header_line == ",".join(CSV_HEADERS)

    def it_writes_one_csv_line_per_split_row():
        BillingSettingsFactory()
        guild = GuildFactory(name="Metal")
        member = MemberFactory(full_legal_name="Bob")
        tab = TabFactory(member=member)
        TabEntryFactory(
            tab=tab,
            description="Welding rod",
            amount=Decimal("6.00"),
            admin_percent=Decimal("20.00"),
            guild=guild,
        )
        response = stream_report_csv()
        body = b"".join(response.streaming_content).decode()
        lines = [line for line in body.splitlines() if line]
        assert len(lines) == 2  # header + one row
        assert "Bob" in lines[1]
        assert "Welding rod" in lines[1]
        assert "4.80" in lines[1]  # $6.00 - 20% admin = $4.80 guild
        assert "1.20" in lines[1]  # admin amount

    def it_sets_content_disposition_with_a_filename():
        response = stream_report_csv()
        assert response["Content-Type"] == "text/csv"
        assert "attachment" in response["Content-Disposition"]
        assert "plfog-billing-report-" in response["Content-Disposition"]
        assert ".csv" in response["Content-Disposition"]


def describe_admin_reports_view():
    def it_requires_staff(client: Client):
        response = client.get("/billing/admin/reports/")
        assert response.status_code == 302

    def it_renders_blank_form_for_staff(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/reports/")
        assert response.status_code == 200
        assert b"Billing Reports" in response.content
        # No rows yet — no filters submitted
        assert response.context["rows"] == []

    def it_runs_a_report_with_filters(client: Client):
        _create_superuser(client)
        BillingSettingsFactory()
        guild = GuildFactory(name="Woodshop")
        member = MemberFactory()
        tab = TabFactory(member=member)
        TabEntryFactory(
            tab=tab,
            description="Chisel time",
            amount=Decimal("5.00"),
            admin_percent=Decimal("20.00"),
            guild=guild,
        )

        response = client.get(f"/billing/admin/reports/?guilds={guild.pk}")
        assert response.status_code == 200
        assert len(response.context["rows"]) == 1
        assert b"Chisel time" in response.content
        assert b"Woodshop" in response.content


def describe_admin_reports_csv_view():
    def it_requires_staff(client: Client):
        response = client.get("/billing/admin/reports/export/csv/")
        assert response.status_code == 302

    def it_streams_csv_for_staff(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/reports/export/csv/")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
