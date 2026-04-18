"""Session-backed "Viewing as" role preview for the hub.

A Member's *actual* roles are derived from ``member.fog_role``. Any subset
can be *hidden* for the current session via the topbar popover — hidden role
names are stored in ``request.session["view_as_hidden_roles"]``.

*Effective* roles = actual − hidden. Every hub-side UI gate and convenience
check should read ``request.view_as`` (attached by ``ViewAsMiddleware``) so
the session override is respected uniformly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http import HttpRequest

ROLE_MEMBER = "member"
ROLE_GUILD_OFFICER = "guild_officer"
ROLE_ADMIN = "admin"

ALL_ROLES: frozenset[str] = frozenset({ROLE_MEMBER, ROLE_GUILD_OFFICER, ROLE_ADMIN})

ROLE_LABELS: tuple[tuple[str, str], ...] = (
    (ROLE_MEMBER, "Member"),
    (ROLE_GUILD_OFFICER, "Guild Officer"),
    (ROLE_ADMIN, "Admin"),
)

SESSION_HIDDEN_KEY = "view_as_hidden_roles"


def compute_actual_roles(user: "AbstractBaseUser | AnonymousUser | None") -> frozenset[str]:
    """Derive the set of roles a user actually holds.

    Superusers without a linked Member still get the full set so emergency
    access is never dependent on Member data being correct.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()

    from membership.models import Member as MemberModel

    try:
        member = user.member  # type: ignore[union-attr]
    except MemberModel.DoesNotExist:
        member = None

    if member is None:
        if getattr(user, "is_superuser", False):
            return ALL_ROLES
        return frozenset()

    if member.fog_role == MemberModel.FogRole.ADMIN:
        return frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})
    if member.fog_role == MemberModel.FogRole.GUILD_OFFICER:
        return frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER})
    return frozenset({ROLE_MEMBER})


def _read_hidden(session) -> frozenset[str]:  # noqa: ANN001 — Django session is untyped
    raw = session.get(SESSION_HIDDEN_KEY, []) if session is not None else []
    return frozenset(name for name in raw if name in ALL_ROLES)


class ViewAs:
    """Effective-roles wrapper attached to every request by the middleware."""

    def __init__(self, actual: frozenset[str], hidden: frozenset[str]) -> None:
        self.actual = actual
        self.hidden = hidden
        self.effective = actual - hidden

    def has(self, role: str) -> bool:
        return role in self.effective

    def has_actual(self, role: str) -> bool:
        """Check the *actual* set, ignoring session overrides — used by the popover."""
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
    def show_popover(self) -> bool:
        """Only users with more than the base ``member`` role see the popover."""
        return len(self.actual - {ROLE_MEMBER}) > 0

    @property
    def popover_rows(self) -> list[dict[str, object]]:
        """Ordered ``{name, label, active}`` dicts for the popover UI."""
        return [
            {"name": name, "label": label, "active": name not in self.hidden}
            for name, label in ROLE_LABELS
            if name in self.actual
        ]

    @classmethod
    def for_request(cls, request: "HttpRequest") -> "ViewAs":
        actual = compute_actual_roles(request.user)
        hidden = _read_hidden(getattr(request, "session", None))
        return cls(actual=actual, hidden=hidden)


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
