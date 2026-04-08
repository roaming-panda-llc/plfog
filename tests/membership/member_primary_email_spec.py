"""Specs for Member.primary_email property.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md for context
on why this property exists (the three-email-store split).
"""

from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from tests.membership.factories import MembershipPlanFactory, MemberFactory

User = get_user_model()


def _user_with_member(username: str, email: str) -> tuple[object, object]:
    """Create a user (signal auto-creates a Member) and return both."""
    MembershipPlanFactory()  # signal requires a plan to exist
    user = User.objects.create_user(username=username, email=email)
    return user, user.member


def describe_Member_primary_email():
    def it_returns_pre_signup_email_when_no_linked_user(db):
        member = MemberFactory(user=None, _pre_signup_email="staged@example.com")
        assert member.primary_email == "staged@example.com"

    def it_returns_empty_string_when_no_linked_user_and_no_stored_email(db):
        member = MemberFactory(user=None, _pre_signup_email="")
        assert member.primary_email == ""

    def it_returns_primary_EmailAddress_for_linked_user(db):
        user, member = _user_with_member("u1", "primary@example.com")
        # Signal already created the primary EmailAddress; just add an alias.
        EmailAddress.objects.create(user=user, email="alias@example.com", verified=True, primary=False)
        member._pre_signup_email = "stale@example.com"
        member.save(update_fields=["_pre_signup_email"])
        assert member.primary_email == "primary@example.com"

    def it_falls_back_to_user_email_when_no_EmailAddress_rows(db):
        _user, member = _user_with_member("u2", "fallback@example.com")
        # Remove the auto-created EmailAddress to exercise the fallback.
        EmailAddress.objects.filter(user=_user).delete()
        member._pre_signup_email = "stale@example.com"
        member.save(update_fields=["_pre_signup_email"])
        assert member.primary_email == "fallback@example.com"

    def it_returns_empty_string_when_no_EmailAddress_and_user_email_blank(db):
        _user, member = _user_with_member("u3", "")
        EmailAddress.objects.filter(user=_user).delete()
        member._pre_signup_email = "stale@example.com"
        member.save(update_fields=["_pre_signup_email"])
        assert member.primary_email == ""
