"""BDD-style tests for core.admin — SiteConfigurationAdmin."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory

from core.admin import SiteConfigurationAdmin
from core.models import SiteConfiguration

User = get_user_model()

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

    def it_redirects_changelist_to_edit_form():
        SiteConfiguration.load()
        user = User.objects.create_superuser(username="cfg-admin", password="pass", email="cfg@example.com")
        client = Client()
        client.force_login(user)
        resp = client.get("/admin/core/siteconfiguration/")
        assert resp.status_code == 302
        assert "/admin/core/siteconfiguration/1/change/" in resp.url
