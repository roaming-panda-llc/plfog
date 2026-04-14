"""BDD-style tests for billing-related forms.

TODO(splits): rewrite in Task 7 — ``TabItemForm`` is stripped to a stub during
the v1.7 product-revenue-splits refactor. Task 7 rebuilds the form on top of
``ProductRevenueSplit`` and restores this test suite. The remaining simple
tests that don't touch splits (``BillingSettingsForm``, ``VoidTabEntryForm``,
``ConnectPlatformSettingsForm``) are preserved below.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from billing.forms import (
    BillingSettingsForm,
    ConnectPlatformSettingsForm,
    VoidTabEntryForm,
)
from tests.billing.factories import BillingSettingsFactory

pytestmark = pytest.mark.django_db


def describe_VoidTabEntryForm():
    def it_requires_reason():
        form = VoidTabEntryForm(data={})
        assert not form.is_valid()
        assert "reason" in form.errors

    def it_is_valid_with_reason():
        form = VoidTabEntryForm(data={"reason": "Duplicate"})
        assert form.is_valid()


def describe_BillingSettingsForm():
    def it_saves_valid_settings():
        form = BillingSettingsForm(
            data={
                "charge_frequency": "monthly",
                "charge_time": "23:00",
                "charge_day_of_month": "1",
                "default_tab_limit": "200.00",
                "default_admin_percent": "20.00",
                "max_retry_attempts": "3",
                "retry_interval_hours": "24",
            }
        )
        assert form.is_valid(), form.errors

    def it_rejects_negative_tab_limit():
        form = BillingSettingsForm(
            data={
                "charge_frequency": "monthly",
                "charge_time": "23:00",
                "charge_day_of_month": "1",
                "default_tab_limit": "-5.00",
                "default_admin_percent": "20.00",
                "max_retry_attempts": "3",
                "retry_interval_hours": "24",
            }
        )
        assert not form.is_valid()
        assert "default_tab_limit" in form.errors


def describe_ConnectPlatformSettingsForm():
    def it_saves_when_connect_is_disabled():
        settings = BillingSettingsFactory()
        form = ConnectPlatformSettingsForm(
            instance=settings,
            data={
                "connect_enabled": False,
                "connect_client_id": "",
                "connect_platform_publishable_key": "",
                "connect_platform_secret_key": "",
                "connect_platform_webhook_secret": "",
            },
        )
        assert form.is_valid(), form.errors

    def it_requires_all_keys_when_connect_is_enabled():
        settings = BillingSettingsFactory()
        form = ConnectPlatformSettingsForm(
            instance=settings,
            data={
                "connect_enabled": True,
                "connect_client_id": "",
                "connect_platform_publishable_key": "",
                "connect_platform_secret_key": "",
                "connect_platform_webhook_secret": "",
            },
        )
        assert not form.is_valid()
        for field in (
            "connect_client_id",
            "connect_platform_publishable_key",
            "connect_platform_secret_key",
            "connect_platform_webhook_secret",
        ):
            assert field in form.errors

    def it_accepts_full_credential_set():
        settings = BillingSettingsFactory()
        form = ConnectPlatformSettingsForm(
            instance=settings,
            data={
                "connect_enabled": True,
                "connect_client_id": "ca_123",
                "connect_platform_publishable_key": "pk_test_123",
                "connect_platform_secret_key": "sk_test_123",
                "connect_platform_webhook_secret": "whsec_test_123",
            },
        )
        assert form.is_valid(), form.errors


# TODO(splits): the large ``TabItemForm`` test suite that used to live here is
# parked until Task 7 rebuilds the form around ``ProductRevenueSplit``.
# See the 2026-04-14-product-revenue-splits plan, Task 7.
_ = Decimal  # keep Decimal import live for future additions
