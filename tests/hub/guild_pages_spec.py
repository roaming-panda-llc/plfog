"""BDD specs for guild pages views."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client

from billing.exceptions import TabLimitExceededError, TabLockedError
from billing.models import Product, TabEntry
from tests.billing.factories import BillingSettingsFactory, ProductFactory, TabFactory
from tests.membership.factories import GuildFactory, MembershipPlanFactory


def _linked_user(client: Client, *, username: str = "u1", guild=None) -> tuple[User, TabEntry]:
    """Create a user + auto-linked Member + Tab (with a saved card) + login."""
    MembershipPlanFactory()
    user = User.objects.create_user(username=username, password="pass")
    member = user.member
    tab = TabFactory(member=member, stripe_payment_method_id="pm_test", stripe_customer_id="cus_test")
    client.login(username=username, password="pass")
    return user, tab


@pytest.mark.django_db
def describe_guild_detail():
    def it_requires_login(client: Client):
        guild = GuildFactory()
        response = client.get(f"/guilds/{guild.pk}/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def it_shows_guild_name(client: Client):
        User.objects.create_user(username="viewer", password="pass")
        guild = GuildFactory(name="Woodworking Guild")
        client.login(username="viewer", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert response.status_code == 200
        assert b"Woodworking Guild" in response.content

    def it_shows_about_text(client: Client):
        User.objects.create_user(username="v2", password="pass")
        guild = GuildFactory(about="We love wood.")
        client.login(username="v2", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"We love wood." in response.content

    def it_shows_placeholder_when_about_is_blank(client: Client):
        User.objects.create_user(username="v3", password="pass")
        guild = GuildFactory(about="")
        client.login(username="v3", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Nothing here yet" in response.content

    def it_shows_active_products_only(client: Client):
        User.objects.create_user(username="v4", password="pass")
        guild = GuildFactory()
        ProductFactory(guild=guild, name="Laser Cutter", is_active=True)
        ProductFactory(guild=guild, name="Hidden", is_active=False)
        client.login(username="v4", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Laser Cutter" in response.content
        assert b"Hidden" not in response.content

    def it_shows_no_products_placeholder_when_empty(client: Client):
        User.objects.create_user(username="v5", password="pass")
        guild = GuildFactory()
        client.login(username="v5", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"No products listed yet" in response.content

    def describe_product_quick_add():
        def it_adds_a_product_to_the_tab_on_post(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            product = ProductFactory(guild=guild, price=Decimal("10.00"))
            _user, tab = _linked_user(client)

            response = client.post(f"/guilds/{guild.pk}/", {"product_pk": product.pk})

            assert response.status_code == 302
            assert response.url == f"/guilds/{guild.pk}/"
            entry = TabEntry.objects.get(tab=tab)
            assert entry.description == product.name
            assert entry.amount == product.price
            assert entry.guild == guild
            assert entry.admin_percent == Decimal("20.00")

        def it_rejects_unknown_product(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            _user, tab = _linked_user(client)

            response = client.post(f"/guilds/{guild.pk}/", {"product_pk": "99999"})

            assert response.status_code == 302
            assert tab.entries.count() == 0

        def it_shows_error_when_no_payment_method(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            product = ProductFactory(guild=guild, price=Decimal("10.00"))
            MembershipPlanFactory()
            user = User.objects.create_user(username="nocard_add", password="pass")
            tab = TabFactory(member=user.member, stripe_payment_method_id="")
            client.login(username="nocard_add", password="pass")

            response = client.post(f"/guilds/{guild.pk}/", {"product_pk": product.pk})

            assert response.status_code == 302
            assert tab.entries.count() == 0

        def it_shows_error_when_tab_is_locked(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            product = ProductFactory(guild=guild, price=Decimal("10.00"))
            _user, tab = _linked_user(client)

            with patch("billing.models.Tab.add_entry", side_effect=TabLockedError("locked")):
                response = client.post(f"/guilds/{guild.pk}/", {"product_pk": product.pk})

            assert response.status_code == 302
            assert response.url == f"/guilds/{guild.pk}/"

        def it_shows_error_when_tab_limit_exceeded(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            product = ProductFactory(guild=guild, price=Decimal("10.00"))
            _user, tab = _linked_user(client)

            with patch("billing.models.Tab.add_entry", side_effect=TabLimitExceededError("exceeded")):
                response = client.post(f"/guilds/{guild.pk}/", {"product_pk": product.pk})

            assert response.status_code == 302
            assert response.url == f"/guilds/{guild.pk}/"

    def describe_eyop_form():
        def it_adds_a_custom_item_with_the_guild_snapshot(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            _user, tab = _linked_user(client, username="eyop1")

            response = client.post(
                f"/guilds/{guild.pk}/",
                {"description": "Donation", "amount": "3.50"},
            )

            assert response.status_code == 302
            entry = TabEntry.objects.get(tab=tab)
            assert entry.description == "Donation"
            assert entry.amount == Decimal("3.50")
            assert entry.guild == guild
            # Member can't override the split — locked to site default
            assert entry.admin_percent == Decimal("20.00")
            assert entry.split_mode == Product.SplitMode.SINGLE_GUILD

        def it_shows_eyop_form_when_member_has_payment_method(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            _linked_user(client, username="eyop2")
            response = client.get(f"/guilds/{guild.pk}/")
            assert response.status_code == 200
            assert b"Enter Your Own Price" in response.content
            assert b"Add to tab" not in response.content or b"Add Item" in response.content

        def it_hides_eyop_form_for_member_without_a_card(client: Client):
            MembershipPlanFactory()
            guild = GuildFactory()
            user = User.objects.create_user(username="nocard", password="pass")
            TabFactory(member=user.member, stripe_payment_method_id="")
            client.login(username="nocard", password="pass")
            response = client.get(f"/guilds/{guild.pk}/")
            assert response.status_code == 200
            assert b"saved payment method" in response.content

        def it_shows_error_when_no_payment_method_on_eyop_post(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            MembershipPlanFactory()
            user = User.objects.create_user(username="nocard_eyop", password="pass")
            TabFactory(member=user.member, stripe_payment_method_id="")
            client.login(username="nocard_eyop", password="pass")

            response = client.post(
                f"/guilds/{guild.pk}/",
                {"description": "Custom item", "amount": "5.00"},
            )

            assert response.status_code == 200
            assert b"payment method" in response.content.lower()

        def it_shows_error_when_tab_is_locked_on_eyop_post(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            _user, tab = _linked_user(client, username="eyoplocked")

            with patch("billing.models.Tab.add_entry", side_effect=TabLockedError("locked")):
                response = client.post(
                    f"/guilds/{guild.pk}/",
                    {"description": "Custom item", "amount": "5.00"},
                )

            assert response.status_code == 200
            assert b"locked" in response.content.lower()

        def it_shows_error_when_tab_limit_exceeded_on_eyop_post(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            _user, tab = _linked_user(client, username="eyoplimit")

            with patch("billing.models.Tab.add_entry", side_effect=TabLimitExceededError("exceeded")):
                response = client.post(
                    f"/guilds/{guild.pk}/",
                    {"description": "Custom item", "amount": "5.00"},
                )

            assert response.status_code == 200
            assert b"limit" in response.content.lower()

        def it_rerenders_when_eyop_form_is_invalid(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            _user, tab = _linked_user(client, username="eyopinvalid")

            # Post with missing amount — form is invalid, view re-renders
            response = client.post(
                f"/guilds/{guild.pk}/",
                {"description": "No amount here"},
            )

            assert response.status_code == 200

    def describe_member_none_branches():
        def it_renders_without_eyop_form_when_user_has_no_member(client: Client):
            # A plain User with no linked Member (unlinked account)
            guild = GuildFactory()
            user = User.objects.create_user(username="nomember", password="pass")
            # Remove the auto-created member if present (some signals create one)
            from membership.models import Member

            Member.objects.filter(user=user).delete()
            client.login(username="nomember", password="pass")

            response = client.get(f"/guilds/{guild.pk}/")

            # Page still renders, but no eyop form shown
            assert response.status_code == 200
            assert response.context["eyop_form"] is None
