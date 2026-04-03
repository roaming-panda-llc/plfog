"""BDD specs for guild pages views."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from billing.models import Product as BillingProduct
from hub.forms import GuildPageForm, GuildProductForm
from membership.models import Guild
from tests.billing.factories import ProductFactory
from tests.membership.factories import GuildFactory, MemberFactory


@pytest.mark.django_db
def describe_guild_about_field():
    def it_defaults_to_empty_string():
        guild = GuildFactory()
        assert guild.about == ""

    def it_stores_about_text():
        guild = GuildFactory(about="Welcome to our guild!")
        guild.refresh_from_db()
        assert guild.about == "Welcome to our guild!"


@pytest.mark.django_db
def describe_GuildPageForm():
    def it_is_valid_with_about_text():
        guild = GuildFactory(about="Old text")
        form = GuildPageForm(data={"about": "New text"}, instance=guild)
        assert form.is_valid()

    def it_is_valid_with_blank_about():
        guild = GuildFactory()
        form = GuildPageForm(data={"about": ""}, instance=guild)
        assert form.is_valid()

    def it_saves_about_text():
        guild = GuildFactory(about="Old")
        form = GuildPageForm(data={"about": "Updated"}, instance=guild)
        assert form.is_valid()
        form.save()
        guild.refresh_from_db()
        assert guild.about == "Updated"


@pytest.mark.django_db
def describe_GuildProductForm():
    def it_is_valid_with_name_and_positive_price():
        form = GuildProductForm(data={"name": "Wood Laser", "price": "25.00"})
        assert form.is_valid()

    def it_rejects_zero_price():
        form = GuildProductForm(data={"name": "Freebie", "price": "0.00"})
        assert not form.is_valid()
        assert "price" in form.errors

    def it_rejects_negative_price():
        form = GuildProductForm(data={"name": "Bad", "price": "-5.00"})
        assert not form.is_valid()
        assert "price" in form.errors


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

    def it_shows_edit_button_for_guild_lead(client: Client):
        lead_user = User.objects.create_user(username="gl", password="pass")
        lead_member = lead_user.member
        guild = GuildFactory(guild_lead=lead_member)
        client.login(username="gl", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Edit Guild Page" in response.content

    def it_hides_edit_button_for_non_lead(client: Client):
        User.objects.create_user(username="other", password="pass")
        guild = GuildFactory()
        client.login(username="other", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Edit Guild Page" not in response.content


@pytest.mark.django_db
def describe_guild_edit():
    def _lead_client_and_guild() -> tuple[Client, Guild, User]:
        lead_user = User.objects.create_user(username="lead2", password="pass")
        lead_member = lead_user.member
        guild = GuildFactory(guild_lead=lead_member, about="Old text")
        client = Client()
        client.login(username="lead2", password="pass")
        return client, guild, lead_user

    def it_requires_login(client: Client):
        guild = GuildFactory()
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def it_returns_403_for_non_lead(client: Client):
        User.objects.create_user(username="rando", password="pass")
        guild = GuildFactory()
        client.login(username="rando", password="pass")
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert response.status_code == 403

    def it_renders_form_with_current_about_text():
        client, guild, _ = _lead_client_and_guild()
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert response.status_code == 200
        assert b"Old text" in response.content

    def it_saves_about_and_redirects():
        client, guild, _ = _lead_client_and_guild()
        response = client.post(f"/guilds/{guild.pk}/edit/", {"about": "New announcement"})
        assert response.status_code == 302
        assert response["Location"] == f"/guilds/{guild.pk}/edit/"
        guild.refresh_from_db()
        assert guild.about == "New announcement"

    def it_shows_active_products_in_table():
        client, guild, _ = _lead_client_and_guild()
        ProductFactory(guild=guild, name="Laser Session", is_active=True)
        ProductFactory(guild=guild, name="Old Product", is_active=False)
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert b"Laser Session" in response.content
        assert b"Old Product" not in response.content

    def it_adds_product_on_post():
        client, guild, _ = _lead_client_and_guild()
        client.post(
            f"/guilds/{guild.pk}/edit/",
            {"about": guild.about, "add_product": "1", "name": "CNC Hour", "price": "30.00"},
        )
        assert BillingProduct.objects.filter(guild=guild, name="CNC Hour", price="30.00").exists()

    def it_rejects_product_with_zero_price():
        client, guild, _ = _lead_client_and_guild()
        response = client.post(
            f"/guilds/{guild.pk}/edit/",
            {"about": guild.about, "add_product": "1", "name": "Free", "price": "0.00"},
        )
        assert response.status_code == 200
        assert b"greater than zero" in response.content


@pytest.mark.django_db
def describe_guild_product_edit():
    def _setup() -> tuple[Client, Guild, BillingProduct]:
        lead_user = User.objects.create_user(username="lead3", password="pass")
        lead_member = lead_user.member
        guild = GuildFactory(guild_lead=lead_member)
        product = ProductFactory(guild=guild, name="Old Name", price="15.00")
        client = Client()
        client.login(username="lead3", password="pass")
        return client, guild, product

    def it_requires_login(client: Client):
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/edit/")
        assert response.status_code == 302

    def it_returns_403_for_non_lead(client: Client):
        User.objects.create_user(username="rando2", password="pass")
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        client.login(username="rando2", password="pass")
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/edit/")
        assert response.status_code == 403

    def it_returns_404_for_product_not_in_guild():
        client, guild, _ = _setup()
        other_product = ProductFactory()
        response = client.get(f"/guilds/{guild.pk}/products/{other_product.pk}/edit/")
        assert response.status_code == 404

    def it_renders_form_prefilled():
        client, guild, product = _setup()
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/edit/")
        assert response.status_code == 200
        assert b"Old Name" in response.content

    def it_saves_and_redirects():
        client, guild, product = _setup()
        response = client.post(
            f"/guilds/{guild.pk}/products/{product.pk}/edit/",
            {"name": "New Name", "price": "20.00"},
        )
        assert response.status_code == 302
        assert response["Location"] == f"/guilds/{guild.pk}/edit/"
        product.refresh_from_db()
        assert product.name == "New Name"
        assert product.price == Decimal("20.00")


@pytest.mark.django_db
def describe_guild_product_remove():
    def _setup() -> tuple[Client, Guild, BillingProduct]:
        lead_user = User.objects.create_user(username="lead4", password="pass")
        lead_member = lead_user.member
        guild = GuildFactory(guild_lead=lead_member)
        product = ProductFactory(guild=guild, is_active=True)
        client = Client()
        client.login(username="lead4", password="pass")
        return client, guild, product

    def it_returns_405_on_get():
        client, guild, product = _setup()
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        assert response.status_code == 405

    def it_returns_403_for_non_lead(client: Client):
        User.objects.create_user(username="rando3", password="pass")
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        client.login(username="rando3", password="pass")
        response = client.post(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        assert response.status_code == 403

    def it_returns_404_for_product_not_in_guild():
        client, guild, _ = _setup()
        other_product = ProductFactory()
        response = client.post(f"/guilds/{guild.pk}/products/{other_product.pk}/remove/")
        assert response.status_code == 404

    def it_sets_is_active_false():
        client, guild, product = _setup()
        client.post(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        product.refresh_from_db()
        assert product.is_active is False

    def it_redirects_to_edit_page():
        client, guild, product = _setup()
        response = client.post(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        assert response.status_code == 302
        assert response["Location"] == f"/guilds/{guild.pk}/edit/"
