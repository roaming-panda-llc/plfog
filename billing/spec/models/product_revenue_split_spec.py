from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from billing.models import ProductRevenueSplit
from tests.billing.factories import ProductFactory
from tests.membership.factories import GuildFactory


def describe_ProductRevenueSplit():
    def describe_constraints():
        def it_allows_an_admin_row_with_no_guild(db):
            product = ProductFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                guild=None,
                percent=Decimal("20"),
            )
            assert product.splits.count() == 1

        def it_allows_a_guild_row_with_a_guild(db):
            product = ProductFactory()
            guild = GuildFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("80"),
            )
            assert product.splits.count() == 1

        def it_rejects_an_admin_row_that_has_a_guild(db):
            product = ProductFactory()
            guild = GuildFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=guild,
                    percent=Decimal("20"),
                )

        def it_rejects_a_guild_row_with_no_guild(db):
            product = ProductFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                    guild=None,
                    percent=Decimal("80"),
                )

        def it_rejects_a_zero_percent(db):
            product = ProductFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("0"),
                )

        def it_rejects_a_percent_over_100(db):
            product = ProductFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("100.01"),
                )

    def describe_uniqueness():
        def it_rejects_two_admin_rows_on_the_same_product(db):
            product = ProductFactory()
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
            product = ProductFactory()
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
            p1 = ProductFactory()
            p2 = ProductFactory()
            ProductRevenueSplit.objects.create(
                product=p1, recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild, percent=Decimal("100"),
            )
            ProductRevenueSplit.objects.create(
                product=p2, recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild, percent=Decimal("100"),
            )
            assert ProductRevenueSplit.objects.filter(guild=guild).count() == 2
