"""BDD-style tests for core.admin — SiteConfigurationAdmin."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.admin import SiteConfigurationAdmin
from core.models import SiteConfiguration

User = get_user_model()

pytestmark = pytest.mark.django_db


def describe_SiteConfigurationAdmin():
    @pytest.fixture()
    def admin_instance():
        from django.contrib.admin.sites import AdminSite

        return SiteConfigurationAdmin(SiteConfiguration, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    @pytest.fixture()
    def staff_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=False)
        return request

    def it_prevents_add_when_singleton_exists(admin_instance, superuser_request):
        SiteConfiguration.load()  # Ensure singleton exists
        assert admin_instance.has_add_permission(superuser_request) is False

    def it_allows_add_when_no_singleton(admin_instance, superuser_request):
        SiteConfiguration.objects.all().delete()
        assert admin_instance.has_add_permission(superuser_request) is True

    def it_never_allows_delete(admin_instance, superuser_request):
        assert admin_instance.has_delete_permission(superuser_request) is False

    def it_never_allows_delete_for_object(admin_instance, superuser_request):
        config = SiteConfiguration.load()
        assert admin_instance.has_delete_permission(superuser_request, obj=config) is False

    def it_redirects_changelist_to_edit_form():
        SiteConfiguration.load()
        user = User.objects.create_superuser(username="cfg-admin", password="pass", email="cfg@example.com")
        client = Client()
        client.force_login(user)
        resp = client.get("/admin/core/siteconfiguration/")
        assert resp.status_code == 302
        assert "/admin/core/siteconfiguration/1/change/" in resp.url

    def describe_permission_restrictions():
        def it_denies_module_access_for_non_superuser(admin_instance, staff_request):
            assert admin_instance.has_module_permission(staff_request) is False

        def it_allows_module_access_for_superuser(admin_instance, superuser_request):
            assert admin_instance.has_module_permission(superuser_request) is True

        def it_denies_view_for_non_superuser(admin_instance, staff_request):
            assert admin_instance.has_view_permission(staff_request) is False

        def it_allows_view_for_superuser(admin_instance, superuser_request):
            assert admin_instance.has_view_permission(superuser_request) is True

        def it_denies_change_for_non_superuser(admin_instance, staff_request):
            assert admin_instance.has_change_permission(staff_request) is False

        def it_allows_change_for_superuser(admin_instance, superuser_request):
            assert admin_instance.has_change_permission(superuser_request) is True

        def it_denies_add_for_non_superuser(admin_instance, staff_request):
            SiteConfiguration.objects.all().delete()
            assert admin_instance.has_add_permission(staff_request) is False
