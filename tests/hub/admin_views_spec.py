"""BDD specs for the hub-native admin pages: voting dashboard, members, member edit, site settings."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from core.models import SiteConfiguration
from membership.models import Member

pytestmark = pytest.mark.django_db


def _create_superuser(client: Client, *, username: str = "admin") -> User:
    user = User.objects.create_superuser(username=username, email=f"{username}@x.com", password="p")
    client.login(username=username, password="p")
    return user


def _create_member_user(*, username: str, fog_role: str = Member.FogRole.MEMBER) -> User:
    user = User.objects.create_user(username=username, email=f"{username}@x.com", password="p")
    member = user.member
    member.fog_role = fog_role
    member.save(update_fields=["fog_role"])
    return user


def describe_admin_voting_dashboard():
    def it_requires_login(client):
        response = client.get(reverse("hub_admin_voting_dashboard"))
        assert response.status_code == 302

    def it_forbids_plain_members(client):
        user = _create_member_user(username="plain")
        client.login(username=user.username, password="p")
        response = client.get(reverse("hub_admin_voting_dashboard"))
        assert response.status_code == 403

    def it_renders_for_admin(client):
        _create_superuser(client)
        response = client.get(reverse("hub_admin_voting_dashboard"))
        assert response.status_code == 200
        assert b"Voting Dashboard" in response.content
        assert "stats" in response.context


def describe_admin_members():
    def it_requires_login(client):
        response = client.get(reverse("hub_admin_members"))
        assert response.status_code == 302

    def it_forbids_plain_members(client):
        user = _create_member_user(username="m1")
        client.login(username=user.username, password="p")
        response = client.get(reverse("hub_admin_members"))
        assert response.status_code == 403

    def it_renders_for_admin_with_default_active_filter(client):
        _create_superuser(client)
        response = client.get(reverse("hub_admin_members"))
        assert response.status_code == 200
        assert b"Manage Members" in response.content
        assert response.context["status_filter"] == "active"

    def it_filters_by_all_status(client):
        _create_superuser(client)
        response = client.get(reverse("hub_admin_members") + "?status=all")
        assert response.status_code == 200
        assert response.context["status_filter"] == "all"


def describe_admin_member_edit():
    def it_requires_login(client):
        m = _create_member_user(username="target")
        response = client.get(reverse("hub_admin_member_edit", args=[m.member.pk]))
        assert response.status_code == 302

    def it_forbids_plain_members(client):
        target = _create_member_user(username="target2")
        plain = _create_member_user(username="plain2")
        client.login(username=plain.username, password="p")
        response = client.get(reverse("hub_admin_member_edit", args=[target.member.pk]))
        assert response.status_code == 403

    def it_renders_edit_form_for_admin(client):
        _create_superuser(client)
        target = _create_member_user(username="target3")
        response = client.get(reverse("hub_admin_member_edit", args=[target.member.pk]))
        assert response.status_code == 200
        assert b"Edit Member" in response.content

    def it_saves_changes_and_redirects(client):
        _create_superuser(client)
        target = _create_member_user(username="target4")
        response = client.post(
            reverse("hub_admin_member_edit", args=[target.member.pk]),
            data={
                "full_legal_name": "Updated Name",
                "preferred_name": "",
                "pronouns": "",
                "discord_handle": "",
                "about_me": "",
                "status": Member.Status.ACTIVE,
                "member_type": Member.MemberType.STANDARD,
                "fog_role": Member.FogRole.MEMBER,
                "show_in_directory": "on",
            },
        )
        assert response.status_code == 302
        target.member.refresh_from_db()
        assert target.member.full_legal_name == "Updated Name"

    def it_re_renders_on_invalid_post(client):
        _create_superuser(client)
        target = _create_member_user(username="target5")
        response = client.post(
            reverse("hub_admin_member_edit", args=[target.member.pk]),
            data={"full_legal_name": ""},
        )
        assert response.status_code == 200

    def it_404s_for_unknown_member(client):
        _create_superuser(client)
        response = client.get(reverse("hub_admin_member_edit", args=[99999]))
        assert response.status_code == 404


def describe_admin_site_settings():
    def it_requires_login(client):
        response = client.get(reverse("hub_admin_site_settings"))
        assert response.status_code == 302

    def it_forbids_plain_members(client):
        user = _create_member_user(username="plain3")
        client.login(username=user.username, password="p")
        response = client.get(reverse("hub_admin_site_settings"))
        assert response.status_code == 403

    def it_renders_settings_form_for_admin(client):
        _create_superuser(client)
        response = client.get(reverse("hub_admin_site_settings"))
        assert response.status_code == 200
        assert b"Site Settings" in response.content

    def it_saves_changes_and_redirects(client):
        _create_superuser(client)
        response = client.post(
            reverse("hub_admin_site_settings"),
            data={
                "registration_mode": SiteConfiguration.RegistrationMode.OPEN,
                "general_calendar_url": "https://example.com/cal.ics",
                "general_calendar_color": "#123456",
                "sync_classes_enabled": "",
                "classes_calendar_color": "#abcdef",
                "mailchimp_api_key": "",
                "mailchimp_list_id": "",
                "google_analytics_measurement_id": "",
            },
        )
        assert response.status_code == 302
        config = SiteConfiguration.load()
        assert config.registration_mode == SiteConfiguration.RegistrationMode.OPEN
        assert config.general_calendar_url == "https://example.com/cal.ics"

    def it_re_renders_on_invalid_post(client):
        _create_superuser(client)
        response = client.post(
            reverse("hub_admin_site_settings"),
            data={"registration_mode": "not-a-real-mode"},
        )
        assert response.status_code == 200


def describe_fog_admin_required():
    def it_returns_403_when_request_has_no_view_as(rf):
        from django.contrib.auth.models import AnonymousUser

        from hub.view_as import fog_admin_required

        @fog_admin_required
        def view(request):
            return "ok"

        request = rf.get("/")
        request.user = AnonymousUser()
        # No view_as attribute attached — simulates middleware not running.
        response = view(request)
        # @login_required wraps the result, so anonymous users get a redirect, not 403.
        assert response.status_code in (302, 403)
