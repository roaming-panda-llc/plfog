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
