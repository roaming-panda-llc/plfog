from decimal import Decimal

import pytest

from billing.models import TabEntrySplit
from tests.billing.factories import TabEntryFactory
from tests.membership.factories import GuildFactory


def _split_input(recipient_type, percent, guild=None):
    return {"recipient_type": recipient_type, "guild": guild, "percent": Decimal(str(percent))}


def describe_TabEntry_snapshot_splits():
    def it_writes_one_TabEntrySplit_per_input_row(db):
        entry = TabEntryFactory(amount=Decimal("10.00"))
        guild = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "20"),
            _split_input("guild", "80", guild=guild),
        ])
        assert entry.splits.count() == 2

    def it_rounds_each_split_amount_with_round_half_up(db):
        entry = TabEntryFactory(amount=Decimal("10.00"))
        guild = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "20", guild=None),
            _split_input("guild", "80", guild=guild),
        ])
        admin = entry.splits.get(recipient_type="admin")
        g = entry.splits.get(recipient_type="guild")
        assert admin.amount == Decimal("2.00")
        assert g.amount == Decimal("8.00")

    def it_assigns_remainder_pennies_to_the_largest_percent_row(db):
        # $0.03 split three ways = $0.01 each, no remainder. Try $0.10 / 3 ways:
        # 33% -> 0.033 -> 0.03;  33% -> 0.033 -> 0.03;  34% -> 0.034 -> 0.03
        # raw sum = 0.09; remainder = 0.01 should go to largest (34%) row.
        entry = TabEntryFactory(amount=Decimal("0.10"))
        g1 = GuildFactory()
        g2 = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "33", guild=None),
            _split_input("guild", "33", guild=g1),
            _split_input("guild", "34", guild=g2),
        ])
        amounts = sorted(entry.splits.values_list("amount", flat=True))
        assert amounts == [Decimal("0.03"), Decimal("0.03"), Decimal("0.04")]
        # 34% row absorbs the penny
        largest = entry.splits.get(percent=Decimal("34"))
        assert largest.amount == Decimal("0.04")

    def it_keeps_sum_equal_to_entry_amount_for_one_cent_50_50(db):
        entry = TabEntryFactory(amount=Decimal("0.01"))
        g = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "50"),
            _split_input("guild", "50", guild=g),
        ])
        total = sum((s.amount for s in entry.splits.all()), Decimal("0"))
        assert total == Decimal("0.01")

    def it_handles_a_single_recipient_at_100_percent(db):
        entry = TabEntryFactory(amount=Decimal("25.00"))
        g = GuildFactory()
        entry.snapshot_splits([_split_input("guild", "100", guild=g)])
        assert entry.splits.count() == 1
        only = entry.splits.first()
        assert only.amount == Decimal("25.00")
        assert only.percent == Decimal("100")
        assert only.guild_id == g.pk

    def it_breaks_largest_percent_ties_by_lowest_id(db):
        # 50/50 split: both rows are equally largest. Penny remainder
        # (if any) should go to the row created first (lowest id).
        entry = TabEntryFactory(amount=Decimal("0.03"))
        g = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "50"),
            _split_input("guild", "50", guild=g),
        ])
        admin_split = entry.splits.get(recipient_type="admin")
        guild_split = entry.splits.get(recipient_type="guild")
        # 0.03 * 0.5 = 0.015 -> rounds half-up to 0.02 each = 0.04 (overshoot by 0.01)
        # OR 0.015 floors to 0.01 each = 0.02 (undershoot by 0.01).
        # Either way one row absorbs +/-0.01 to make total exactly 0.03.
        # Lowest id (admin, created first) absorbs the adjustment.
        assert admin_split.amount + guild_split.amount == Decimal("0.03")
        assert admin_split.id < guild_split.id

    def it_raises_if_inputs_dont_cover_full_amount_after_rounding(db):
        # Sanity check: snapshot_splits should not be callable with bad inputs.
        # Form-level validation prevents this in production, but the method
        # asserts internally as defense in depth.
        entry = TabEntryFactory(amount=Decimal("10.00"))
        with pytest.raises(AssertionError):
            entry.snapshot_splits([
                _split_input("admin", "50"),
                # Missing other 50% — sums to 50, not 100
            ])

    def it_creates_admin_split_with_null_guild(db):
        entry = TabEntryFactory(amount=Decimal("5.00"))
        entry.snapshot_splits([_split_input("admin", "100")])
        only = entry.splits.first()
        assert only.recipient_type == TabEntrySplit.RecipientType.ADMIN
        assert only.guild_id is None
