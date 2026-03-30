from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client

from django.utils import timezone

from unittest.mock import MagicMock

from membership.admin import (
    ActiveStatusFilter,
    FundingSnapshotAdmin,
    GuildAdmin,
    HasUserFilter,
    MemberAdmin,
    MemberEmailInline,
    PayingMemberFilter,
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


def describe_hidden_admin_pages():
    def it_does_not_register_user_admin():
        from django.contrib.auth import get_user_model

        assert get_user_model() not in admin.site._registry

    def it_does_not_register_emailaddress_admin():
        from allauth.account.models import EmailAddress

        assert EmailAddress not in admin.site._registry


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
            "status",
            "member_type",
            "fog_role",
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
        assert HasUserFilter in member_admin.list_filter
        assert "member_type" in member_admin.list_filter

    def it_has_list_per_page_set():
        member_admin = admin.site._registry[Member]
        assert member_admin.list_per_page == 100

    @pytest.mark.django_db
    def it_shows_fog_role_field_for_superusers():
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/admin/membership/member/add/")
        request.user = User(is_staff=True, is_superuser=True)
        member_admin = admin.site._registry[Member]
        fieldsets = member_admin.get_fieldsets(request)
        membership_fields = fieldsets[1][1]["fields"]
        assert "fog_role" in membership_fields

    @pytest.mark.django_db
    def it_hides_fog_role_field_for_non_superusers():
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/admin/membership/member/add/")
        request.user = User(is_staff=True, is_superuser=False)
        member_admin = admin.site._registry[Member]
        fieldsets = member_admin.get_fieldsets(request)
        membership_fields = fieldsets[1][1]["fields"]
        assert "fog_role" not in membership_fields

    @pytest.mark.django_db
    def it_shows_create_user_on_add_form():
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/admin/membership/member/add/")
        request.user = User(is_staff=True, is_superuser=True)
        member_admin = admin.site._registry[Member]
        fieldsets = member_admin.get_fieldsets(request)
        personal_fields = fieldsets[0][1]["fields"]
        assert "create_user" in personal_fields
        assert "user" not in personal_fields

    @pytest.mark.django_db
    def it_shows_user_on_edit_form():
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/admin/membership/member/1/change/")
        request.user = User(is_staff=True, is_superuser=True)
        member = MemberFactory()
        member_admin = admin.site._registry[Member]
        fieldsets = member_admin.get_fieldsets(request, obj=member)
        personal_fields = fieldsets[0][1]["fields"]
        assert "user" in personal_fields
        assert "create_user" not in personal_fields


def describe_MemberEmailInline():
    def it_is_attached_to_member_admin():
        member_admin = admin.site._registry[Member]
        inline_classes = [type(i) for i in member_admin.get_inline_instances(MagicMock())]
        assert MemberEmailInline in inline_classes


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


@pytest.mark.django_db
def describe_has_user_filter():
    def it_shows_all_members_by_default(admin_client):
        MemberFactory(full_legal_name="No User Nancy", user=None)
        user = User.objects.create_user(username="hasuser", email="hasuser@example.com")
        user.member.full_legal_name = "Has User Helen"
        user.member.save()
        resp = admin_client.get("/admin/membership/member/?status=all")
        content = resp.content.decode()
        assert "No User Nancy" in content
        assert "Has User Helen" in content

    def it_shows_only_users_when_users_filter_selected(admin_client):
        MemberFactory(full_legal_name="No User Nancy", user=None)
        user = User.objects.create_user(username="hasuser2", email="hasuser2@example.com")
        user.member.full_legal_name = "Has User Helen"
        user.member.save()
        resp = admin_client.get("/admin/membership/member/?status=all&has_user=yes")
        content = resp.content.decode()
        assert "No User Nancy" not in content
        assert "Has User Helen" in content


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

    def it_has_paying_member_filter():
        pref_admin = admin.site._registry[VotePreference]
        assert PayingMemberFilter in pref_admin.list_filter


@pytest.mark.django_db
def describe_paying_member_filter():
    def it_shows_all_by_default(admin_client):
        g1, g2, g3 = GuildFactory(), GuildFactory(), GuildFactory()
        standard = MemberFactory(member_type=Member.MemberType.STANDARD, full_legal_name="Paying Pat")
        work_trade = MemberFactory(member_type=Member.MemberType.WORK_TRADE, full_legal_name="Free Fred")
        VotePreferenceFactory(member=standard, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        VotePreferenceFactory(member=work_trade, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        resp = admin_client.get("/admin/membership/votepreference/")
        content = resp.content.decode()
        assert "Paying Pat" in content
        assert "Free Fred" in content

    def it_filters_paying_only(admin_client):
        g1, g2, g3 = GuildFactory(), GuildFactory(), GuildFactory()
        standard = MemberFactory(member_type=Member.MemberType.STANDARD, full_legal_name="Paying Pat")
        work_trade = MemberFactory(member_type=Member.MemberType.WORK_TRADE, full_legal_name="Free Fred")
        VotePreferenceFactory(member=standard, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        VotePreferenceFactory(member=work_trade, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        resp = admin_client.get("/admin/membership/votepreference/?paying=yes")
        content = resp.content.decode()
        assert "Paying Pat" in content
        assert "Free Fred" not in content

    def it_filters_non_paying_only(admin_client):
        g1, g2, g3 = GuildFactory(), GuildFactory(), GuildFactory()
        standard = MemberFactory(member_type=Member.MemberType.STANDARD, full_legal_name="Paying Pat")
        work_trade = MemberFactory(member_type=Member.MemberType.WORK_TRADE, full_legal_name="Free Fred")
        VotePreferenceFactory(member=standard, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        VotePreferenceFactory(member=work_trade, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        resp = admin_client.get("/admin/membership/votepreference/?paying=no")
        content = resp.content.decode()
        assert "Paying Pat" not in content
        assert "Free Fred" in content


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


@pytest.mark.django_db
def describe_admin_search_by_alias():
    def it_finds_member_by_alias_email(admin_client):
        from membership.models import MemberEmail

        member = MemberFactory(full_legal_name="Alias Andy", email="primary@example.com")
        MemberEmail.objects.create(member=member, email="secret@alias.com")
        resp = admin_client.get("/admin/membership/member/?status=all&q=secret@alias.com")
        content = resp.content.decode()
        assert "Alias Andy" in content


@pytest.mark.django_db
def describe_admin_create_user_with_member():
    def it_creates_member_without_user_by_default(admin_client):
        plan = MembershipPlanFactory()
        resp = admin_client.post(
            "/admin/membership/member/add/",
            {
                "full_legal_name": "Test Person",
                "email": "test@example.com",
                "membership_plan": plan.pk,
                "status": "active",
                "member_type": "standard",
                "fog_role": "member",
                "create_user": "",
                "emails-TOTAL_FORMS": "1",
                "emails-INITIAL_FORMS": "0",
                "emails-MIN_NUM_FORMS": "0",
                "emails-MAX_NUM_FORMS": "1000",
                "emails-0-email": "",
                "emails-0-is_primary": "",
            },
        )
        assert resp.status_code == 302
        member = Member.objects.get(email="test@example.com")
        assert member.user is None

    def it_creates_member_with_user_when_checked(admin_client):
        plan = MembershipPlanFactory()
        resp = admin_client.post(
            "/admin/membership/member/add/",
            {
                "full_legal_name": "Login Person",
                "email": "login@example.com",
                "membership_plan": plan.pk,
                "status": "active",
                "member_type": "employee",
                "fog_role": "admin",
                "create_user": "on",
                "emails-TOTAL_FORMS": "1",
                "emails-INITIAL_FORMS": "0",
                "emails-MIN_NUM_FORMS": "0",
                "emails-MAX_NUM_FORMS": "1000",
                "emails-0-email": "",
                "emails-0-is_primary": "",
            },
        )
        assert resp.status_code == 302
        member = Member.objects.get(email="login@example.com")
        assert member.user is not None
        assert member.user.email == "login@example.com"
        assert member.user.username == "login@example.com"
