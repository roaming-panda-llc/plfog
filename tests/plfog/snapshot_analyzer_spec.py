"""Specs for the unified snapshot analyzer views (draft + stored modes).

See docs/superpowers/plans/2026-04-09-funding-snapshot-overhaul.md.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from membership.models import FundingSnapshot, Member
from tests.membership.factories import (
    GuildFactory,
    MemberFactory,
    VotePreferenceFactory,
)

User = get_user_model()


@pytest.fixture()
def admin_client(db):
    user = User.objects.create_superuser(
        username="snap-admin",
        password="pass",
        email="snap-admin@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture()
def three_guilds(db):
    return GuildFactory(name="Ceramics"), GuildFactory(name="Textiles"), GuildFactory(name="Wood")


@pytest.fixture()
def votes_with_mixed_roles(three_guilds):
    """Paying standard member + non-paying guild officer, each with a vote."""
    g1, g2, g3 = three_guilds
    paying = MemberFactory(
        member_type=Member.MemberType.STANDARD,
        fog_role=Member.FogRole.MEMBER,
        full_legal_name="Alice Standard",
    )
    officer = MemberFactory(
        member_type=Member.MemberType.WORK_TRADE,
        fog_role=Member.FogRole.GUILD_OFFICER,
        full_legal_name="Oscar Officer",
    )
    VotePreferenceFactory(member=paying, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
    VotePreferenceFactory(member=officer, guild_1st=g2, guild_2nd=g3, guild_3rd=g1)
    return paying, officer


# ---------------------------------------------------------------------------
# Draft mode — /admin/snapshots/draft/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_snapshot_draft_view():
    def it_requires_staff(client):
        resp = client.get("/admin/snapshots/draft/")
        assert resp.status_code == 302

    def it_renders_live_vote_data_without_creating_a_snapshot(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/")
        assert resp.status_code == 200
        assert FundingSnapshot.objects.count() == 0
        assert resp.context["mode"] == "draft"

    def it_applies_member_type_filter_to_live_data(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/?member_type=work_trade")
        assert resp.status_code == 200
        assert resp.context["total_count"] == 1
        assert resp.context["paying_count"] == 0

    def it_applies_fog_role_filter_to_live_data(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/?fog_role=guild_officer")
        assert resp.status_code == 200
        assert resp.context["total_count"] == 1

    def it_applies_is_paying_filter(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/?is_paying=yes")
        assert resp.status_code == 200
        assert resp.context["total_count"] == 1
        assert resp.context["paying_count"] == 1

    def it_defaults_minimum_pool_to_1000(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/")
        assert resp.context["minimum_pool"] == Decimal("1000")

    def it_accepts_custom_minimum_pool_via_get(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/?minimum_pool=500")
        assert resp.context["minimum_pool"] == Decimal("500")

    def it_shows_individual_votes(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/")
        body = resp.content.decode()
        assert "Alice Standard" in body
        assert "Oscar Officer" in body

    def it_falls_back_to_default_minimum_pool_on_invalid_input(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/?minimum_pool=abc")
        assert resp.context["minimum_pool"] == Decimal("1000")

    def it_falls_back_to_default_minimum_pool_on_negative_input(admin_client, votes_with_mixed_roles):
        resp = admin_client.get("/admin/snapshots/draft/?minimum_pool=-100")
        assert resp.context["minimum_pool"] == Decimal("1000")


# ---------------------------------------------------------------------------
# Stored mode — /admin/snapshots/<pk>/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_snapshot_detail_view():
    def it_requires_staff(client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = client.get(f"/admin/snapshots/{snap.pk}/")
        assert resp.status_code == 302

    def it_renders_stored_snapshot_data(admin_client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = admin_client.get(f"/admin/snapshots/{snap.pk}/")
        assert resp.status_code == 200
        assert resp.context["mode"] == "stored"
        assert resp.context["snapshot"] == snap

    def it_filters_stored_raw_votes_by_member_type(admin_client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = admin_client.get(f"/admin/snapshots/{snap.pk}/?member_type=standard")
        assert resp.context["total_count"] == 1
        assert resp.context["paying_count"] == 1

    def it_filters_stored_raw_votes_by_fog_role(admin_client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = admin_client.get(f"/admin/snapshots/{snap.pk}/?fog_role=guild_officer")
        assert resp.context["total_count"] == 1

    def it_filters_stored_raw_votes_by_is_paying(admin_client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = admin_client.get(f"/admin/snapshots/{snap.pk}/?is_paying=no")
        assert resp.context["total_count"] == 1
        assert resp.context["non_paying_count"] == 1

    def it_shows_individual_vote_rows_with_names(admin_client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = admin_client.get(f"/admin/snapshots/{snap.pk}/")
        body = resp.content.decode()
        assert "Alice Standard" in body
        assert "Oscar Officer" in body

    def it_gracefully_handles_legacy_snapshot_without_raw_votes(admin_client):
        snap = FundingSnapshot.objects.create(
            cycle_label="Legacy",
            contributor_count=5,
            funding_pool=Decimal("50.00"),
            minimum_pool=Decimal("0.00"),
            raw_votes=[],
            results={"total_pool": "50.00", "votes_cast": 5, "results": []},
        )
        resp = admin_client.get(f"/admin/snapshots/{snap.pk}/")
        assert resp.status_code == 200
        assert resp.context["is_legacy"] is True
        body = resp.content.decode()
        assert "before per-vote history was stored" in body


# ---------------------------------------------------------------------------
# Take (commit) endpoint — /admin/snapshots/take/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_snapshot_take_endpoint():
    def it_commits_full_unfiltered_snapshot(admin_client, votes_with_mixed_roles):
        resp = admin_client.post(
            "/admin/snapshots/take/",
            {"title": "Test", "minimum_pool": "1000"},
        )
        assert resp.status_code == 302
        snap = FundingSnapshot.objects.first()
        assert snap is not None
        assert snap.cycle_label == "Test"
        assert snap.funding_pool == Decimal("1000.00")
        # Both voters captured (not affected by any previous filter state)
        assert len(snap.raw_votes) == 2

    def it_stores_title_and_minimum_pool_from_post(admin_client, votes_with_mixed_roles):
        admin_client.post(
            "/admin/snapshots/take/",
            {"title": "Q2 2026", "minimum_pool": "500"},
        )
        snap = FundingSnapshot.objects.first()
        assert snap is not None
        assert snap.cycle_label == "Q2 2026"
        assert snap.minimum_pool == Decimal("500.00")

    def it_redirects_to_detail_on_success(admin_client, votes_with_mixed_roles):
        resp = admin_client.post(
            "/admin/snapshots/take/",
            {"title": "Redirect Test", "minimum_pool": "1000"},
        )
        snap = FundingSnapshot.objects.first()
        assert resp.status_code == 302
        assert f"/admin/snapshots/{snap.pk}/" in resp.url

    def it_warns_and_redirects_when_no_votes(admin_client):
        resp = admin_client.post(
            "/admin/snapshots/take/",
            {"title": "Empty", "minimum_pool": "1000"},
        )
        assert resp.status_code == 302
        assert FundingSnapshot.objects.count() == 0

    def it_rejects_non_staff(client, votes_with_mixed_roles):
        resp = client.post("/admin/snapshots/take/")
        assert resp.status_code == 302

    def it_rejects_get(admin_client):
        resp = admin_client.get("/admin/snapshots/take/")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Delete endpoint — /admin/snapshots/<pk>/delete/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_snapshot_delete_endpoint():
    def it_deletes_the_snapshot_and_redirects_to_list(admin_client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        pk = snap.pk
        resp = admin_client.post(f"/admin/snapshots/{pk}/delete/")
        assert resp.status_code == 302
        assert not FundingSnapshot.objects.filter(pk=pk).exists()

    def it_rejects_get(admin_client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = admin_client.get(f"/admin/snapshots/{snap.pk}/delete/")
        assert resp.status_code == 405

    def it_rejects_non_staff(client, votes_with_mixed_roles):
        snap = FundingSnapshot.take(minimum_pool=1000)
        resp = client.post(f"/admin/snapshots/{snap.pk}/delete/")
        assert resp.status_code == 302

    def it_returns_404_for_nonexistent_pk(admin_client):
        resp = admin_client.post("/admin/snapshots/999999/delete/")
        assert resp.status_code == 404
