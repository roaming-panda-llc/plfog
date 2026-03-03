"""BDD-style tests for the member dashboard view."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from membership.models import Guild, Member, MembershipPlan
from outreach.models import Event

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture()
def user():
    return User.objects.create_user(
        username="dashuser",
        email="dash@example.com",
        password="testpass123",
    )


@pytest.fixture()
def logged_in_client(client, user):
    client.force_login(user)
    return client


def describe_dashboard_access():
    def it_redirects_anonymous_users(client):
        response = client.get(reverse("dashboard"))
        assert response.status_code == 302
        assert "login" in response["Location"]

    def it_returns_200_for_authenticated_user(logged_in_client):
        response = logged_in_client.get(reverse("dashboard"))
        assert response.status_code == 200

    def it_uses_dashboard_template(logged_in_client):
        response = logged_in_client.get(reverse("dashboard"))
        assert "membership/dashboard.html" in [t.name for t in response.templates]

    def it_includes_all_context_keys(logged_in_client):
        response = logged_in_client.get(reverse("dashboard"))
        assert "my_votes" in response.context
        assert "my_favorites" in response.context
        assert "upcoming_events" in response.context
        assert "upcoming_classes" in response.context
        assert "upcoming_orientations" in response.context
        assert "notifications" in response.context

    def it_renders_calendar_and_sidebar_elements(logged_in_client):
        response = logged_in_client.get(reverse("dashboard"))
        content = response.content.decode()
        assert 'id="dashboard-calendar"' in content
        assert "Activity Feed" in content
        assert "My Guilds" in content


def describe_dashboard_notifications():
    def it_builds_notification_from_upcoming_published_event(logged_in_client, user):
        guild = Guild.objects.create(name="Woodshop", slug="woodshop")
        now = timezone.now()
        Event.objects.create(
            name="Lathe Demo",
            description="Learn the lathe",
            starts_at=now + timezone.timedelta(days=3),
            ends_at=now + timezone.timedelta(days=3, hours=2),
            guild=guild,
            is_published=True,
            created_by=user,
        )
        response = logged_in_client.get(reverse("dashboard"))
        assert response.status_code == 200
        notifications = response.context["notifications"]
        messages = [n["message"] for n in notifications]
        assert any("Lathe Demo" in m for m in messages)

    def it_excludes_unpublished_events(logged_in_client, user):
        guild = Guild.objects.create(name="Metalwork", slug="metalwork")
        now = timezone.now()
        Event.objects.create(
            name="Secret Weld",
            description="Draft event",
            starts_at=now + timezone.timedelta(days=1),
            ends_at=now + timezone.timedelta(days=1, hours=1),
            guild=guild,
            is_published=False,
            created_by=user,
        )
        response = logged_in_client.get(reverse("dashboard"))
        notifications = response.context["notifications"]
        assert not any("Secret Weld" in n["message"] for n in notifications)

    def it_uses_past_lives_name_for_unguilded_event(logged_in_client, user):
        now = timezone.now()
        Event.objects.create(
            name="Unguilded Event",
            description="No guild",
            starts_at=now + timezone.timedelta(days=2),
            ends_at=now + timezone.timedelta(days=2, hours=1),
            guild=None,
            is_published=True,
            created_by=user,
        )
        response = logged_in_client.get(reverse("dashboard"))
        notifications = response.context["notifications"]
        unguilded = [n for n in notifications if "Unguilded Event" in n["message"]]
        assert len(unguilded) == 1
        assert unguilded[0]["guild_name"] == "Past Lives"

    def it_shows_my_guilds_for_voting_member(logged_in_client, user):
        from membership.models import GuildVote

        plan = MembershipPlan.objects.create(name="Standard", monthly_price="50.00")
        member = Member.objects.create(
            user=user,
            full_legal_name="Dash User",
            membership_plan=plan,
        )
        guild = Guild.objects.create(name="Ceramics Guild", slug="ceramics-guild")
        GuildVote.objects.create(member=member, guild=guild, priority=1)
        response = logged_in_client.get(reverse("dashboard"))
        assert b"Ceramics Guild" in response.content
