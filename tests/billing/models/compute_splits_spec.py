"""BDD-style tests for TabEntry.compute_splits() — the revenue split engine.

These tests pin specific behavior of the remainder-allocation algorithm. Changing
the distribution rule later would silently shift pennies between guilds across
historical reports, so these assertions are deliberately strict.
"""

from decimal import Decimal

import pytest

from billing.models import EntrySplit, Product
from tests.billing.factories import TabEntryFactory
from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db


def describe_compute_splits():
    def describe_single_guild():
        def it_splits_20_percent_admin_on_10_dollar_entry():
            guild = GuildFactory()
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("20.00"),
                split_mode=Product.SplitMode.SINGLE_GUILD,
                guild=guild,
                split_guild_ids=[],
            )
            splits = entry.compute_splits()
            assert splits == [
                EntrySplit(
                    guild_id=guild.pk,
                    admin_amount=Decimal("2.00"),
                    guild_amount=Decimal("8.00"),
                )
            ]

        def it_returns_admin_only_row_when_no_guild():
            entry = TabEntryFactory(
                amount=Decimal("7.50"),
                admin_percent=Decimal("20.00"),
                split_mode=Product.SplitMode.SINGLE_GUILD,
                guild=None,
                split_guild_ids=[],
            )
            splits = entry.compute_splits()
            assert splits == [
                EntrySplit(
                    guild_id=None,
                    admin_amount=Decimal("7.50"),
                    guild_amount=Decimal("0.00"),
                    is_admin_only=True,
                )
            ]

        def it_handles_100_percent_admin():
            guild = GuildFactory()
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("100.00"),
                split_mode=Product.SplitMode.SINGLE_GUILD,
                guild=guild,
            )
            splits = entry.compute_splits()
            assert splits == [
                EntrySplit(
                    guild_id=guild.pk,
                    admin_amount=Decimal("10.00"),
                    guild_amount=Decimal("0.00"),
                )
            ]

        def it_handles_0_percent_admin():
            guild = GuildFactory()
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("0.00"),
                split_mode=Product.SplitMode.SINGLE_GUILD,
                guild=guild,
            )
            splits = entry.compute_splits()
            assert splits == [
                EntrySplit(
                    guild_id=guild.pk,
                    admin_amount=Decimal("0.00"),
                    guild_amount=Decimal("10.00"),
                )
            ]

    def describe_split_equally():
        def it_splits_10_dollars_20_percent_across_4_guilds_evenly():
            # $10 * 20% = $2 admin. $8 guild total / 4 = $2 per guild, no remainder.
            guilds = [GuildFactory() for _ in range(4)]
            gids = sorted([g.pk for g in guilds])
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("20.00"),
                split_mode=Product.SplitMode.SPLIT_EQUALLY,
                guild=None,
                split_guild_ids=gids,
            )
            splits = entry.compute_splits()
            assert len(splits) == 4
            # First row carries the admin share
            assert splits[0].guild_id == gids[0]
            assert splits[0].admin_amount == Decimal("2.00")
            assert splits[0].guild_amount == Decimal("2.00")
            for split in splits[1:]:
                assert split.admin_amount == Decimal("0.00")
                assert split.guild_amount == Decimal("2.00")
            # Sum reconciles to the entry amount
            total = sum((s.admin_amount + s.guild_amount for s in splits), Decimal("0.00"))
            assert total == Decimal("10.00")

        def it_pins_remainder_allocation_for_10_dollars_0_percent_3_guilds():
            # $10 * 0% = $0 admin. $10 / 3 = $3.33 base, $0.01 remainder.
            # The remainder goes to the first sorted guild.
            guilds = [GuildFactory() for _ in range(3)]
            gids = sorted([g.pk for g in guilds])
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("0.00"),
                split_mode=Product.SplitMode.SPLIT_EQUALLY,
                guild=None,
                split_guild_ids=gids,
            )
            splits = entry.compute_splits()
            assert len(splits) == 3
            assert splits[0].guild_id == gids[0]
            assert splits[0].admin_amount == Decimal("0.00")
            assert splits[0].guild_amount == Decimal("3.34")
            assert splits[1].guild_id == gids[1]
            assert splits[1].guild_amount == Decimal("3.33")
            assert splits[2].guild_id == gids[2]
            assert splits[2].guild_amount == Decimal("3.33")
            total = sum((s.guild_amount for s in splits), Decimal("0.00"))
            assert total == Decimal("10.00")

        def it_handles_33_percent_admin_3_guilds():
            # $10 * 33% = $3.30 admin. $6.70 / 3 = $2.23 base, $0.01 remainder.
            guilds = [GuildFactory() for _ in range(3)]
            gids = sorted([g.pk for g in guilds])
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("33.00"),
                split_mode=Product.SplitMode.SPLIT_EQUALLY,
                guild=None,
                split_guild_ids=gids,
            )
            splits = entry.compute_splits()
            assert len(splits) == 3
            assert splits[0].admin_amount == Decimal("3.30")
            assert splits[0].guild_amount == Decimal("2.24")
            assert splits[1].admin_amount == Decimal("0.00")
            assert splits[1].guild_amount == Decimal("2.23")
            assert splits[2].admin_amount == Decimal("0.00")
            assert splits[2].guild_amount == Decimal("2.23")
            total = sum((s.admin_amount + s.guild_amount for s in splits), Decimal("0.00"))
            assert total == Decimal("10.00")

        def it_falls_back_to_admin_only_when_snapshot_is_empty():
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("20.00"),
                split_mode=Product.SplitMode.SPLIT_EQUALLY,
                guild=None,
                split_guild_ids=[],
            )
            splits = entry.compute_splits()
            assert splits == [
                EntrySplit(
                    guild_id=None,
                    admin_amount=Decimal("10.00"),
                    guild_amount=Decimal("0.00"),
                    is_admin_only=True,
                )
            ]

        def it_sorts_guild_ids_before_allocating():
            # Input order should not affect which guild gets the remainder.
            guilds = [GuildFactory() for _ in range(3)]
            gids = sorted([g.pk for g in guilds])
            reversed_ids = list(reversed(gids))
            entry = TabEntryFactory(
                amount=Decimal("10.00"),
                admin_percent=Decimal("0.00"),
                split_mode=Product.SplitMode.SPLIT_EQUALLY,
                guild=None,
                split_guild_ids=reversed_ids,
            )
            splits = entry.compute_splits()
            # First sorted guild always gets the extra cent, regardless of input order
            assert splits[0].guild_id == gids[0]
            assert splits[0].guild_amount == Decimal("3.34")


