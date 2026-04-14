"""Capability checks for member-facing pages that expose admin-ish controls.

These helpers answer "can this user see or do this?" based on their role
and relationship to the object. Views and templates call them; there's no
decoration layer yet — the helpers return booleans so templates can use
them directly for conditional rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

    from membership.models import Guild, Member


def _get_member(user: "AbstractBaseUser | AnonymousUser | None") -> "Member | None":
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "member", None)


def can_manage_guild(user: "AbstractBaseUser | AnonymousUser | None", guild: "Guild") -> bool:
    """True if the user can add/edit/remove products on this guild's page.

    Who qualifies:
      - Django superusers
      - Members with ``fog_role=admin``
      - Members with ``fog_role=guild_officer`` whose led_guilds include this guild
      - The guild's ``guild_lead`` member (implicit officer of one)
    """
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True

    member = _get_member(user)
    if member is None:
        return False

    if member.is_fog_admin:
        return True

    # Guild-scoped: the guild's lead is this member
    return guild.guild_lead_id == member.pk
