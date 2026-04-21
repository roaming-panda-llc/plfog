"""BDD specs for Registration."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from classes.factories import ClassOfferingFactory, RegistrationFactory
from classes.models import Registration
from membership.models import Member
from tests.membership.factories import MembershipPlanFactory


def describe_Registration():
    def describe_self_serve_token():
        def it_generates_64_char_token_on_create(db):
            reg = RegistrationFactory()
            assert reg.self_serve_token
            assert len(reg.self_serve_token) >= 60  # urlsafe 48 bytes -> 64 chars

        def it_keeps_token_stable_across_saves(db):
            reg = RegistrationFactory()
            original = reg.self_serve_token
            reg.first_name = "Changed"
            reg.save()
            reg.refresh_from_db()
            assert reg.self_serve_token == original

        def it_issues_unique_tokens(db):
            a = RegistrationFactory()
            b = RegistrationFactory()
            assert a.self_serve_token != b.self_serve_token

    def describe_member_linking():
        def it_auto_links_member_by_verified_email(db):
            from allauth.account.models import EmailAddress

            User = get_user_model()
            # MembershipPlan must exist so the post_save signal auto-creates the Member
            # and migrate_to_user creates a verified primary EmailAddress
            MembershipPlanFactory()
            user = User.objects.create_user(username="m@x.com", email="m@x.com")
            # Signal auto-created the Member and a verified EmailAddress; fetch them
            member = Member.objects.get(user=user)
            # Confirm the EmailAddress was auto-created as verified
            assert EmailAddress.objects.filter(user=user, email="m@x.com", verified=True).exists()

            reg = RegistrationFactory(email="m@x.com")
            reg.refresh_from_db()
            assert reg.member_id == member.pk

        def it_does_not_link_unverified_email(db):
            from allauth.account.models import EmailAddress

            User = get_user_model()
            MembershipPlanFactory()
            user = User.objects.create_user(username="u@x.com", email="u@x.com")
            # Signal created a verified EmailAddress; flip it to unverified
            EmailAddress.objects.filter(user=user, email="u@x.com").update(verified=False)

            reg = RegistrationFactory(email="u@x.com")
            reg.refresh_from_db()
            assert reg.member is None

        def it_does_not_link_when_no_match(db):
            reg = RegistrationFactory(email="nobody@example.com")
            assert reg.member is None

    def describe_state_transitions():
        def it_cancels_and_stamps_cancelled_at(db):
            reg = RegistrationFactory(status=Registration.Status.CONFIRMED)
            reg.cancel(reason="changed mind")
            reg.refresh_from_db()
            assert reg.status == Registration.Status.CANCELLED
            assert reg.cancelled_at is not None

    def describe_stringify():
        def it_includes_email_and_class(db):
            offering = ClassOfferingFactory(title="Pottery")
            reg = RegistrationFactory(class_offering=offering, email="x@y.com")
            assert "x@y.com" in str(reg)
            assert "Pottery" in str(reg)
