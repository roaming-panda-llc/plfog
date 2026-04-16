"""Capability system for plfog.

A Member's *actual* capabilities are derived from their data (`fog_role`,
guild lead assignments, etc.). Any subset of them can be *hidden* for the
current session via the "Viewing as" popover — hidden capabilities are
stored in ``request.session["hidden_capabilities"]`` as a list of names.

*Effective* capabilities = actual − hidden. Every permission check in the
app should go through ``request.capabilities`` (attached by
``CapabilityMiddleware``) so session overrides are respected uniformly.

Capabilities are atomic — each is an independent flag. New roles
(treasurer, event coordinator, ...) add new constants here; they never
modify or subsume existing ones.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

    from membership.models import Guild, Member


SESSION_HIDDEN_KEY = "hidden_capabilities"


def admin_capability_required(view_func):
    """View decorator: require effective ``admin`` capability.

    Uses the session-aware check so an admin who unchecks "Admin" in the
    popover is also denied — consistent with the rest of the capability
    system. Anonymous users are redirected to login; authenticated
    non-admins get a 403.
    """
    from functools import wraps

    from django.contrib.auth.decorators import login_required
    from django.http import HttpResponseForbidden

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        caps = getattr(request, "capabilities", None)
        if caps is None or not caps.is_admin:
            return HttpResponseForbidden("Admin capability required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


class Capability:
    """String constants for every capability the app knows about."""

    MEMBER = "member"
    GUILD_OFFICER = "guild_officer"
    ADMIN = "admin"

    ALL: frozenset[str] = frozenset({MEMBER, GUILD_OFFICER, ADMIN})

    # Display order + human-readable labels for the "Viewing as" popover.
    LABELS: tuple[tuple[str, str], ...] = (
        (MEMBER, "Member"),
        (GUILD_OFFICER, "Guild Officer"),
        (ADMIN, "Admin"),
    )


def _member_for(user: "AbstractBaseUser | AnonymousUser | None") -> "Member | None":
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "member", None)


def compute_actual(user: "AbstractBaseUser | AnonymousUser | None") -> frozenset[str]:
    """Derive the set of capabilities a user actually holds.

    Source of truth:
      - Superusers get every capability (emergency fallback).
      - A linked ``Member`` always has ``member``.
      - ``fog_role=admin`` adds ``admin`` (and ``guild_officer``, since
        every admin also has officer powers).
      - ``fog_role=guild_officer`` adds ``guild_officer``.
      - Being the ``guild_lead`` of any active guild adds ``guild_officer``
        (leading one guild is an implicit officer of that guild).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()

    if getattr(user, "is_superuser", False):
        return Capability.ALL

    member = _member_for(user)
    if member is None:
        return frozenset()

    caps: set[str] = {Capability.MEMBER}

    from membership.models import Member as MemberModel

    if member.fog_role == MemberModel.FogRole.ADMIN:
        caps.add(Capability.ADMIN)
        caps.add(Capability.GUILD_OFFICER)
    elif member.fog_role == MemberModel.FogRole.GUILD_OFFICER:
        caps.add(Capability.GUILD_OFFICER)

    if member.led_guilds.filter(is_active=True).exists():
        caps.add(Capability.GUILD_OFFICER)
    elif member.officer_of_guilds.filter(is_active=True).exists():
        caps.add(Capability.GUILD_OFFICER)

    return frozenset(caps)


def _read_hidden(session) -> frozenset[str]:  # noqa: ANN001 — Django session is untyped
    raw = session.get(SESSION_HIDDEN_KEY, []) if session is not None else []
    return frozenset(name for name in raw if name in Capability.ALL)


class Capabilities:
    """Effective-capability wrapper attached to every request.

    Holds the user's actual set + the session-hidden set, and exposes a
    single ``has()`` check that respects both. Views and template tags
    should never compare ``fog_role`` directly — go through here.
    """

    def __init__(
        self,
        user: "AbstractBaseUser | AnonymousUser | None",
        actual: frozenset[str],
        hidden: frozenset[str],
    ) -> None:
        self.user = user
        self.actual = actual
        self.hidden = hidden
        self.effective = actual - hidden

    def has(self, name: str) -> bool:
        return name in self.effective

    def has_actual(self, name: str) -> bool:
        """Check the *actual* set, ignoring session overrides.

        Used by the popover itself — we need to know which checkboxes to
        render even for capabilities the user has hidden.
        """
        return name in self.actual

    @property
    def is_admin(self) -> bool:
        return self.has(Capability.ADMIN)

    @property
    def is_guild_officer(self) -> bool:
        return self.has(Capability.GUILD_OFFICER)

    @property
    def is_member(self) -> bool:
        return self.has(Capability.MEMBER)

    @property
    def top_label(self) -> str:
        """Human label for the highest *effective* capability — shown in the sidebar brand."""
        if self.is_admin:
            return "Admin"
        if self.is_guild_officer:
            return "Guild Officer"
        if self.is_member:
            return "Member"
        return "Guest"

    @property
    def popover_rows(self) -> list[dict[str, object]]:
        """Ordered list of ``{name, label, active}`` dicts for the popover UI."""
        return [
            {"name": name, "label": label, "active": name not in self.hidden}
            for name, label in Capability.LABELS
            if name in self.actual
        ]

    @property
    def show_popover(self) -> bool:
        """Only users with more than the base ``member`` capability see the popover."""
        return len(self.actual - {Capability.MEMBER}) > 0

    def can_manage_guild(self, guild: "Guild") -> bool:
        """Whether the current user can manage ``guild``.

        Admins can manage every guild. Otherwise only members who are
        the guild's lead or appear in its per-guild officers M2M can
        manage it (edit products, info, officer roster).

        Note: the ``admin`` capability is the only thing that lets you
        change the lead itself — that check lives on the view side.
        """
        if self.is_admin:
            return True
        member = _member_for(self.user)
        if member is None:
            return False
        if guild.guild_lead_id == member.pk:
            return True
        return guild.officers.filter(pk=member.pk).exists()

    @classmethod
    def for_request(cls, request) -> "Capabilities":  # noqa: ANN001 — HttpRequest
        actual = compute_actual(request.user)
        hidden = _read_hidden(getattr(request, "session", None))
        return cls(user=request.user, actual=actual, hidden=hidden)
