"""Tests for enhanced Guild fields and new Guild-related models."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client

from tests.membership.factories import (
    GuildDocumentFactory,
    GuildFactory,
    GuildMembershipFactory,
    GuildWishlistItemFactory,
)
from tests.core.factories import UserFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Guild slug enhancements
# ---------------------------------------------------------------------------


def describe_Guild_slug():
    def it_auto_generates_slug_from_name():
        guild = GuildFactory(name="Ceramics Guild")
        assert guild.slug == "ceramics-guild"

    def it_preserves_existing_slug():
        guild = GuildFactory(name="Woodworking Guild", slug="custom-slug")
        assert guild.slug == "custom-slug"

    def it_generates_slug_for_name_with_spaces():
        guild = GuildFactory(name="3D Printing Guild")
        assert guild.slug == "3d-printing-guild"

    def it_does_not_overwrite_slug_on_resave():
        guild = GuildFactory(name="Glass Guild")
        original_slug = guild.slug
        guild.notes = "Updated notes"
        guild.save()
        guild.refresh_from_db()
        assert guild.slug == original_slug


def describe_Guild_new_fields():
    def it_has_intro_field():
        guild = GuildFactory(name="Textiles Guild", intro="We make textiles.")
        guild.refresh_from_db()
        assert guild.intro == "We make textiles."

    def it_has_description_field():
        guild = GuildFactory(name="Leather Guild", description="Detailed description of the leather guild.")
        guild.refresh_from_db()
        assert guild.description == "Detailed description of the leather guild."

    def it_defaults_is_active_to_true():
        guild = GuildFactory(name="Active Guild")
        assert guild.is_active is True

    def it_can_set_is_active_to_false():
        guild = GuildFactory(name="Inactive Guild", is_active=False)
        assert guild.is_active is False

    def it_has_icon_field():
        guild = GuildFactory(name="Icon Guild", icon="fa-hammer")
        guild.refresh_from_db()
        assert guild.icon == "fa-hammer"


# ---------------------------------------------------------------------------
# GuildMembership
# ---------------------------------------------------------------------------


def describe_GuildMembership():
    def it_links_user_to_guild():
        user = UserFactory()
        guild = GuildFactory(name="Membership Test Guild")
        membership = GuildMembershipFactory(guild=guild, user=user)
        assert membership.guild == guild
        assert membership.user == user

    def it_defaults_is_lead_to_false():
        membership = GuildMembershipFactory()
        assert membership.is_lead is False

    def it_can_set_is_lead_to_true():
        membership = GuildMembershipFactory(is_lead=True)
        assert membership.is_lead is True

    def it_has_str_representation_for_member():
        user = UserFactory(username="testuser")
        guild = GuildFactory(name="Test Guild")
        membership = GuildMembershipFactory(guild=guild, user=user, is_lead=False)
        assert str(membership) == "testuser - Test Guild (Member)"

    def it_has_str_representation_for_lead():
        user = UserFactory(username="leaduser")
        guild = GuildFactory(name="Lead Guild")
        membership = GuildMembershipFactory(guild=guild, user=user, is_lead=True)
        assert str(membership) == "leaduser - Lead Guild (Lead)"

    def it_records_joined_at_automatically():
        membership = GuildMembershipFactory()
        assert membership.joined_at is not None

    def it_enforces_unique_together_guild_and_user():
        user = UserFactory()
        guild = GuildFactory(name="Unique Membership Guild")
        GuildMembershipFactory(guild=guild, user=user)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                GuildMembershipFactory(guild=guild, user=user)

    def it_allows_same_user_in_different_guilds():
        user = UserFactory()
        guild_a = GuildFactory(name="Guild Alpha")
        guild_b = GuildFactory(name="Guild Beta")
        mem_a = GuildMembershipFactory(guild=guild_a, user=user)
        mem_b = GuildMembershipFactory(guild=guild_b, user=user)
        assert mem_a.pk != mem_b.pk


# ---------------------------------------------------------------------------
# GuildDocument
# ---------------------------------------------------------------------------


def describe_GuildDocument():
    def it_has_str_representation():
        doc = GuildDocumentFactory(name="Safety Guidelines")
        assert str(doc) == "Safety Guidelines"

    def it_belongs_to_guild():
        guild = GuildFactory(name="Document Guild")
        doc = GuildDocumentFactory(guild=guild, name="Rules Doc")
        assert doc.guild == guild

    def it_tracks_uploader():
        user = UserFactory()
        doc = GuildDocumentFactory(uploaded_by=user)
        assert doc.uploaded_by == user

    def it_allows_null_uploader():
        doc = GuildDocumentFactory(uploaded_by=None)
        assert doc.uploaded_by is None

    def it_has_created_at():
        doc = GuildDocumentFactory()
        assert doc.created_at is not None


# ---------------------------------------------------------------------------
# GuildWishlistItem
# ---------------------------------------------------------------------------


def describe_GuildWishlistItem():
    def it_has_str_representation():
        item = GuildWishlistItemFactory(name="Laser Cutter")
        assert str(item) == "Laser Cutter"

    def it_defaults_is_fulfilled_to_false():
        item = GuildWishlistItemFactory()
        assert item.is_fulfilled is False

    def it_can_be_marked_fulfilled():
        item = GuildWishlistItemFactory(is_fulfilled=True)
        assert item.is_fulfilled is True

    def it_belongs_to_guild():
        guild = GuildFactory(name="Wishlist Guild")
        item = GuildWishlistItemFactory(guild=guild, name="3D Printer")
        assert item.guild == guild

    def it_has_created_at():
        item = GuildWishlistItemFactory()
        assert item.created_at is not None


# ---------------------------------------------------------------------------
# Admin changelist HTTP tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="admin-enhance-test",
        password="admin-test-pw",
        email="admin-enhance@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


def describe_admin_guild_membership_views():
    def it_loads_changelist(admin_client):
        GuildMembershipFactory()
        resp = admin_client.get("/admin/membership/guildmembership/")
        assert resp.status_code == 200


def describe_admin_guild_document_views():
    def it_loads_changelist(admin_client):
        GuildDocumentFactory()
        resp = admin_client.get("/admin/membership/guilddocument/")
        assert resp.status_code == 200


def describe_admin_guild_wishlist_item_views():
    def it_loads_changelist(admin_client):
        GuildWishlistItemFactory()
        resp = admin_client.get("/admin/membership/guildwishlistitem/")
        assert resp.status_code == 200
