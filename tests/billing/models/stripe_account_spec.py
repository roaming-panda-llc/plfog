from __future__ import annotations

from decimal import Decimal

import pytest

from billing.models import StripeAccount
from tests.billing.factories import StripeAccountFactory
from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db


def describe_StripeAccount():
    def it_has_str_representation():
        account = StripeAccountFactory(display_name="Workshop Account")
        assert str(account) == "Workshop Account"

    def it_links_to_guild():
        guild = GuildFactory(name="Woodshop")
        account = StripeAccountFactory(guild=guild)
        assert account.guild == guild
        assert guild.stripe_account == account

    def it_allows_null_guild():
        account = StripeAccountFactory(guild=None)
        assert account.guild is None

    def it_defaults_to_active():
        account = StripeAccountFactory()
        assert account.is_active is True

    def it_defaults_platform_fee_to_zero():
        account = StripeAccountFactory()
        assert account.platform_fee_percent == Decimal("0.00")

    def describe_compute_fee():
        def it_returns_zero_when_fee_is_zero():
            account = StripeAccountFactory(platform_fee_percent=Decimal("0.00"))
            assert account.compute_fee(Decimal("100.00")) == Decimal("0.00")

        def it_computes_correct_fee():
            account = StripeAccountFactory(platform_fee_percent=Decimal("15.00"))
            assert account.compute_fee(Decimal("100.00")) == Decimal("15.00")

        def it_rounds_to_two_decimal_places():
            account = StripeAccountFactory(platform_fee_percent=Decimal("15.00"))
            assert account.compute_fee(Decimal("12.00")) == Decimal("1.80")

    def describe_upsert_for_guild():
        def it_creates_new_stripe_account_for_guild():
            guild = GuildFactory(name="Laser Guild")
            account = StripeAccount.upsert_for_guild(guild, "acct_new_001")
            assert account.pk is not None
            assert account.stripe_account_id == "acct_new_001"
            assert account.guild == guild

        def it_updates_existing_stripe_account():
            guild = GuildFactory(name="Metal Guild")
            StripeAccountFactory(guild=guild, stripe_account_id="acct_old_999")
            account = StripeAccount.upsert_for_guild(guild, "acct_updated_001")
            assert account.stripe_account_id == "acct_updated_001"
            assert StripeAccount.objects.filter(guild=guild).count() == 1

        def it_sets_is_active_true_and_display_name_from_guild():
            guild = GuildFactory(name="Wood Guild")
            account = StripeAccount.upsert_for_guild(guild, "acct_wood_001")
            assert account.is_active is True
            assert account.display_name == guild.name

        def it_sets_connected_at():
            guild = GuildFactory(name="Ceramics Guild")
            account = StripeAccount.upsert_for_guild(guild, "acct_clay_001")
            assert account.connected_at is not None

    def describe_auth_mode():
        def it_defaults_to_oauth():
            account = StripeAccountFactory()
            assert account.auth_mode == StripeAccount.AuthMode.OAUTH

        def it_rejects_nonzero_platform_fee_when_direct_keys():
            from django.core.exceptions import ValidationError
            from tests.billing.factories import DirectKeysStripeAccountFactory

            account = DirectKeysStripeAccountFactory.build(platform_fee_percent=Decimal("3.50"))
            with pytest.raises(ValidationError, match="Platform fee must be 0"):
                account.clean()

        def it_allows_zero_platform_fee_when_direct_keys():
            from tests.billing.factories import DirectKeysStripeAccountFactory

            account = DirectKeysStripeAccountFactory.build(platform_fee_percent=Decimal("0.00"))
            account.clean()  # should not raise

        def it_returns_platform_client_in_oauth_mode(configured_billing_stripe):
            import stripe

            account = StripeAccountFactory()
            client = account.get_stripe_client()
            assert isinstance(client, stripe.StripeClient)

        def it_returns_guild_scoped_client_in_direct_keys_mode():
            import stripe

            from tests.billing.factories import DirectKeysStripeAccountFactory

            account = DirectKeysStripeAccountFactory(direct_secret_key="sk_test_perguild")
            client = account.get_stripe_client()
            assert isinstance(client, stripe.StripeClient)

        def it_raises_if_direct_keys_account_has_no_secret():
            from tests.billing.factories import DirectKeysStripeAccountFactory

            account = DirectKeysStripeAccountFactory(direct_secret_key="")
            with pytest.raises(ValueError, match="no secret key"):
                account.get_stripe_client()

    def describe_upsert_direct_keys():
        def it_creates_a_direct_keys_account():
            guild = GuildFactory(name="Ceramics")
            account = StripeAccount.upsert_direct_keys(
                guild,
                stripe_account_id="acct_direct_001",
                display_name="Ceramics Guild Stripe",
                secret_key="sk_test_xxx",
                publishable_key="pk_test_xxx",
                webhook_secret="whsec_xxx",
            )
            assert account.auth_mode == StripeAccount.AuthMode.DIRECT_KEYS
            assert account.stripe_account_id == "acct_direct_001"
            assert account.direct_secret_key == "sk_test_xxx"
            assert account.direct_publishable_key == "pk_test_xxx"
            assert account.direct_webhook_secret == "whsec_xxx"
            assert account.platform_fee_percent == Decimal("0.00")
            assert account.connected_at is not None

        def it_updates_an_existing_account():
            guild = GuildFactory()
            StripeAccount.upsert_direct_keys(
                guild,
                stripe_account_id="acct_v1",
                display_name="V1",
                secret_key="sk_test_v1",
                publishable_key="pk_test_v1",
                webhook_secret="",
            )
            updated = StripeAccount.upsert_direct_keys(
                guild,
                stripe_account_id="acct_v2",
                display_name="V2",
                secret_key="sk_test_v2",
                publishable_key="pk_test_v2",
                webhook_secret="whsec_v2",
            )
            assert StripeAccount.objects.filter(guild=guild).count() == 1
            assert updated.stripe_account_id == "acct_v2"
            assert updated.direct_webhook_secret == "whsec_v2"
