from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from billing.models import ProductRevenueSplit
from tests.billing.factories import ProductFactory
from tests.membership.factories import GuildFactory


def describe_ProductRevenueSplit():
    def describe_constraints():
        def it_allows_an_admin_row_with_no_guild(db):
            product = ProductFactory(with_default_splits=False)
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                guild=None,
                percent=Decimal("20"),
            )
            assert product.splits.count() == 1

        def it_allows_a_guild_row_with_a_guild(db):
            product = ProductFactory(with_default_splits=False)
            guild = GuildFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("80"),
            )
            assert product.splits.count() == 1

        def it_rejects_an_admin_row_that_has_a_guild(db):
            product = ProductFactory(with_default_splits=False)
            guild = GuildFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=guild,
                    percent=Decimal("20"),
                )

        def it_rejects_a_guild_row_with_no_guild(db):
            product = ProductFactory(with_default_splits=False)
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                    guild=None,
                    percent=Decimal("80"),
                )

        def it_rejects_a_zero_percent(db):
            product = ProductFactory(with_default_splits=False)
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("0"),
                )

        def it_rejects_a_percent_over_100(db):
            product = ProductFactory(with_default_splits=False)
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("100.01"),
                )

    def describe_uniqueness():
        def it_rejects_two_admin_rows_on_the_same_product(db):
            product = ProductFactory(with_default_splits=False)
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                guild=None,
                percent=Decimal("20"),
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("10"),
                )

        def it_rejects_the_same_guild_twice_on_one_product(db):
            product = ProductFactory(with_default_splits=False)
            guild = GuildFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("50"),
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                    guild=guild,
                    percent=Decimal("30"),
                )

        def it_allows_the_same_guild_on_different_products(db):
            guild = GuildFactory()
            p1 = ProductFactory(with_default_splits=False)
            p2 = ProductFactory(with_default_splits=False)
            ProductRevenueSplit.objects.create(
                product=p1,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("100"),
            )
            ProductRevenueSplit.objects.create(
                product=p2,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("100"),
            )
            assert ProductRevenueSplit.objects.filter(guild=guild).count() == 2

    def describe_str():
        def it_renders_admin_rows(db):
            product = ProductFactory(with_default_splits=False)
            split = ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                guild=None,
                percent=Decimal("25"),
            )
            assert str(split) == "Admin 25%"

        def it_renders_guild_rows(db):
            guild = GuildFactory(name="Woodshop")
            product = ProductFactory(with_default_splits=False)
            split = ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("75"),
            )
            assert str(split) == "Woodshop 75%"

        def it_renders_guild_rows_with_missing_guild_safely():
            # Built but never persisted — bypasses the DB constraint so we can
            # exercise the defensive ``Guild?`` fallback in __str__.
            split = ProductRevenueSplit(
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=None,
                percent=Decimal("50"),
            )
            assert str(split) == "Guild? 50%"
