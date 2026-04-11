"""Signal hook: promote staging emails when a User is linked to a Member.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""

from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from membership.models import MemberEmail
from tests.membership.factories import MemberFactory, MembershipPlanFactory

User = get_user_model()


def describe_user_link_signal_promotes_emails():
    def it_promotes_staging_emails_when_user_signs_up_with_alias(db):
        MembershipPlanFactory()
        member = MemberFactory(user=None, _pre_signup_email="primary@example.com")
        MemberEmail.objects.create(member=member, email="alias@example.com")

        user = User.objects.create_user(username="aliasuser", email="alias@example.com")

        member.refresh_from_db()
        assert member.user_id == user.pk
        assert EmailAddress.objects.filter(user=user, email="primary@example.com", verified=True).exists()
        assert EmailAddress.objects.filter(user=user, email="alias@example.com", verified=True).exists()
        assert not MemberEmail.objects.filter(member=member).exists()

    def it_promotes_when_user_signs_up_with_primary_email(db):
        MembershipPlanFactory()
        member = MemberFactory(user=None, _pre_signup_email="primary@example.com")

        user = User.objects.create_user(username="primaryuser", email="primary@example.com")

        member.refresh_from_db()
        assert member.user_id == user.pk
        primary = EmailAddress.objects.get(user=user, primary=True)
        assert primary.email == "primary@example.com"
        assert primary.verified is True

    def it_promotes_for_freshly_auto_created_member(db):
        MembershipPlanFactory()
        user = User.objects.create_user(username="fresh", email="fresh@example.com")

        # The signal auto-created a Member; migrate_to_user should have run too.
        assert EmailAddress.objects.filter(user=user, email="fresh@example.com", primary=True, verified=True).exists()

    def it_runs_migrate_safety_net_when_user_already_has_member(db):
        MembershipPlanFactory()
        user = User.objects.create_user(username="existing", email="existing@example.com")
        # Saving the user again triggers post_save and the early-return safety-net branch.
        user.first_name = "Updated"
        user.save()
        assert EmailAddress.objects.filter(user=user, email="existing@example.com", primary=True).exists()
