"""Custom managers for the membership app.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md for
context on the three-email-store architecture that `MemberEmailManager`
bridges.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models, transaction

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class MemberEmailManager(models.Manager):
    """Manager for MemberEmail with the pre-signup -> allauth promotion logic."""

    @transaction.atomic
    def migrate_to_user(self, user: AbstractUser) -> None:
        """Promote staging emails for this user's Member into allauth.EmailAddress.

        Creates (if missing) a primary, verified EmailAddress for the Member's
        stored _pre_signup_email, then promotes each MemberEmail row for that
        Member into a verified non-primary EmailAddress, then deletes the
        staging rows. Idempotent.

        THREE-EMAIL-STORE NOTE: After this runs, ``allauth.account.EmailAddress``
        is authoritative for the user. See the spec for the full design.
        """
        from allauth.account.models import EmailAddress

        from .models import Member, MemberEmail

        try:
            member = user.member  # type: ignore[attr-defined]
        except Member.DoesNotExist:
            return

        # 1. Ensure a primary EmailAddress exists.
        primary_email_value = (member._pre_signup_email or user.email or "").strip().lower()
        if primary_email_value:
            ea = EmailAddress.objects.filter(user=user, email__iexact=primary_email_value).first()
            if ea is None:
                EmailAddress.objects.create(
                    user=user,
                    email=primary_email_value,
                    verified=True,
                    primary=True,
                )
            elif not ea.primary:
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                ea.primary = True
                ea.verified = True
                ea.save(update_fields=["primary", "verified"])

        # 2. Promote each staging row.
        for staging in MemberEmail.objects.filter(member=member):
            if not EmailAddress.objects.filter(user=user, email__iexact=staging.email).exists():
                EmailAddress.objects.create(
                    user=user,
                    email=staging.email,
                    verified=True,
                    primary=False,
                )

        # 3. Delete staging rows.
        MemberEmail.objects.filter(member=member).delete()
