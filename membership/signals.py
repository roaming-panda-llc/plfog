"""Signals for the membership app."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_has_member(sender: type, instance: Any, **kwargs: Any) -> None:
    """Auto-create or link a Member record for any user who doesn't have one.

    After linking (or creating) a Member, also promotes any pre-signup
    ``MemberEmail`` staging rows for that member into
    ``allauth.account.EmailAddress`` so the user can log in via any of them.
    See ``docs/superpowers/specs/2026-04-07-user-email-aliases-design.md``.
    """
    from .models import Member, MemberEmail, MembershipPlan

    try:
        instance.member
        # Idempotent safety net: ensure allauth EmailAddress reflects current state.
        MemberEmail.objects.migrate_to_user(instance)
        return
    except Member.DoesNotExist:
        pass

    email = getattr(instance, "email", "") or ""
    if email:
        # Check primary email on Member
        try:
            member = Member.objects.get(_pre_signup_email__iexact=email, user__isnull=True)
            member.user = instance
            member.full_legal_name = instance.get_full_name() or member.full_legal_name or instance.username
            member.status = Member.Status.ACTIVE
            member.save(update_fields=["user", "full_legal_name", "status"])
            logger.info("Linked existing Member (primary email) to user %s.", instance.username)
            MemberEmail.objects.migrate_to_user(instance)
            return
        except Member.DoesNotExist:
            pass

        # Check email aliases (pre-signup staging table)
        try:
            alias = MemberEmail.objects.select_related("member").get(email__iexact=email, member__user__isnull=True)
            member = alias.member
            member.user = instance
            member.full_legal_name = instance.get_full_name() or member.full_legal_name or instance.username
            member.status = Member.Status.ACTIVE
            member.save(update_fields=["user", "full_legal_name", "status"])
            logger.info("Linked existing Member (alias email %s) to user %s.", email, instance.username)
            MemberEmail.objects.migrate_to_user(instance)
            return
        except MemberEmail.DoesNotExist:
            pass

    # No pre-existing member found; create one
    try:
        plan = MembershipPlan.objects.order_by("pk").earliest("pk")
    except MembershipPlan.DoesNotExist:
        logger.warning(
            "Cannot auto-create Member for user %s: no MembershipPlan exists.",
            instance.username,
        )
        return

    name = instance.get_full_name() or instance.username
    Member.objects.create(
        user=instance,
        full_legal_name=name,
        _pre_signup_email=instance.email or "",
        membership_plan=plan,
        status=Member.Status.ACTIVE,
    )
    MemberEmail.objects.migrate_to_user(instance)
    logger.info("Auto-created Member for user %s with plan '%s'.", instance.username, plan.name)
