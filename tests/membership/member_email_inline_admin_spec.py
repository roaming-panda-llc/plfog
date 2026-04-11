"""Admin inline behavior for the MemberEmail staging table.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from membership.admin import MemberAdmin, MemberEmailInline
from membership.models import Member
from tests.membership.factories import MemberFactory, MembershipPlanFactory

User = get_user_model()


def describe_MemberEmailInline_fields():
    def it_does_not_expose_is_primary(db):
        assert "is_primary" not in list(MemberEmailInline.fields)

    def it_only_exposes_email(db):
        assert list(MemberEmailInline.fields) == ["email"]


def describe_MemberAdmin_inline_visibility():
    def it_hides_staging_inline_for_linked_members(db):
        MembershipPlanFactory()
        user = User.objects.create_user(username="linkeduser", email="linked@example.com")
        member = user.member  # signal created it

        rf = RequestFactory()
        request = rf.get("/")
        request.user = User.objects.create_superuser(username="admin1", email="admin1@example.com", password="x")
        model_admin = MemberAdmin(Member, admin.site)

        instances = model_admin.get_inline_instances(request, obj=member)
        assert not any(isinstance(i, MemberEmailInline) for i in instances)

    def it_shows_staging_inline_for_unlinked_members(db):
        member = MemberFactory(user=None)

        rf = RequestFactory()
        request = rf.get("/")
        request.user = User.objects.create_superuser(username="admin2", email="admin2@example.com", password="x")
        model_admin = MemberAdmin(Member, admin.site)

        instances = model_admin.get_inline_instances(request, obj=member)
        assert any(isinstance(i, MemberEmailInline) for i in instances)

    def it_shows_staging_inline_on_add_form(db):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = User.objects.create_superuser(username="admin3", email="admin3@example.com", password="x")
        model_admin = MemberAdmin(Member, admin.site)

        instances = model_admin.get_inline_instances(request, obj=None)
        assert any(isinstance(i, MemberEmailInline) for i in instances)
