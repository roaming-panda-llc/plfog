"""Session-backed "Viewing as" role preview for the hub.

A Member's *actual* roles are derived from ``member.fog_role``. Admins can
pick a *view-as* role via the topbar dropdown — the picked role name is
stored in ``request.session["view_as_role"]``.

Roles are a linear hierarchy: admin > guild_officer > member. Effective
roles are every role from the user's actual set that sits at or below the
picked role. When no role is picked (or the picked role is the user's
highest), effective == actual.

Every hub-side UI gate should read ``request.view_as`` (attached by
``ViewAsMiddleware``) so the session override is respected uniformly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http import HttpRequest

ROLE_MEMBER = "member"
ROLE_GUILD_OFFICER = "guild_officer"
ROLE_ADMIN = "admin"
ROLE_INSTRUCTOR = "instructor"

ALL_ROLES: frozenset[str] = frozenset({ROLE_MEMBER, ROLE_INSTRUCTOR, ROLE_GUILD_OFFICER, ROLE_ADMIN})

ROLE_HIERARCHY: tuple[str, ...] = (ROLE_MEMBER, ROLE_GUILD_OFFICER, ROLE_ADMIN)

ROLE_LABELS: tuple[tuple[str, str], ...] = (
    (ROLE_ADMIN, "Admin"),
    (ROLE_INSTRUCTOR, "Instructor"),
    (ROLE_GUILD_OFFICER, "Guild Officer"),
    (ROLE_MEMBER, "Member"),
)

SESSION_ROLE_KEY = "view_as_role"


def compute_actual_roles(user: "AbstractBaseUser | AnonymousUser | None") -> frozenset[str]:
    """Derive the set of roles a user actually holds.

    Superusers without a linked Member still get the full set so emergency
    access is never dependent on Member data being correct. The ``instructor``
    role is parallel to the member hierarchy — derived from the existence
    of an ``Instructor`` record linked to the user.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()

    from membership.models import Member as MemberModel

    try:
        member = user.member  # type: ignore[union-attr]
    except MemberModel.DoesNotExist:
        member = None

    # Lazy import — avoids circulars during Django app loading.
    from classes.models import Instructor

    has_instructor = Instructor.objects.filter(user=user).exists()  # type: ignore[misc]

    roles: set[str] = set()
    if member is not None:
        if member.fog_role == MemberModel.FogRole.ADMIN:
            roles.update({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})
        elif member.fog_role == MemberModel.FogRole.GUILD_OFFICER:
            roles.update({ROLE_GUILD_OFFICER, ROLE_MEMBER})
        else:
            roles.add(ROLE_MEMBER)
    if has_instructor:
        roles.add(ROLE_INSTRUCTOR)
    if getattr(user, "is_superuser", False) and not roles:
        roles.update({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})
    return frozenset(roles)


def _highest_role(actual: frozenset[str]) -> str | None:
    for role in reversed(ROLE_HIERARCHY):
        if role in actual:
            return role
    return None


def _roles_up_to(picked: str, actual: frozenset[str]) -> frozenset[str]:
    """Return the subset of ``actual`` at or below ``picked`` in the hierarchy."""
    idx = ROLE_HIERARCHY.index(picked)
    allowed = frozenset(ROLE_HIERARCHY[: idx + 1])
    return actual & allowed


def _read_picked_role(session, actual: frozenset[str]) -> str | None:  # noqa: ANN001 — Django session is untyped
    raw = session.get(SESSION_ROLE_KEY) if session is not None else None
    if raw in actual:
        return raw
    return None


class ViewAs:
    """Effective-role wrapper attached to every request by the middleware."""

    def __init__(self, actual: frozenset[str], picked: str | None) -> None:
        self.actual = actual
        self.view_as_role = picked or _highest_role(actual)
        self.effective = _roles_up_to(self.view_as_role, actual) if self.view_as_role else frozenset()

    def has(self, role: str) -> bool:
        return role in self.effective

    def has_actual(self, role: str) -> bool:
        """Check the *actual* set, ignoring session overrides — used by the dropdown."""
        return role in self.actual

    @property
    def is_admin(self) -> bool:
        return self.has(ROLE_ADMIN)

    @property
    def is_guild_officer(self) -> bool:
        return self.has(ROLE_GUILD_OFFICER)

    @property
    def is_member(self) -> bool:
        return self.has(ROLE_MEMBER)

    @property
    def is_instructor(self) -> bool:
        return ROLE_INSTRUCTOR in self.actual

    @property
    def show_dropdown(self) -> bool:
        """Only users with more than the base ``member`` hierarchy role see the dropdown.

        The ``instructor`` role is parallel — it never triggers the dropdown on its own.
        """
        hierarchy_roles = self.actual & frozenset(ROLE_HIERARCHY)
        return len(hierarchy_roles - {ROLE_MEMBER}) > 0

    @property
    def current_label(self) -> str:
        """Human label for the currently-viewed role."""
        for name, label in ROLE_LABELS:
            if name == self.view_as_role:
                return label
        return ""

    @property
    def dropdown_options(self) -> list[dict[str, object]]:
        """Ordered ``{name, label, selected}`` dicts for the dropdown menu — highest role first.

        Only hierarchy roles (admin, guild_officer, member) appear in the dropdown.
        The ``instructor`` role is parallel and is excluded.
        """
        return [
            {"name": name, "label": label, "selected": name == self.view_as_role}
            for name, label in ROLE_LABELS
            if name in self.actual and name in ROLE_HIERARCHY
        ]

    @classmethod
    def for_request(cls, request: "HttpRequest") -> "ViewAs":
        actual = compute_actual_roles(request.user)
        picked = _read_picked_role(getattr(request, "session", None), actual)
        return cls(actual=actual, picked=picked)


class ViewAsMiddleware:
    """Attach ``request.view_as`` to every request.

    Must run after ``AuthenticationMiddleware`` (needs ``request.user``)
    and ``SessionMiddleware`` (needs ``request.session``).
    """

    def __init__(self, get_response) -> None:  # noqa: ANN001
        self.get_response = get_response

    def __call__(self, request: "HttpRequest"):
        request.view_as = ViewAs.for_request(request)  # type: ignore[attr-defined]
        return self.get_response(request)
