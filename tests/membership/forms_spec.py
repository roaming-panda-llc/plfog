"""BDD-style tests for membership.forms — InviteMemberForm."""

from __future__ import annotations

import pytest

from core.models import Invite
from membership.forms import InviteMemberForm
from membership.models import Member
from tests.membership.factories import MemberFactory, MembershipPlanFactory

pytestmark = pytest.mark.django_db


def describe_InviteMemberForm():
    def it_accepts_valid_email():
        form = InviteMemberForm(data={"email": "new@example.com"})
        assert form.is_valid()

    def it_rejects_existing_active_member():
        MemberFactory(_pre_signup_email="taken@example.com", status=Member.Status.ACTIVE)
        form = InviteMemberForm(data={"email": "taken@example.com"})
        assert not form.is_valid()
        assert "A member with this email already exists." in form.errors["email"]

    def it_rejects_existing_active_member_case_insensitive():
        MemberFactory(_pre_signup_email="taken@example.com", status=Member.Status.ACTIVE)
        form = InviteMemberForm(data={"email": "TAKEN@example.com"})
        assert not form.is_valid()

    def it_allows_email_with_invited_status_member():
        MemberFactory(_pre_signup_email="invited@example.com", status=Member.Status.INVITED, user=None)
        form = InviteMemberForm(data={"email": "invited@example.com"})
        # Still blocked by pending invite check if one exists, but not by member check
        assert form.is_valid()

    def it_rejects_pending_invite():
        MembershipPlanFactory()
        Invite.objects.create(email="pending@example.com")
        form = InviteMemberForm(data={"email": "pending@example.com"})
        assert not form.is_valid()
        assert "A pending invite for this email already exists." in form.errors["email"]

    def it_allows_accepted_invite_email():
        MembershipPlanFactory()
        from django.utils import timezone

        Invite.objects.create(email="accepted@example.com", accepted_at=timezone.now())
        form = InviteMemberForm(data={"email": "accepted@example.com"})
        assert form.is_valid()
