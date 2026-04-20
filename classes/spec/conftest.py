"""Shared fixtures for classes specs."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def admin_user(db):
    from membership.models import Member

    User = get_user_model()
    user = User.objects.create_user(username="admin@example.com", email="admin@example.com", password="x")
    member = Member.objects.create(user=user, full_legal_name="Admin User", fog_role=Member.FogRole.ADMIN)
    member.sync_user_permissions()
    return user


@pytest.fixture
def member_user(db):
    from membership.models import Member

    User = get_user_model()
    user = User.objects.create_user(username="member@example.com", email="member@example.com", password="x")
    Member.objects.create(user=user, full_legal_name="Plain Member", fog_role=Member.FogRole.MEMBER)
    return user