def describe_Tab_add_entry_snapshots():
    def it_snapshots_admin_percent_from_site_default(tab):
        from billing.models import BillingSettings

        BillingSettings.load()  # ensure singleton exists (default 20%)
        entry = tab.add_entry(description="Custom", amount=Decimal("5.00"))
        assert entry.admin_percent == Decimal("20.00")

    def it_snapshots_admin_percent_from_product_override(tab):
        from billing.models import Product
        from tests.billing.factories import ProductFactory

        product = ProductFactory(price=Decimal("12.00"), admin_percent_override=Decimal("50.00"))
        entry = tab.add_entry(description=product.name, amount=product.price, product=product)
        assert entry.admin_percent == Decimal("50.00")
        assert entry.guild_id == product.guild_id
        assert entry.split_mode == Product.SplitMode.SINGLE_GUILD

    def it_snapshots_split_guild_ids_on_split_equally(tab):
        from billing.models import Product
        from tests.billing.factories import ProductFactory
        from tests.membership.factories import GuildFactory

        other_guilds = [GuildFactory() for _ in range(2)]
        product = ProductFactory(split_mode=Product.SplitMode.SPLIT_EQUALLY)
        entry = tab.add_entry(description=product.name, amount=product.price, product=product)
        assert entry.split_mode == Product.SplitMode.SPLIT_EQUALLY
        # Snapshot includes the product's guild + the two new ones
        expected_ids = sorted([product.guild_id] + [g.pk for g in other_guilds])
        assert sorted(entry.split_guild_ids) == expected_ids

    def it_excludes_inactive_guilds_from_split_equally_snapshot(tab):
        from billing.models import Product
        from tests.billing.factories import ProductFactory
        from tests.membership.factories import GuildFactory

        active_guild = GuildFactory(is_active=True)
        GuildFactory(is_active=False)  # should be excluded
        product = ProductFactory(split_mode=Product.SplitMode.SPLIT_EQUALLY)
        entry = tab.add_entry(description=product.name, amount=product.price, product=product)
        # Only active guilds: product's guild + active_guild
        expected_ids = sorted([product.guild_id, active_guild.pk])
        assert sorted(entry.split_guild_ids) == expected_ids

    def it_does_not_retroactively_affect_existing_entries(tab):
        """Creating a new guild after an entry must not alter that entry's snapshot."""
        from billing.models import Product
        from tests.billing.factories import ProductFactory
        from tests.membership.factories import GuildFactory

        product = ProductFactory(split_mode=Product.SplitMode.SPLIT_EQUALLY)
        entry = tab.add_entry(description=product.name, amount=product.price, product=product)
        snapshot = list(entry.split_guild_ids)
        GuildFactory()  # new guild after the fact
        entry.refresh_from_db()
        assert list(entry.split_guild_ids) == snapshot


@pytest.fixture
def tab():
    from tests.billing.factories import TabFactory

    return TabFactory()
