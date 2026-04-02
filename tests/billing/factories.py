from __future__ import annotations

from decimal import Decimal

import factory
from django.contrib.auth import get_user_model

from billing.models import BillingSettings, Product, StripeAccount, Tab, TabCharge, TabEntry
from tests.membership.factories import GuildFactory, MemberFactory

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")


class BillingSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BillingSettings
        django_get_or_create = ("pk",)

    pk = 1
    charge_frequency = BillingSettings.ChargeFrequency.MONTHLY
    default_tab_limit = Decimal("200.00")


class StripeAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StripeAccount

    guild = factory.SubFactory(GuildFactory)
    stripe_account_id = factory.Sequence(lambda n: f"acct_test_{n:04d}")
    display_name = factory.LazyAttribute(lambda o: f"{o.guild.name} Account" if o.guild else "Platform Account")
    is_active = True
    platform_fee_percent = Decimal("0.00")


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Product {n}")
    price = Decimal("10.00")
    guild = factory.SubFactory(GuildFactory)
    is_active = True


class TabFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tab

    member = factory.SubFactory(MemberFactory)
    stripe_payment_method_id = "pm_test_1234"
    payment_method_last4 = "4242"
    payment_method_brand = "visa"


class TabEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TabEntry

    tab = factory.SubFactory(TabFactory)
    description = factory.Faker("sentence", nb_words=4)
    amount = Decimal("25.00")
    entry_type = TabEntry.EntryType.MANUAL


class TabChargeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TabCharge

    tab = factory.SubFactory(TabFactory)
    amount = Decimal("100.00")
    status = TabCharge.Status.PENDING
