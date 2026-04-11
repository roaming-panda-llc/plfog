"""Specs for the admin email-aliases page.

See docs/superpowers/specs/2026-04-11-admin-email-aliases-design.md.
"""

from __future__ import annotations

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client

from membership.forms import AddEmailAliasForm
from membership.models import Member
from tests.membership.factories import MemberFactory

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client(db):
    admin = User.objects.create_superuser(
        username="alias-admin",
        password="pass",
        email="alias-admin@example.com",
    )
    # The ensure_user_has_member signal may have auto-created a Member for the
    # admin. Delete it so it doesn't interfere with test counts.
    Member.objects.filter(user=admin).delete()
    c = Client()
    c.force_login(admin)
    return c


@pytest.fixture()
def linked_member(db):
    """Member with a linked User and one primary verified EmailAddress."""
    user = User.objects.create_user(
        username="penina",
        password="pass",
        email="penina@example.com",
    )
    # Signal may have created a Member already — find it or make one.
    member = Member.objects.filter(user=user).first()
    if member is None:
        member = MemberFactory(user=user, _pre_signup_email="penina@example.com")
    else:
        member._pre_signup_email = "penina@example.com"
        member.save(update_fields=["_pre_signup_email"])
    EmailAddress.objects.filter(user=user).delete()
    EmailAddress.objects.create(
        user=user,
        email="penina@example.com",
        verified=True,
        primary=True,
    )
    return member


@pytest.fixture()
def unlinked_member(db):
    """Member imported from Airtable, no linked User."""
    return MemberFactory(user=None, _pre_signup_email="airtable-only@example.com")


# ---------------------------------------------------------------------------
# describe_AddEmailAliasForm
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_AddEmailAliasForm():
    def it_accepts_a_new_email(linked_member):
        form = AddEmailAliasForm(
            data={"email": "writersguild@pastlives.space"},
            user=linked_member.user,
        )
        assert form.is_valid()
        assert form.cleaned_data["email"] == "writersguild@pastlives.space"

    def it_rejects_an_email_already_on_this_user(linked_member):
        form = AddEmailAliasForm(
            data={"email": "penina@example.com"},
            user=linked_member.user,
        )
        assert not form.is_valid()
        assert "already on this member" in str(form.errors["email"]).lower()

    def it_rejects_case_insensitive_duplicate_on_self(linked_member):
        form = AddEmailAliasForm(
            data={"email": "PENINA@example.com"},
            user=linked_member.user,
        )
        assert not form.is_valid()

    def it_rejects_an_email_tied_to_another_user(linked_member):
        other_user = User.objects.create_user(
            username="other",
            password="pass",
            email="other@example.com",
        )
        EmailAddress.objects.create(
            user=other_user,
            email="shared@example.com",
            verified=True,
            primary=False,
        )
        form = AddEmailAliasForm(
            data={"email": "shared@example.com"},
            user=linked_member.user,
        )
        assert not form.is_valid()
        assert "different account" in str(form.errors["email"]).lower()

    def it_rejects_empty_email(linked_member):
        form = AddEmailAliasForm(data={"email": ""}, user=linked_member.user)
        assert not form.is_valid()

    def it_rejects_malformed_email(linked_member):
        form = AddEmailAliasForm(data={"email": "not-an-email"}, user=linked_member.user)
        assert not form.is_valid()
