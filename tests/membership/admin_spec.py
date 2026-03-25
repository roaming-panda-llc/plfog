from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client

from django.utils import timezone

from membership.admin import (
    ActiveStatusFilter,
    FundingSnapshotAdmin,
    GuildAdmin,
    MemberAdmin,
    VotePreferenceAdmin,
)
from membership.models import FundingSnapshot, Guild, Member, VotePreference
from tests.membership.factories import (
    FundingSnapshotFactory,
    GuildFactory,
    MemberFactory,
    MembershipPlanFactory,
    VotePreferenceFactory,
)

User = get_user_model()


def describe_admin_registration():
    def it_registers_member():
        assert Member in admin.site._registry
        assert isinstance(admin.site._registry[Member], MemberAdmin)

    def it_registers_guild():
        assert Guild in admin.site._registry
        assert isinstance(admin.site._registry[Guild], GuildAdmin)

    def it_registers_vote_preference():
        assert VotePreference in admin.site._registry
        assert isinstance(admin.site._registry[VotePreference], VotePreferenceAdmin)

    def it_registers_funding_snapshot():
        assert FundingSnapshot in admin.site._registry
        assert isinstance(admin.site._registry[FundingSnapshot], FundingSnapshotAdmin)


def describe_MemberAdmin():
    def it_has_expected_list_display():
        member_admin = admin.site._registry[Member]
        assert member_admin.list_display == [
            "display_name",
            "email",
            "membership_plan",
            "status",
            "role",
            "join_date",
            "last_login_display",
        ]

    def it_has_expected_search_fields():
        member_admin = admin.site._registry[Member]
        assert member_admin.search_fields == [
            "full_legal_name",
            "preferred_name",
            "email",
        ]

    def it_has_expected_list_filter():
        member_admin = admin.site._registry[Member]
        assert member_admin.list_filter[0] is ActiveStatusFilter
        assert "role" in member_admin.list_filter
        assert "membership_plan" in member_admin.list_filter

    def it_has_list_per_page_set():
        member_admin = admin.site._registry[Member]
        assert member_admin.list_per_page == 100


@pytest.mark.django_db
def describe_admin_member_computed_fields():
    def it_displays_member_display_name():
        plan = MembershipPlanFactory(monthly_price=Decimal("75.00"))
        member = MemberFactory(
            full_legal_name="John Smith",
            preferred_name="Johnny",
            membership_plan=plan,
        )
        member_admin = admin.site._registry[Member]
        result = member_admin.display_name(member)
        assert result == "Johnny"

    def it_displays_last_login_never_when_no_user():
        member = MemberFactory(user=None)
        member_admin = admin.site._registry[Member]
        result = member_admin.last_login_display(member)
        assert "Never" in result

    def it_displays_last_login_never_when_user_never_logged_in():
        user = User.objects.create_user(username="nologin", password="test", email="nologin@example.com")
        member = user.member  # auto-created by signal
        member_admin = admin.site._registry[Member]
        result = member_admin.last_login_display(member)
        assert "Never" in result

    def it_displays_last_login_today():
        user = User.objects.create_user(username="today", password="test", email="today@example.com")
        user.last_login = timezone.now()
        user.save()
        member = user.member
        member_admin = admin.site._registry[Member]
        result = member_admin.last_login_display(member)
        assert result == "Today"

    def it_displays_last_login_yesterday():
        user = User.objects.create_user(username="yesterday", password="test", email="yesterday@example.com")
        user.last_login = timezone.now() - timezone.timedelta(days=1)
        user.save()
        member = user.member
        member_admin = admin.site._registry[Member]
        result = member_admin.last_login_display(member)
        assert result == "Yesterday"

    def it_displays_last_login_days_ago():
        user = User.objects.create_user(username="daysago", password="test", email="daysago@example.com")
        user.last_login = timezone.now() - timezone.timedelta(days=15)
        user.save()
        member = user.member
        member_admin = admin.site._registry[Member]
        result = member_admin.last_login_display(member)
        assert result == "15 days ago"


