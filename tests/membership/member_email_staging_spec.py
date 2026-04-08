"""Specs for MemberEmail.objects.migrate_to_user().

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""

from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from membership.models import MemberEmail
from tests.membership.factories import MembershipPlanFactory

User = get_user_model()


def _user_with_member(username: str, email: str, pre_signup: str | None = None) -> tuple[object, object]:
    """Create a user (signal auto-creates a Member) and return both."""
    MembershipPlanFactory()
    user = User.objects.create_user(username=username, email=email)
    member = user.member
    if pre_signup is not None:
        member._pre_signup_email = pre_signup
        member.save(update_fields=["_pre_signup_email"])
    return user, member


def describe_MemberEmail_migrate_to_user():
    def it_promotes_each_staging_row_to_a_verified_EmailAddress(db):
        user, member = _user_with_member("u", "primary@example.com", "primary@example.com")
        MemberEmail.objects.create(member=member, email="alias1@example.com")
        MemberEmail.objects.create(member=member, email="alias2@example.com")

        MemberEmail.objects.migrate_to_user(user)

        assert EmailAddress.objects.filter(user=user, email="alias1@example.com", verified=True).exists()
        assert EmailAddress.objects.filter(user=user, email="alias2@example.com", verified=True).exists()

    def it_deletes_the_staging_rows_after_promotion(db):
        user, member = _user_with_member("u", "primary@example.com", "primary@example.com")
        MemberEmail.objects.create(member=member, email="alias@example.com")

        MemberEmail.objects.migrate_to_user(user)

        assert not MemberEmail.objects.filter(member=member).exists()

    def it_is_idempotent(db):
        user, member = _user_with_member("u", "primary@example.com", "primary@example.com")
        MemberEmail.objects.create(member=member, email="alias@example.com")

        MemberEmail.objects.migrate_to_user(user)
        MemberEmail.objects.migrate_to_user(user)

        assert EmailAddress.objects.filter(user=user, email="alias@example.com").count() == 1

    def it_ensures_primary_EmailAddress_exists_for_the_user(db):
        user, _member = _user_with_member("u", "primary@example.com", "primary@example.com")

        MemberEmail.objects.migrate_to_user(user)

        primary = EmailAddress.objects.get(user=user, primary=True)
        assert primary.email == "primary@example.com"
        assert primary.verified is True

    def it_does_nothing_when_member_has_no_staging_rows_and_primary_already_exists(db):
        user, _member = _user_with_member("u", "primary@example.com", "primary@example.com")
        EmailAddress.objects.create(user=user, email="primary@example.com", verified=True, primary=True)

        MemberEmail.objects.migrate_to_user(user)

        assert EmailAddress.objects.filter(user=user).count() == 1

    def it_returns_early_when_user_has_no_member(db):
        MembershipPlanFactory()
        user = User.objects.create_user(username="u", email="x@example.com")
        user.member.delete()
        user.refresh_from_db()
        # Should not raise
        MemberEmail.objects.migrate_to_user(user)
        assert not EmailAddress.objects.filter(user=user).exists()

    def it_promotes_existing_non_primary_primary_email_to_primary(db):
        user, member = _user_with_member("u", "primary@example.com", "primary@example.com")
        EmailAddress.objects.create(user=user, email="primary@example.com", verified=False, primary=False)

        MemberEmail.objects.migrate_to_user(user)

        ea = EmailAddress.objects.get(user=user, email="primary@example.com")
        assert ea.primary is True
        assert ea.verified is True

    def it_skips_staging_row_when_EmailAddress_already_exists(db):
        user, member = _user_with_member("u", "primary@example.com", "primary@example.com")
        EmailAddress.objects.create(user=user, email="alias@example.com", verified=True, primary=False)
        MemberEmail.objects.create(member=member, email="alias@example.com")

        MemberEmail.objects.migrate_to_user(user)

        assert EmailAddress.objects.filter(user=user, email="alias@example.com").count() == 1
        assert not MemberEmail.objects.filter(member=member).exists()

    def it_skips_primary_creation_when_no_email_value(db):
        MembershipPlanFactory()
        user = User.objects.create_user(username="u", email="")
        member = user.member
        member._pre_signup_email = ""
        member.save(update_fields=["_pre_signup_email"])

        MemberEmail.objects.migrate_to_user(user)

        assert not EmailAddress.objects.filter(user=user).exists()
