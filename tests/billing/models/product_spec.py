from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError

from tests.billing.factories import ProductFactory
from tests.membership.factories import GuildFactory


def describe_Product():
    def it_has_str_representation(db):
        product = ProductFactory(name="Laser Time")
        assert str(product) == "Laser Time"

    def it_links_to_guild(db):
        guild = GuildFactory(name="Woodshop")
        product = ProductFactory(guild=guild)
        assert product.guild == guild
        assert guild.products.first() == product

    def it_defaults_to_active(db):
        product = ProductFactory()
        assert product.is_active is True

    def it_enforces_positive_price(db):
        with pytest.raises(IntegrityError):
            ProductFactory(price=Decimal("0.00"))

    def it_cascades_on_guild_delete(db):
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        product_pk = product.pk
        guild.delete()
        from billing.models import Product

        assert not Product.objects.filter(pk=product_pk).exists()
