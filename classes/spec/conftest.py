"""Shared fixtures for classes specs."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def admin_user(db):
    from membership.models import Member, MembershipPlan

    plan, _ = MembershipPlan.objects.get_or_create(name="Standard", defaults={"monthly_price": "50.00"})
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="admin@example.com", defaults={"email": "admin@example.com"})
    # The ensure_user_has_member signal auto-creates a Member with fog_role=MEMBER,
    # so get_or_create always finds the existing record. Flip to ADMIN unconditionally.
    member, _ = Member.objects.get_or_create(
        user=user,
        defaults={"full_legal_name": "Admin User", "fog_role": Member.FogRole.ADMIN, "membership_plan": plan},
    )
    member.fog_role = Member.FogRole.ADMIN
    member.save(update_fields=["fog_role"])
    member.sync_user_permissions()
    return user


@pytest.fixture
def member_user(db):
    from membership.models import Member, MembershipPlan

    plan, _ = MembershipPlan.objects.get_or_create(name="Standard", defaults={"monthly_price": "50.00"})
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="member@example.com", defaults={"email": "member@example.com"})
    Member.objects.get_or_create(
        user=user,
        defaults={"full_legal_name": "Plain Member", "fog_role": Member.FogRole.MEMBER, "membership_plan": plan},
    )
    return user
