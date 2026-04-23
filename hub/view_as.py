"""Session-backed "Viewing as" role preview for the hub.

A Member's *actual* roles are derived from ``member.fog_role``. Admins can
pick a *view-as* role via the topbar dropdown — the picked role name is
stored in ``request.session["view_as_role"]``.

Hierarchy roles are a linear ladder: admin > guild_officer > member.
Effective roles are every role from the user's actual set that sits at or
below the picked role. When no role is picked (or the picked role is the
user's highest), effective == actual.

Two roles sit OUTSIDE the hierarchy:

- ``instructor``: a capability granted by having an ``Instructor`` record
  linked to ``request.user``. Users with both Member + Instructor records
  see both; instructors without any Member see "Non-member Instructor" as
  their effective role.
- ``guest``: assigned to anonymous visitors so view-as checks work
  uniformly on public-facing pages.

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
ROLE_GUEST = "guest"

ALL_ROLES: frozenset[str] = frozenset({ROLE_MEMBER, ROLE_INSTRUCTOR, ROLE_GUILD_OFFICER, ROLE_ADMIN, ROLE_GUEST})

ROLE_HIERARCHY: tuple[str, ...] = (ROLE_MEMBER, ROLE_GUILD_OFFICER, ROLE_ADMIN)

ROLE_LABELS: tuple[tuple[str, str], ...] = (
    (ROLE_ADMIN, "Admin"),
    (ROLE_INSTRUCTOR, "Instructor (Non-mem)"),
    (ROLE_GUILD_OFFICER, "Guild Officer"),
    (ROLE_MEMBER, "Member"),
    (ROLE_GUEST, "Guest"),
)

SESSION_ROLE_KEY = "view_as_role"


def compute_actual_roles(user: "AbstractBaseUser | AnonymousUser | None") -> frozenset[str]:
    """Derive the set of roles a user actually holds.

    Anonymous visitors get ``{ROLE_GUEST}``. Superusers without a linked
    Member still get the full hierarchy set so emergency access is never
    dependent on Member data being correct. ``instructor`` is parallel to
    the member hierarchy — derived from an ``Instructor`` record linked
    to the user.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset({ROLE_GUEST})

    from membership.models import Member as MemberModel

    # Query fresh each request rather than `user.member` — avoids stale reverse-OneToOne
    # cache when Member.status is updated outside the instance (e.g. signal updates).
    # user.pk is guaranteed non-None here by the is_authenticated guard above; mypy
    # can't infer that because AbstractBaseUser.pk is typed Any | None.
    member = MemberModel.objects.filter(user_id=user.pk).first()  # type: ignore[misc]

    # Lazy import — avoids circulars during Django app loading.
    from classes.models import Instructor

    has_instructor = Instructor.objects.filter(user=user).exists()  # type: ignore[misc]

    roles: set[str] = set()
    if member is not None and member.status == MemberModel.Status.ACTIVE:
        if member.fog_role == MemberModel.FogRole.ADMIN:
            roles.update({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})
        elif member.fog_role == MemberModel.FogRole.GUILD_OFFICER:
            roles.update({ROLE_GUILD_OFFICER, ROLE_MEMBER})
        else:
            roles.add(ROLE_MEMBER)
    if has_instructor:
        roles.add(ROLE_INSTRUCTOR)
    if getattr(user, "is_superuser", False) and not (roles & set(ROLE_HIERARCHY)):
        roles.update({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})
    if not roles:
        # Logged-in user with no Member and no Instructor — treat as a guest
        # for purposes of role gating. They can still log out / sign up.
        roles.add(ROLE_GUEST)
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
    """Return the session-picked role if the user is allowed to hold or preview it.

    Admins can preview any role (including Guest and Non-member Instructor) by
    picking it in the dropdown, even if it's not in their actual set. Non-admins
    are restricted to roles they already hold.
    """
    raw = session.get(SESSION_ROLE_KEY) if session is not None else None
    if raw is None:
        return None
    if raw in actual:
        return raw
    if ROLE_ADMIN in actual and raw in {ROLE_GUEST, ROLE_INSTRUCTOR, ROLE_MEMBER, ROLE_GUILD_OFFICER, ROLE_ADMIN}:
        return raw
    return None


class ViewAs:
    """Effective-role wrapper attached to every request by the middleware."""

    def __init__(self, actual: frozenset[str], picked: str | None) -> None:
        self.actual = actual
        self.view_as_role = picked or _highest_role(actual)
        # Default (no explicit preview) = every role the user actually holds, so
        # parallel roles like instructor/guest aren't silently dropped by the
        # hierarchy subset. Explicit picks narrow to that preview lens only.
        if picked is None:
            self.effective = actual
        elif picked in ROLE_HIERARCHY:
            self.effective = _roles_up_to(picked, actual)
        elif picked in {ROLE_INSTRUCTOR, ROLE_GUEST}:
            self.effective = frozenset({picked})
        else:
            self.effective = frozenset()

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
        """Honors preview mode — returns True when the effective view is an instructor."""
        return ROLE_INSTRUCTOR in self.effective

    @property
    def is_guest(self) -> bool:
        """Honors preview mode — True when the effective view is a guest."""
        return ROLE_GUEST in self.effective

    @property
    def has_member_role(self) -> bool:
        """Distinct from ``is_member`` (which honors view-as downgrades)."""
        return ROLE_MEMBER in self.actual

    @property
    def is_non_member_instructor(self) -> bool:
        """Instructor without any Member record — a narrower identity used in UI labels."""
        return ROLE_INSTRUCTOR in self.actual and ROLE_MEMBER not in self.actual

    @property
    def instructor_label(self) -> str:
        """UI label for the instructor role — distinguishes member-instructors from non-member ones."""
        return "Non-member Instructor" if self.is_non_member_instructor else "Instructor"

    @property
    def show_dropdown(self) -> bool:
        """The "Viewing as" dropdown is for users who can preview other roles.

        Admins can preview every role (including Guest + Non-member Instructor).
        Guild officers can downgrade to Member. Instructors who also have a
        hierarchy role see it via that path. Plain members and guests don't.
        """
        if ROLE_ADMIN in self.actual:
            return True
        hierarchy_roles = self.actual & frozenset(ROLE_HIERARCHY)
        return len(hierarchy_roles - {ROLE_MEMBER}) > 0

    @property
    def current_label(self) -> str:
        """Human label for the currently-viewed role."""
        if self.view_as_role == ROLE_INSTRUCTOR:
            return self.instructor_label
        for name, label in ROLE_LABELS:
            if name == self.view_as_role:
                return label
        return ""

    @property
    def dropdown_options(self) -> list[dict[str, object]]:
        """Ordered ``{name, label, selected}`` dicts for the dropdown menu — highest role first.

        Admins see every role (including Guest and Non-member Instructor) so they
        can preview what each viewer type sees. Non-admins only see roles from
        their own ``actual`` set — for them the dropdown is a downgrade tool.
        """
        selectable: frozenset[str]
        if ROLE_ADMIN in self.actual:
            selectable = ALL_ROLES
        else:
            selectable = self.actual
        options = []
        for name, label in ROLE_LABELS:
            if name not in selectable:
                continue
            options.append({"name": name, "label": label, "selected": name == self.view_as_role})
        return options

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
