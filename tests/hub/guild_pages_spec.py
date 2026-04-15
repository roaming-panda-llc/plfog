"""BDD specs for guild pages views."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from tests.billing.factories import BillingSettingsFactory, ProductFactory, TabFactory
from tests.membership.factories import GuildFactory, MembershipPlanFactory


def _linked_user(client: Client, *, username: str = "u1", guild=None) -> tuple:
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

    def it_shows_no_products_placeholder_when_empty(client: Client):
        User.objects.create_user(username="v5", password="pass")
        guild = GuildFactory()
        client.login(username="v5", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"No products listed yet" in response.content

    def describe_product_cards():
        def it_shows_add_to_cart_button_when_member_can_add(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            ProductFactory(guild=guild, name="Laser Time")
            _linked_user(client)
            response = client.get(f"/guilds/{guild.pk}/")
            assert b"Add to Cart" in response.content

        def it_hides_add_button_when_no_payment_method(client: Client):
            MembershipPlanFactory()
            guild = GuildFactory()
            ProductFactory(guild=guild)
            user = User.objects.create_user(username="nocard_grid", password="pass")
            TabFactory(member=user.member, stripe_payment_method_id="")
            client.login(username="nocard_grid", password="pass")
            response = client.get(f"/guilds/{guild.pk}/")
            assert b"Add to Cart" not in response.content
            assert b"saved payment method" in response.content

    def describe_member_none_branches():
        def it_renders_without_cart_when_user_has_no_member(client: Client):
            guild = GuildFactory()
            user = User.objects.create_user(username="nomember", password="pass")
            from membership.models import Member

            Member.objects.filter(user=user).delete()
            client.login(username="nomember", password="pass")

            response = client.get(f"/guilds/{guild.pk}/")

            assert response.status_code == 200
            assert response.context["tab"] is None
