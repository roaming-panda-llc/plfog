"""BDD-style tests for the billing reports module."""

from __future__ import annotations

from decimal import Decimal

from billing.reports import build_report
from tests.billing.factories import ProductFactory, TabFactory
from tests.membership.factories import GuildFactory


def describe_build_report():
    def it_returns_one_row_per_TabEntrySplit(db):
        product = ProductFactory()  # default 20/80 split
        tab = TabFactory()
        tab.add_entry(description="x", amount=Decimal("10.00"), product=product)
        rows, payouts, admin_total = build_report()
        assert len(rows) == 2
        assert admin_total == Decimal("2.00")
        assert sum((r.amount for r in rows), Decimal("0")) == Decimal("10.00")

    def it_aggregates_payouts_per_recipient(db):
        product = ProductFactory()
        tab = TabFactory()
        tab.add_entry(description="x", amount=Decimal("10.00"), product=product)
        tab.add_entry(description="y", amount=Decimal("10.00"), product=product)
        rows, payouts, admin_total = build_report()
        # One payout row per recipient (admin + the owning guild)
        assert len(payouts) == 2
        admin_payout = next(p for p in payouts if p.recipient_type == "admin")
        guild_payout = next(p for p in payouts if p.recipient_type == "guild")
        assert admin_payout.amount == Decimal("4.00")
        assert guild_payout.amount == Decimal("16.00")
        assert guild_payout.entry_count == 2

    def it_excludes_voided_entries(db, django_user_model):
        product = ProductFactory()
        tab = TabFactory()
        e = tab.add_entry(description="x", amount=Decimal("10.00"), product=product)
        voider = django_user_model.objects.create_user(username="voider", password="x")
        e.void(user=voider, reason="oops")
        rows, payouts, admin_total = build_report()
        assert rows == []
        assert payouts == []
        assert admin_total == Decimal("0")

    def it_filters_by_recipient_guild(db):
        g1 = GuildFactory()
        g2 = GuildFactory()
        p1 = ProductFactory(guild=g1)
        p2 = ProductFactory(guild=g2)
        tab = TabFactory()
        tab.add_entry(description="x", amount=Decimal("10.00"), product=p1)
        tab.add_entry(description="y", amount=Decimal("10.00"), product=p2)
        rows, payouts, admin_total = build_report(guild_ids=[g1.pk])
        recipient_guild_ids = {r.guild_id for r in rows if r.recipient_type == "guild"}
        assert recipient_guild_ids == {g1.pk}
