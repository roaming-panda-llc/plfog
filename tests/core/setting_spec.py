from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.models import Setting
from tests.core.factories import SettingFactory, UserFactory

User = get_user_model()


@pytest.mark.django_db
def describe_setting_model():
    def it_has_str_representation():
        setting = SettingFactory(key="my_key")
        assert str(setting) == "my_key"

    def it_stores_json_value():
        payload = {"foo": "bar", "count": 42}
        setting = SettingFactory(key="json_test", value=payload, type="json")
        setting.refresh_from_db()
        assert setting.value == payload

    def it_tracks_updated_by():
        user = UserFactory()
        setting = SettingFactory(key="user_setting", updated_by=user)
        setting.refresh_from_db()
        assert setting.updated_by == user

    def it_get_returns_value():
        SettingFactory(key="lookup_key", value={"enabled": True}, type="json")
        result = Setting.get("lookup_key")
        assert result == {"enabled": True}

    def it_get_returns_cached_value_on_second_call():
        SettingFactory(key="cached_key", value={"cached": True}, type="json")
        Setting.get("cached_key")  # populates cache
        result = Setting.get("cached_key")  # hits cache (line 32)
        assert result == {"cached": True}

    def it_get_returns_default_when_missing():
        result = Setting.get("nope", "fb")
        assert result == "fb"

    def it_set_creates_setting():
        Setting.set("new_key", {"created": True}, type="json")
        assert Setting.objects.filter(key="new_key").exists()
        assert Setting.objects.get(key="new_key").value == {"created": True}

    def it_set_updates_existing():
        SettingFactory(key="update_key", value={"old": True}, type="json")
        Setting.set("update_key", {"new": True}, type="json")
        updated = Setting.objects.get(key="update_key")
        assert updated.value == {"new": True}


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="core-admin-test",
        password="core-admin-test-pw",
        email="core-admin-test@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def describe_setting_admin():
    def it_loads_changelist(admin_client):
        response = admin_client.get("/admin/core/setting/")
        assert response.status_code == 200
