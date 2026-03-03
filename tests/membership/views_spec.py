"""BDD-style tests for guild page views."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from membership.models import Guild, Member, MembershipPlan

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture()
def guild() -> Guild:
    return Guild.objects.create(name="Woodworkers", slug="woodworkers")


@pytest.fixture()
def member_user():
    user = User.objects.create_user(username="member1", password="test")
    plan = MembershipPlan.objects.create(name="Full-Time", monthly_price=300)
    Member.objects.create(
        user=user,
        full_legal_name="Test Member",
        preferred_name="Test",
        email="test@example.com",
        phone="503-555-0001",
        billing_name="Test Member",
        emergency_contact_name="EC",
        emergency_contact_phone="503-555-9999",
        emergency_contact_relationship="Partner",
        membership_plan=plan,
    )
    return user


def describe_guild_list():
    def it_returns_200(client, guild):
        response = client.get(reverse("guild_list"))
        assert response.status_code == 200

    def it_contains_guild_name(client, guild):
        response = client.get(reverse("guild_list"))
        assert guild.name in response.content.decode()


def describe_guild_detail():
    def it_returns_200(client, guild):
        response = client.get(reverse("guild_detail", args=[guild.slug]))
        assert response.status_code == 200

    def it_returns_404_for_missing_guild(client):
        response = client.get(reverse("guild_detail", args=["nonexistent"]))
        assert response.status_code == 404


def describe_dashboard():
    def it_redirects_anonymous_users(client):
        response = client.get(reverse("dashboard"))
        assert response.status_code == 302

    def it_returns_200_for_authenticated_users(client, member_user):
        client.login(username="member1", password="test")
        response = client.get(reverse("dashboard"))
        assert response.status_code == 200
