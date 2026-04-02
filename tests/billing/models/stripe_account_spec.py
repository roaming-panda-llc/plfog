from __future__ import annotations

from decimal import Decimal

from tests.billing.factories import StripeAccountFactory
from tests.membership.factories import GuildFactory


def describe_StripeAccount():
    def it_has_str_representation(db):
        account = StripeAccountFactory(display_name="Workshop Account")
        assert str(account) == "Workshop Account"

    def it_links_to_guild(db):
        guild = GuildFactory(name="Woodshop")
        account = StripeAccountFactory(guild=guild)
        assert account.guild == guild
        assert guild.stripe_account == account

    def it_allows_null_guild(db):
        account = StripeAccountFactory(guild=None)
        assert account.guild is None

    def it_defaults_to_active(db):
        account = StripeAccountFactory()
        assert account.is_active is True

    def it_defaults_platform_fee_to_zero(db):
        account = StripeAccountFactory()
        assert account.platform_fee_percent == Decimal("0.00")

    def describe_compute_fee():
        def it_returns_zero_when_fee_is_zero(db):
            account = StripeAccountFactory(platform_fee_percent=Decimal("0.00"))
            assert account.compute_fee(Decimal("100.00")) == Decimal("0.00")

        def it_computes_correct_fee(db):
            account = StripeAccountFactory(platform_fee_percent=Decimal("15.00"))
            assert account.compute_fee(Decimal("100.00")) == Decimal("15.00")

        def it_rounds_to_two_decimal_places(db):
            account = StripeAccountFactory(platform_fee_percent=Decimal("15.00"))
            assert account.compute_fee(Decimal("12.00")) == Decimal("1.80")
