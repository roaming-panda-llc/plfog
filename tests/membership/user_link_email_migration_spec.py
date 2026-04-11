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

    def it_does_not_re_run_migration_on_subsequent_user_saves(db):
        """Regression: re-saving a User must NOT re-trigger migrate_to_user.

        Prior 1.4.0 behavior force-re-promoted Member._pre_signup_email to primary
        on every user.save(), which silently reverted any other primary set via
        allauth's set_as_primary (which itself calls user.save() internally).
        See feature/admin-email-aliases for the discovery context.
        """
        MembershipPlanFactory()
        user = User.objects.create_user(username="existing", email="existing@example.com")

        # Promote a different email to primary, mimicking what allauth's
        # set_as_primary does internally.
        new_primary = EmailAddress.objects.create(user=user, email="other@example.com", verified=True, primary=False)
        EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
        new_primary.primary = True
        new_primary.save(update_fields=["primary"])

        # Re-save the user — this is what set_as_primary does at the end. The
        # signal MUST NOT revert the new primary back to existing@example.com.
        user.first_name = "Updated"
        user.save()

        new_primary.refresh_from_db()
        assert new_primary.primary is True
        old = EmailAddress.objects.get(user=user, email="existing@example.com")
        assert old.primary is False

    def it_does_not_revert_primary_when_set_as_primary_is_called(db):
        """End-to-end regression using allauth's actual set_as_primary."""
        MembershipPlanFactory()
        user = User.objects.create_user(username="existing", email="existing@example.com")

        new_primary = EmailAddress.objects.create(user=user, email="other@example.com", verified=True, primary=False)
        new_primary.set_as_primary(conditional=False)

        new_primary.refresh_from_db()
        old = EmailAddress.objects.get(user=user, email="existing@example.com")
        assert new_primary.primary is True
        assert old.primary is False
        user.refresh_from_db()
        assert user.email == "other@example.com"
