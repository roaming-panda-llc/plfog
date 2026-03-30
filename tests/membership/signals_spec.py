"""Tests for membership signals."""

from __future__ import annotations

import logging

import pytest
from django.contrib.auth import get_user_model

from membership.models import Member, MembershipPlan
from tests.membership.factories import MemberFactory, MembershipPlanFactory

User = get_user_model()


@pytest.mark.django_db
def describe_ensure_user_has_member():
    def it_auto_creates_member_for_regular_user():
        MembershipPlanFactory()
        user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="password",
        )
        assert Member.objects.filter(user=user).exists()

    def it_auto_creates_member_for_staff_user():
        MembershipPlanFactory()
        user = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password="password",
            is_staff=True,
        )
        assert Member.objects.filter(user=user).exists()

    def it_does_not_create_duplicate_member():
        MembershipPlanFactory()
        user = User.objects.create_user(
            username="existing",
            email="existing@example.com",
            password="password",
        )
        # Signal already created one; saving again shouldn't duplicate
        user.save()
        assert Member.objects.filter(user=user).count() == 1

    def it_logs_warning_and_skips_when_no_membership_plan_exists(caplog):
        MembershipPlan.objects.all().delete()
        with caplog.at_level(logging.WARNING, logger="membership.signals"):
            user = User.objects.create_user(
                username="noplan",
                email="noplan@example.com",
                password="password",
            )

        assert not Member.objects.filter(user=user).exists()
        assert "no MembershipPlan exists" in caplog.text

    def it_uses_full_name_when_available():
        MembershipPlanFactory()
        user = User.objects.create_user(
            username="fullname",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            password="password",
        )
        member = Member.objects.get(user=user)
        assert member.full_legal_name == "Jane Doe"

    def it_falls_back_to_username_when_full_name_is_blank():
        MembershipPlanFactory()
        user = User.objects.create_user(
            username="nofullname",
            first_name="",
            last_name="",
            email="nofullname@example.com",
            password="password",
        )
        member = Member.objects.get(user=user)
        assert member.full_legal_name == "nofullname"

    def it_links_pre_created_invite_member_by_email():
        plan = MembershipPlanFactory()
        # Pre-create a Member placeholder (as invite flow does)
        placeholder = MemberFactory(
            user=None,
            email="invited@example.com",
            status=Member.Status.INVITED,
            membership_plan=plan,
        )
        # Creating a user with matching email should link, not create new
        user = User.objects.create_user(
            username="invitee",
            first_name="Jane",
            last_name="Doe",
            email="invited@example.com",
            password="password",
        )
        placeholder.refresh_from_db()
        assert placeholder.user == user
        assert placeholder.status == Member.Status.ACTIVE
        assert placeholder.full_legal_name == "Jane Doe"
        # No duplicate Member created
        assert Member.objects.filter(email__iexact="invited@example.com").count() == 1

    def it_links_invite_member_case_insensitively():
        plan = MembershipPlanFactory()
        placeholder = MemberFactory(
            user=None,
            email="UPPER@example.com",
            status=Member.Status.INVITED,
            membership_plan=plan,
        )
        user = User.objects.create_user(
            username="upperuser",
            email="upper@example.com",
            password="password",
        )
        placeholder.refresh_from_db()
        assert placeholder.user == user
        assert placeholder.status == Member.Status.ACTIVE

    def it_links_pre_created_member_by_alias_email():
        from membership.models import MemberEmail

        plan = MembershipPlanFactory()
        member = MemberFactory(
            user=None,
            email="primary@example.com",
            full_legal_name="Alias Person",
            status=Member.Status.INVITED,
            membership_plan=plan,
        )
        MemberEmail.objects.create(member=member, email="alias@example.com")

        user = User.objects.create_user(
            username="aliaslogin",
            email="alias@example.com",
            password="password",
        )
        member.refresh_from_db()
        assert member.user == user
        assert member.status == Member.Status.ACTIVE
        assert Member.objects.filter(user=user).count() == 1
