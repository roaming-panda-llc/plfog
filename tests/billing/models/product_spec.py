from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError

from tests.billing.factories import BillingSettingsFactory, ProductFactory
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

    def describe_effective_admin_percent():
        def it_returns_override_when_set(db):
            BillingSettingsFactory(default_admin_percent=Decimal("20.00"))
            product = ProductFactory(admin_percent_override=Decimal("50.00"))
            assert product.effective_admin_percent == Decimal("50.00")

        def it_falls_back_to_site_default_when_override_is_none(db):
            BillingSettingsFactory(default_admin_percent=Decimal("25.00"))
            product = ProductFactory(admin_percent_override=None)
            assert product.effective_admin_percent == Decimal("25.00")
