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

    def it_redirects_unlinked_members_to_the_member_change_page(admin_client, unlinked_member):
        resp = admin_client.get(f"/admin/members/{unlinked_member.pk}/aliases/")
        assert resp.status_code == 302
        assert f"/admin/membership/member/{unlinked_member.pk}/change/" in resp.url


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


# ---------------------------------------------------------------------------
# describe_member_aliases_remove (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_remove():
    def _alias(user, email, *, verified=True, primary=False):
        return EmailAddress.objects.create(user=user, email=email, verified=verified, primary=primary)

    def it_requires_staff(client, linked_member):
        alias = _alias(linked_member.user, "gone@example.com")
        resp = client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/remove/")
        assert resp.status_code == 302
        assert "login" in resp.url
        assert EmailAddress.objects.filter(pk=alias.pk).exists()

    def it_rejects_get(admin_client, linked_member):
        alias = _alias(linked_member.user, "gone@example.com")
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/remove/")
        assert resp.status_code == 405

    def it_deletes_non_primary_email(admin_client, linked_member):
        alias = _alias(linked_member.user, "gone@example.com")
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/remove/")
        assert resp.status_code == 302
        assert resp.url == f"/admin/members/{linked_member.pk}/aliases/"
        assert not EmailAddress.objects.filter(pk=alias.pk).exists()

    def it_refuses_when_it_is_the_only_email(admin_client, linked_member):
        only = EmailAddress.objects.get(user=linked_member.user)
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{only.pk}/remove/")
        assert resp.status_code == 302
        assert EmailAddress.objects.filter(pk=only.pk).exists()

    def it_promotes_lowest_pk_verified_to_primary_when_removing_primary(admin_client, linked_member):
        beta = _alias(linked_member.user, "beta@example.com", verified=True, primary=False)
        _alias(linked_member.user, "gamma@example.com", verified=True, primary=False)
        original_primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{original_primary.pk}/remove/")
        beta.refresh_from_db()
        assert beta.primary is True

    def it_proceeds_and_warns_when_removing_last_verified_email(admin_client, linked_member):
        unverified = _alias(linked_member.user, "unverified@example.com", verified=False, primary=False)
        primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{primary.pk}/remove/")
        assert resp.status_code == 302
        assert not EmailAddress.objects.filter(pk=primary.pk).exists()
        assert EmailAddress.objects.filter(pk=unverified.pk).exists()

    def it_404s_for_email_belonging_to_another_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        # Signal auto-creates the primary EmailAddress for other@example.com — use it directly.
        other_alias = EmailAddress.objects.get(user=other, email="other@example.com")
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{other_alias.pk}/remove/")
        assert resp.status_code == 404
        assert EmailAddress.objects.filter(pk=other_alias.pk).exists()


# ---------------------------------------------------------------------------
# describe_member_aliases_set_primary (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_set_primary():
    def it_requires_staff(client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        resp = client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/")
        assert resp.status_code == 302
        assert "login" in resp.url
        alias.refresh_from_db()
        assert alias.primary is False

    def it_rejects_get(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/")
        assert resp.status_code == 405

    def it_demotes_old_primary_and_promotes_target(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/")
        assert resp.status_code == 302
        alias.refresh_from_db()
        old = EmailAddress.objects.get(email="penina@example.com")
        assert alias.primary is True
        assert old.primary is False

    def it_syncs_user_email_to_new_primary(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/")
        linked_member.user.refresh_from_db()
        assert linked_member.user.email == "new@example.com"

    def it_refuses_unverified_email(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user,
            email="unverified@example.com",
            verified=False,
            primary=False,
        )
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/")
        assert resp.status_code == 302
        alias.refresh_from_db()
        assert alias.primary is False
        original = EmailAddress.objects.get(email="penina@example.com")
        assert original.primary is True

    def it_404s_for_email_belonging_to_another_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        # Signal auto-creates the primary EmailAddress for other@example.com — use it directly.
        other_alias = EmailAddress.objects.get(user=other, email="other@example.com")
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{other_alias.pk}/set-primary/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# describe_member_aliases_toggle_verified (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_toggle_verified():
    def it_requires_staff(client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=False, primary=False
        )
        resp = client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/")
        assert resp.status_code == 302
        assert "login" in resp.url
        alias.refresh_from_db()
        assert alias.verified is False

    def it_rejects_get(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=False, primary=False
        )
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/")
        assert resp.status_code == 405

    def it_flips_verified_from_false_to_true(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=False, primary=False
        )
        admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/")
        alias.refresh_from_db()
        assert alias.verified is True

    def it_flips_verified_from_true_to_false(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/")
        alias.refresh_from_db()
        assert alias.verified is False

    def it_allows_unverifying_primary_with_warning(admin_client, linked_member):
        primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{primary.pk}/toggle-verified/")
        assert resp.status_code == 302
        primary.refresh_from_db()
        assert primary.verified is False

    def it_404s_for_email_belonging_to_another_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        # Signal auto-creates the primary EmailAddress — use it directly.
        other_alias = EmailAddress.objects.get(user=other, email="other@example.com")
        original_verified = other_alias.verified
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{other_alias.pk}/toggle-verified/")
        assert resp.status_code == 404
        other_alias.refresh_from_db()
        assert other_alias.verified == original_verified


# ---------------------------------------------------------------------------
# describe_email_aliases_link_on_member_admin
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_email_aliases_link_on_member_admin():
    def it_renders_link_for_linked_member(admin_client, linked_member):
        resp = admin_client.get(f"/admin/membership/member/{linked_member.pk}/change/")
        assert resp.status_code == 200
        url = f"/admin/members/{linked_member.pk}/aliases/"
        assert url.encode() in resp.content
        assert b"Manage email aliases" in resp.content

    def it_renders_hint_for_unlinked_member(admin_client, unlinked_member):
        resp = admin_client.get(f"/admin/membership/member/{unlinked_member.pk}/change/")
        assert resp.status_code == 200
        assert b"No linked user yet" in resp.content