@pytest.mark.django_db
def describe_active_status_filter():
    def it_defaults_to_active_members_only(admin_client):
        MemberFactory(full_legal_name="Active Al", status=Member.Status.ACTIVE)
        MemberFactory(full_legal_name="Former Fred", status=Member.Status.FORMER)
        resp = admin_client.get("/admin/membership/member/")
        content = resp.content.decode()
        assert "Active Al" in content
        assert "Former Fred" not in content

    def it_shows_all_members_when_all_filter_selected(admin_client):
        MemberFactory(full_legal_name="Active Al", status=Member.Status.ACTIVE)
        MemberFactory(full_legal_name="Former Fred", status=Member.Status.FORMER)
        resp = admin_client.get("/admin/membership/member/?status=all")
        content = resp.content.decode()
        assert "Active Al" in content
        assert "Former Fred" in content

    def it_shows_only_former_when_former_filter_selected(admin_client):
        MemberFactory(full_legal_name="Active Al", status=Member.Status.ACTIVE)
        MemberFactory(full_legal_name="Former Fred", status=Member.Status.FORMER)
        resp = admin_client.get("/admin/membership/member/?status=former")
        content = resp.content.decode()
        assert "Active Al" not in content
        assert "Former Fred" in content


def describe_GuildAdmin():
    def it_has_expected_list_display():
        guild_admin = admin.site._registry[Guild]
        assert guild_admin.list_display == ["name", "guild_lead", "notes_preview"]

    def it_has_expected_search_fields():
        guild_admin = admin.site._registry[Guild]
        assert guild_admin.search_fields == ["name"]


@pytest.mark.django_db
def describe_admin_guild_computed_fields():
    def it_displays_notes_preview_short():
        guild = GuildFactory(name="Short Notes Guild", notes="Brief note")
        guild_admin = admin.site._registry[Guild]
        result = guild_admin.notes_preview(guild)
        assert result == "Brief note"

    def it_displays_notes_preview_truncated():
        long_notes = "A" * 100
        guild = GuildFactory(name="Long Notes Guild", notes=long_notes)
        guild_admin = admin.site._registry[Guild]
        result = guild_admin.notes_preview(guild)
        assert result == "A" * 80 + "..."
        assert len(result) == 83

    def it_displays_notes_preview_empty():
        guild = GuildFactory(name="No Notes Guild", notes="")
        guild_admin = admin.site._registry[Guild]
        result = guild_admin.notes_preview(guild)
        assert result == ""


def describe_VotePreferenceAdmin():
    def it_has_expected_list_display():
        pref_admin = admin.site._registry[VotePreference]
        assert pref_admin.list_display == ["member", "guild_1st", "guild_2nd", "guild_3rd", "updated_at"]

    def it_has_expected_search_fields():
        pref_admin = admin.site._registry[VotePreference]
        assert pref_admin.search_fields == ["member__full_legal_name", "member__preferred_name"]


def describe_FundingSnapshotAdmin():
    def it_has_expected_list_display():
        snap_admin = admin.site._registry[FundingSnapshot]
        assert snap_admin.list_display == ["cycle_label", "snapshot_at", "contributor_count", "funding_pool"]

    def it_has_snapshot_at_in_readonly_fields():
        snap_admin = admin.site._registry[FundingSnapshot]
        assert "snapshot_at" in snap_admin.readonly_fields


# ---------------------------------------------------------------------------
# Admin View Integration Tests (HTTP-level)
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client():
    user = User.objects.create_superuser(
        username="admin-test",
        password="admin-test-pw",
        email="admin-test@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def describe_admin_member_views():
    def it_loads_changelist(admin_client):
        MemberFactory()
        resp = admin_client.get("/admin/membership/member/")
        assert resp.status_code == 200

    def it_loads_add_form(admin_client):
        resp = admin_client.get("/admin/membership/member/add/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_guild_views():
    def it_loads_changelist(admin_client):
        GuildFactory(name="View Test Guild")
        resp = admin_client.get("/admin/membership/guild/")
        assert resp.status_code == 200

    def it_loads_add_form(admin_client):
        resp = admin_client.get("/admin/membership/guild/add/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_vote_preference_views():
    def it_loads_changelist(admin_client):
        g1 = GuildFactory()
        g2 = GuildFactory()
        g3 = GuildFactory()
        member = MemberFactory()
        VotePreferenceFactory(member=member, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        resp = admin_client.get("/admin/membership/votepreference/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_funding_snapshot_views():
    def it_loads_changelist(admin_client):
        FundingSnapshotFactory()
        resp = admin_client.get("/admin/membership/fundingsnapshot/")
        assert resp.status_code == 200
