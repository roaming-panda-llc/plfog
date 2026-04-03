"""BDD-style tests for billing admin configuration."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import Client

from billing.admin import (
    BillingSettingsAdmin,
    ProductAdmin,
    StripeAccountAdmin,
    TabAdmin,
    TabChargeAdmin,
    TabEntryAdmin,
    TabEntryInline,
)
from billing.models import BillingSettings, Product, StripeAccount, Tab, TabCharge, TabEntry
from tests.billing.factories import ProductFactory, TabChargeFactory, TabEntryFactory, TabFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


def describe_BillingSettingsAdmin():
    @pytest.fixture()
    def admin_instance():
        return BillingSettingsAdmin(BillingSettings, AdminSite())

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
        BillingSettings.load()
        assert admin_instance.has_add_permission(superuser_request) is False

    def it_allows_add_when_no_singleton(admin_instance, superuser_request):
        BillingSettings.objects.all().delete()
        assert admin_instance.has_add_permission(superuser_request) is True

    def it_never_allows_delete(admin_instance, superuser_request):
        assert admin_instance.has_delete_permission(superuser_request) is False

    def it_never_allows_delete_for_object(admin_instance, superuser_request):
        config = BillingSettings.load()
        assert admin_instance.has_delete_permission(superuser_request, obj=config) is False

    def it_redirects_changelist_to_edit_form():
        BillingSettings.load()
        user = User.objects.create_superuser(username="billing-admin", password="pass", email="billing@example.com")
        client = Client()
        client.force_login(user)
        resp = client.get("/admin/billing/billingsettings/")
        assert resp.status_code == 302
        assert "/admin/billing/billingsettings/1/change/" in resp.url

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
            BillingSettings.objects.all().delete()
            assert admin_instance.has_add_permission(staff_request) is False


def describe_TabEntryInline():
    @pytest.fixture()
    def inline_instance():
        return TabEntryInline(Tab, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    def it_never_allows_add(inline_instance, superuser_request):
        assert inline_instance.has_add_permission(superuser_request) is False

    def it_never_allows_delete(inline_instance, superuser_request):
        assert inline_instance.has_delete_permission(superuser_request) is False

    def it_orders_entries_by_newest_first(inline_instance, superuser_request):
        tab = TabFactory()
        TabEntryFactory(tab=tab, description="First")
        TabEntryFactory(tab=tab, description="Second")
        qs = inline_instance.get_queryset(superuser_request)
        assert qs[0].description == "Second"


def describe_TabAdmin():
    @pytest.fixture()
    def admin_instance():
        return TabAdmin(Tab, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    def it_never_allows_delete(admin_instance, superuser_request):
        assert admin_instance.has_delete_permission(superuser_request) is False

    def it_never_allows_delete_for_object(admin_instance, superuser_request):
        tab = TabFactory()
        assert admin_instance.has_delete_permission(superuser_request, obj=tab) is False

    def it_displays_balance(admin_instance):
        tab = TabFactory()
        TabEntryFactory(tab=tab, amount=10)
        assert "$" in admin_instance.current_balance_display(tab)

    def it_displays_payment_method_status(admin_instance):
        tab_with = TabFactory(stripe_payment_method_id="pm_test")
        tab_without = TabFactory(stripe_payment_method_id="")
        assert admin_instance.has_payment_method_display(tab_with) is True
        assert admin_instance.has_payment_method_display(tab_without) is False


def describe_TabEntryAdmin():
    @pytest.fixture()
    def admin_instance():
        return TabEntryAdmin(TabEntry, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    def it_never_allows_delete(admin_instance, superuser_request):
        assert admin_instance.has_delete_permission(superuser_request) is False

    def it_never_allows_delete_for_object(admin_instance, superuser_request):
        entry = TabEntryFactory()
        assert admin_instance.has_delete_permission(superuser_request, obj=entry) is False


def describe_TabChargeAdmin():
    @pytest.fixture()
    def admin_instance():
        return TabChargeAdmin(TabCharge, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    def it_never_allows_delete(admin_instance, superuser_request):
        assert admin_instance.has_delete_permission(superuser_request) is False

    def it_never_allows_delete_for_object(admin_instance, superuser_request):
        charge = TabChargeFactory()
        assert admin_instance.has_delete_permission(superuser_request, obj=charge) is False


def describe_StripeAccountAdmin():
    @pytest.fixture()
    def admin_instance():
        return StripeAccountAdmin(StripeAccount, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    def it_never_allows_delete(admin_instance, superuser_request):
        assert admin_instance.has_delete_permission(superuser_request) is False


def describe_ProductAdmin():
    @pytest.fixture()
    def admin_instance():
        return ProductAdmin(Product, AdminSite())

    def it_displays_guild_name(admin_instance):
        product = ProductFactory()
        assert admin_instance.guild_name(product) == product.guild.name
