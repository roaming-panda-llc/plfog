"""BDD specs for the Viewing-as helper."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser, User

from hub.view_as import ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER, ViewAs, compute_actual_roles
from membership.models import Member
from tests.membership.factories import MemberFactory


def _make_user_member(fog_role: str, *, username: str = "u") -> tuple[User, Member]:
    """Create a User + Member pair with the given fog_role.

    The post_save signal ``ensure_user_has_member`` auto-creates a bare Member
    when a User is created, so we update that Member in place rather than
    creating a second one via MemberFactory.
    """
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password="p")
    member = user.member
    member.fog_role = fog_role
    member.save(update_fields=["fog_role"])
    return user, member


@pytest.mark.django_db
def describe_compute_actual_roles():
    def it_returns_empty_frozenset_for_anonymous_user():
        assert compute_actual_roles(AnonymousUser()) == frozenset()

    def it_returns_empty_frozenset_when_user_has_no_member():
        user = User.objects.create_user(username="u", password="p")
        Member.objects.filter(user=user).delete()
        user = User.objects.get(pk=user.pk)  # refetch to drop stale .member descriptor cache
        assert compute_actual_roles(user) == frozenset()

    def it_returns_admin_guild_officer_and_member_for_fog_admin():
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="admin_u")
        assert compute_actual_roles(user) == frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})

    def it_returns_guild_officer_and_member_for_fog_officer():
        user, _ = _make_user_member(Member.FogRole.GUILD_OFFICER, username="officer_u")
        assert compute_actual_roles(user) == frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER})

    def it_returns_only_member_for_regular_members():
        user, _ = _make_user_member(Member.FogRole.MEMBER, username="member_u")
        assert compute_actual_roles(user) == frozenset({ROLE_MEMBER})

    def it_treats_django_superuser_without_member_as_admin():
        user = User.objects.create_superuser(username="root", email="r@x.com", password="p")
        Member.objects.filter(user=user).delete()
        user = User.objects.get(pk=user.pk)
        assert compute_actual_roles(user) == frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})


def describe_ViewAs():
    def it_marks_has_true_only_for_effective_roles():
        v = ViewAs(actual=frozenset({ROLE_ADMIN, ROLE_MEMBER}), hidden=frozenset({ROLE_ADMIN}))
        assert v.has(ROLE_ADMIN) is False
        assert v.has(ROLE_MEMBER) is True

    def it_has_actual_ignores_hidden():
        v = ViewAs(actual=frozenset({ROLE_ADMIN}), hidden=frozenset({ROLE_ADMIN}))
        assert v.has_actual(ROLE_ADMIN) is True
        assert v.has(ROLE_ADMIN) is False

    def it_exposes_convenience_properties():
        v = ViewAs(
            actual=frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER}),
            hidden=frozenset({ROLE_ADMIN}),
        )
        assert v.is_admin is False
        assert v.is_guild_officer is True
        assert v.is_member is True

    def describe_show_popover():
        def it_is_true_for_admins():
            v = ViewAs(actual=frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER}), hidden=frozenset())
            assert v.show_popover is True

        def it_is_true_for_guild_officers():
            v = ViewAs(actual=frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER}), hidden=frozenset())
            assert v.show_popover is True

        def it_is_false_for_plain_members():
            v = ViewAs(actual=frozenset({ROLE_MEMBER}), hidden=frozenset())
            assert v.show_popover is False

        def it_is_false_for_unauthenticated():
            v = ViewAs(actual=frozenset(), hidden=frozenset())
            assert v.show_popover is False

    def describe_popover_rows():
        def it_lists_rows_in_display_order_with_active_flags():
            v = ViewAs(
                actual=frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER}),
                hidden=frozenset({ROLE_ADMIN}),
            )
            assert v.popover_rows == [
                {"name": ROLE_MEMBER, "label": "Member", "active": True},
                {"name": ROLE_GUILD_OFFICER, "label": "Guild Officer", "active": True},
                {"name": ROLE_ADMIN, "label": "Admin", "active": False},
            ]

        def it_skips_roles_not_actually_held():
            v = ViewAs(actual=frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER}), hidden=frozenset())
            names = [row["name"] for row in v.popover_rows]
            assert names == [ROLE_MEMBER, ROLE_GUILD_OFFICER]


from django.test import RequestFactory

from hub.view_as import ViewAsMiddleware


@pytest.fixture
def rf() -> RequestFactory:
    return RequestFactory()


@pytest.mark.django_db
def describe_ViewAsMiddleware():
    def it_attaches_view_as_to_request(rf: RequestFactory):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="mw_admin")
        request = rf.get("/")
        request.user = user
        request.session = {}

        captured: dict[str, object] = {}

        def get_response(req):
            captured["view_as"] = req.view_as
            return "ok"

        ViewAsMiddleware(get_response)(request)

        assert captured["view_as"].is_admin is True
        assert captured["view_as"].actual == frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})

    def it_respects_hidden_roles_in_session(rf: RequestFactory):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="mw_hidden")
        request = rf.get("/")
        request.user = user
        request.session = {"view_as_hidden_roles": ["admin"]}

        captured: dict[str, object] = {}

        def get_response(req):
            captured["view_as"] = req.view_as
            return "ok"

        ViewAsMiddleware(get_response)(request)

        assert captured["view_as"].is_admin is False
        assert captured["view_as"].is_guild_officer is True


import json


@pytest.mark.django_db
def describe_view_as_toggle_endpoint():
    def it_adds_role_to_hidden_set(client):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="toggle_admin")
        client.login(username=user.username, password="p")

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json() == {"hidden": ["admin"]}
        assert client.session["view_as_hidden_roles"] == ["admin"]

    def it_removes_role_when_hidden_is_false(client):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="toggle_unhide")
        client.login(username=user.username, password="p")
        session = client.session
        session["view_as_hidden_roles"] = ["admin", "guild_officer"]
        session.save()

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": False}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json() == {"hidden": ["guild_officer"]}

    def it_rejects_unknown_role_names(client):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="toggle_wizard")
        client.login(username=user.username, password="p")

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "wizard", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code == 400

    def it_rejects_toggling_a_role_the_user_does_not_hold(client):
        user, _ = _make_user_member(Member.FogRole.MEMBER, username="toggle_plain")
        client.login(username=user.username, password="p")

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code == 403

    def it_rejects_malformed_json(client):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="toggle_malformed")
        client.login(username=user.username, password="p")

        response = client.post("/view-as/toggle/", data=b"not json", content_type="application/json")

        assert response.status_code == 400

    def it_requires_login(client):
        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code in (302, 401, 403)


@pytest.mark.django_db
def describe_popover_in_hub_template():
    def it_renders_popover_for_admins(client):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="tmpl_admin")
        client.login(username=user.username, password="p")

        response = client.get("/guilds/voting/")

        assert response.status_code == 200
        assert b"pl-view-as-popover" in response.content
        assert b"Viewing as" in response.content

    def it_hides_popover_for_plain_members(client):
        user, _ = _make_user_member(Member.FogRole.MEMBER, username="tmpl_plain")
        client.login(username=user.username, password="p")

        response = client.get("/guilds/voting/")

        assert response.status_code == 200
        assert b"pl-view-as-popover" not in response.content

    def it_hides_admin_view_button_when_admin_role_is_hidden(client):
        user, _ = _make_user_member(Member.FogRole.ADMIN, username="tmpl_hidden_admin")
        client.login(username=user.username, password="p")
        session = client.session
        session["view_as_hidden_roles"] = ["admin"]
        session.save()

        response = client.get("/guilds/voting/")

        assert b"Admin View" not in response.content
