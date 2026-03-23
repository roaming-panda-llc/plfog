"""BDD-style tests for core.admin — SiteConfigurationAdmin and InviteAdmin."""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory

from core.admin import InviteAdmin, SiteConfigurationAdmin
from core.models import Invite, SiteConfiguration

pytestmark = pytest.mark.django_db


def describe_SiteConfigurationAdmin():
    @pytest.fixture()
    def admin_instance():
        from django.contrib.admin.sites import AdminSite

        return SiteConfigurationAdmin(SiteConfiguration, AdminSite())

    def it_prevents_add_when_singleton_exists(admin_instance):
        SiteConfiguration.load()  # Ensure singleton exists
        rf = RequestFactory()
        request = rf.get("/admin/")
        assert admin_instance.has_add_permission(request) is False

    def it_allows_add_when_no_singleton(admin_instance):
        SiteConfiguration.objects.all().delete()
        rf = RequestFactory()
        request = rf.get("/admin/")
        assert admin_instance.has_add_permission(request) is True

    def it_never_allows_delete(admin_instance):
        rf = RequestFactory()
        request = rf.get("/admin/")
        assert admin_instance.has_delete_permission(request) is False

    def it_never_allows_delete_for_object(admin_instance):
        config = SiteConfiguration.load()
        rf = RequestFactory()
        request = rf.get("/admin/")
        assert admin_instance.has_delete_permission(request, obj=config) is False


def describe_InviteAdmin():
    @pytest.fixture()
    def admin_user():
        return User.objects.create_superuser(username="admin", email="admin@example.com", password="testpass")

    @pytest.fixture()
    def admin_instance():
        from django.contrib.admin.sites import AdminSite

        return InviteAdmin(Invite, AdminSite())

    def it_sets_invited_by_on_create(admin_instance, admin_user):
        rf = RequestFactory()
        request = rf.post("/admin/core/invite/add/")
        request.user = admin_user

        invite = Invite(email="new@example.com")
        with patch.object(Invite, "send_invite_email"):
            admin_instance.save_model(request, invite, form=None, change=False)

        invite.refresh_from_db()
        assert invite.invited_by == admin_user

    def it_sends_invite_email_on_create(admin_instance, admin_user):
        rf = RequestFactory()
        request = rf.post("/admin/core/invite/add/")
        request.user = admin_user

        invite = Invite(email="send@example.com")
        with patch.object(Invite, "send_invite_email") as mock_send:
            admin_instance.save_model(request, invite, form=None, change=False)
            mock_send.assert_called_once()

    def it_does_not_send_email_on_update(admin_instance, admin_user):
        rf = RequestFactory()
        request = rf.post("/admin/core/invite/1/change/")
        request.user = admin_user

        invite = Invite.objects.create(email="existing@example.com", invited_by=admin_user)
        with patch.object(Invite, "send_invite_email") as mock_send:
            admin_instance.save_model(request, invite, form=None, change=True)
            mock_send.assert_not_called()

    def it_does_not_overwrite_invited_by_on_update(admin_instance, admin_user):
        other_user = User.objects.create_user(username="other", email="other@example.com", password="testpass")
        invite = Invite.objects.create(email="keep@example.com", invited_by=other_user)

        rf = RequestFactory()
        request = rf.post("/admin/core/invite/1/change/")
        request.user = admin_user

        with patch.object(Invite, "send_invite_email"):
            admin_instance.save_model(request, invite, form=None, change=True)

        invite.refresh_from_db()
        assert invite.invited_by == other_user

    def it_shows_pending_status_as_boolean(admin_instance, admin_user):
        invite = Invite.objects.create(email="pending@example.com", invited_by=admin_user)
        assert admin_instance.is_pending_display(invite) is True

        invite.mark_accepted()
        assert admin_instance.is_pending_display(invite) is False

    def it_has_readonly_fields():
        from django.contrib.admin.sites import AdminSite

        admin_instance = InviteAdmin(Invite, AdminSite())
        assert "invited_by" in admin_instance.readonly_fields
        assert "created_at" in admin_instance.readonly_fields
        assert "accepted_at" in admin_instance.readonly_fields

    def it_uses_select_related_on_queryset(admin_instance, admin_user):
        rf = RequestFactory()
        request = rf.get("/admin/core/invite/")
        request.user = admin_user
        qs = admin_instance.get_queryset(request)
        assert "invited_by" in str(qs.query)
