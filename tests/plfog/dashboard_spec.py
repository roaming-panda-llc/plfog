"""Tests for admin dashboard callback, snapshot view, and invite view."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.models import Invite
from membership.models import FundingSnapshot, Member
from tests.membership.factories import (
    GuildFactory,
    MemberFactory,
    MembershipPlanFactory,
    VotePreferenceFactory,
)

User = get_user_model()


@pytest.fixture()
def admin_client():
    user = User.objects.create_superuser(
        username="dash-admin",
        password="pass",
        email="dash@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def describe_dashboard_callback():
    def it_loads_admin_index(admin_client):
        resp = admin_client.get("/admin/")
        assert resp.status_code == 200
        assert "stats" in resp.context

    def it_shows_voting_stats(admin_client):
        plan = MembershipPlanFactory(monthly_price=Decimal("100.00"))
        g1, g2, g3 = GuildFactory(), GuildFactory(), GuildFactory()
        m1 = MemberFactory(membership_plan=plan)
        VotePreferenceFactory(member=m1, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        resp = admin_client.get("/admin/")
        stats = resp.context["stats"]

        assert stats["total_voters"] == 1
        assert stats["paying_voters"] == 1
        assert stats["projected_pool"] == 10
        assert len(stats["top_guilds"]) > 0

    def it_excludes_non_standard_members_from_paying_voters(admin_client):
        g1, g2, g3 = GuildFactory(), GuildFactory(), GuildFactory()
        standard = MemberFactory(member_type=Member.MemberType.STANDARD)
        work_trade = MemberFactory(member_type=Member.MemberType.WORK_TRADE)
        VotePreferenceFactory(member=standard, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        VotePreferenceFactory(member=work_trade, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        resp = admin_client.get("/admin/")
        stats = resp.context["stats"]

        assert stats["total_voters"] == 2
        assert stats["paying_voters"] == 1
        assert stats["projected_pool"] == 10

    def it_handles_no_votes(admin_client):
        resp = admin_client.get("/admin/")
        stats = resp.context["stats"]

        assert stats["total_voters"] == 0
        assert stats["participation_pct"] == 0
        assert stats["top_guilds"] == []

    def it_excludes_guilds_with_zero_points(admin_client):
        GuildFactory()  # active guild with no votes
        resp = admin_client.get("/admin/")
        stats = resp.context["stats"]

        assert stats["active_guilds"] == 1
        assert stats["top_guilds"] == []


@pytest.mark.django_db
def describe_take_snapshot_admin():
    def it_requires_staff(client):
        resp = client.post("/admin/take-snapshot/")
        assert resp.status_code == 302
        assert "/login" in resp.url or "/accounts/" in resp.url

    def it_creates_snapshot(admin_client):
        plan = MembershipPlanFactory(monthly_price=Decimal("100.00"))
        g1, g2, g3 = GuildFactory(), GuildFactory(), GuildFactory()
        m = MemberFactory(membership_plan=plan)
        VotePreferenceFactory(member=m, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        resp = admin_client.post("/admin/take-snapshot/")

        assert resp.status_code == 302
        assert FundingSnapshot.objects.count() == 1

    def it_warns_when_no_votes(admin_client):
        resp = admin_client.post("/admin/take-snapshot/")

        assert resp.status_code == 302
        assert FundingSnapshot.objects.count() == 0

    def it_rejects_get(admin_client):
        resp = admin_client.get("/admin/take-snapshot/")
        assert resp.status_code == 405


@pytest.mark.django_db
def describe_invite_member_view():
    def it_requires_staff(client):
        resp = client.get("/admin/membership/member/invite/")
        assert resp.status_code == 302
        assert "/login" in resp.url or "/accounts/" in resp.url

    def it_renders_form_on_get(admin_client):
        resp = admin_client.get("/admin/membership/member/invite/")
        assert resp.status_code == 200
        assert "form" in resp.context

    def it_creates_invite_on_valid_post(admin_client):
        MembershipPlanFactory()
        with patch("core.models.send_mail"):
            resp = admin_client.post(
                "/admin/membership/member/invite/",
                data={"email": "new@example.com"},
            )
        assert resp.status_code == 302
        assert Invite.objects.filter(email="new@example.com").exists()
        member = Member.objects.get(email="new@example.com")
        assert member.status == Member.Status.INVITED

    def it_shows_error_for_existing_member(admin_client):
        MembershipPlanFactory()
        MemberFactory(email="exists@example.com", status=Member.Status.ACTIVE)
        resp = admin_client.post(
            "/admin/membership/member/invite/",
            data={"email": "exists@example.com"},
        )
        assert resp.status_code == 200  # re-renders form with errors

    def it_shows_error_when_no_plan_exists(admin_client):
        from membership.models import Member, MembershipPlan

        Member.objects.all().delete()
        MembershipPlan.objects.all().delete()
        resp = admin_client.post(
            "/admin/membership/member/invite/",
            data={"email": "noplan@example.com"},
        )
        assert resp.status_code == 200  # re-renders form with error message
