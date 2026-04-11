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


# ---------------------------------------------------------------------------
# describe_member_aliases_page (GET)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_page():
    def it_requires_staff(client, linked_member):
        resp = client.get(f"/admin/members/{linked_member.pk}/aliases/")
        assert resp.status_code == 302
        assert "login" in resp.url

    def it_returns_404_for_nonexistent_member(admin_client):
        resp = admin_client.get("/admin/members/999999/aliases/")
        assert resp.status_code == 404

    def it_renders_the_page_for_a_linked_member(admin_client, linked_member):
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        assert resp.status_code == 200
        assert resp.context["member"] == linked_member
        assert list(resp.context["aliases"]) == list(
            EmailAddress.objects.filter(user=linked_member.user).order_by("-primary", "email")
        )
        assert resp.context["add_form"].__class__.__name__ == "AddEmailAliasForm"

    def it_lists_aliases_with_primary_first(admin_client, linked_member):
        EmailAddress.objects.create(
            user=linked_member.user,
            email="aaa@example.com",
            verified=True,
            primary=False,
        )
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        aliases = list(resp.context["aliases"])
        assert aliases[0].primary is True
        assert aliases[0].email == "penina@example.com"
        assert aliases[1].email == "aaa@example.com"


# ---------------------------------------------------------------------------
# describe_member_aliases_add (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_add():
    def it_requires_staff(client, linked_member):
        resp = client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "new@example.com"},
        )
        assert resp.status_code == 302
        assert "login" in resp.url

    def it_rejects_get(admin_client, linked_member):
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/add/")
        assert resp.status_code == 405

    def it_404s_for_nonexistent_member(admin_client):
        resp = admin_client.post(
            "/admin/members/999999/aliases/add/",
            data={"email": "new@example.com"},
        )
        assert resp.status_code == 404

    def it_creates_verified_non_primary_email(admin_client, linked_member):
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "writersguild@pastlives.space"},
        )
        assert resp.status_code == 302
        assert resp.url == f"/admin/members/{linked_member.pk}/aliases/"
        created = EmailAddress.objects.get(
            user=linked_member.user,
            email="writersguild@pastlives.space",
        )
        assert created.verified is True
        assert created.primary is False

    def it_leaves_existing_primary_untouched(admin_client, linked_member):
        admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "new@example.com"},
        )
        primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        assert primary.email == "penina@example.com"

    def it_rejects_duplicate_on_same_user(admin_client, linked_member):
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "penina@example.com"},
        )
        assert resp.status_code == 200  # re-renders page with form errors
        assert EmailAddress.objects.filter(user=linked_member.user).count() == 1

    def it_rejects_duplicate_on_other_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        EmailAddress.objects.create(user=other, email="shared@example.com", verified=True, primary=False)
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "shared@example.com"},
        )
        assert resp.status_code == 200
        assert not EmailAddress.objects.filter(
            user=linked_member.user,
            email__iexact="shared@example.com",
        ).exists()
