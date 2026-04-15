"""BDD-style tests for billing-related forms."""

from __future__ import annotations

from decimal import Decimal

import pytest

from billing.forms import (
    CONTEXT_ADMIN_DASHBOARD,
    BillingSettingsForm,
    ConnectPlatformSettingsForm,
    CustomSplitFormSet,
    TabItemForm,
    VoidTabEntryForm,
)
from billing.models import TabEntrySplit
from tests.billing.factories import BillingSettingsFactory, ProductFactory, TabFactory
from tests.membership.factories import GuildFactory

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


def describe_TabItemForm():
    def describe_save_with_product():
        def it_creates_an_entry_with_product_splits():
            BillingSettingsFactory()
            product = ProductFactory()
            tab = TabFactory()
            form = TabItemForm(
                data={
                    "description": "x",
                    "amount": "10.00",
                    "product": product.pk,
                    "member": tab.member.pk,
                },
                context=CONTEXT_ADMIN_DASHBOARD,
            )
            assert form.is_valid(), form.errors
            entry = form.save(tab=tab)
            assert entry.splits.count() >= 1

    def describe_save_with_custom_splits():
        def it_creates_an_entry_with_explicit_splits():
            BillingSettingsFactory()
            tab = TabFactory()
            form = TabItemForm(
                data={
                    "description": "custom",
                    "amount": "10.00",
                    "member": tab.member.pk,
                },
                context=CONTEXT_ADMIN_DASHBOARD,
            )
            assert form.is_valid(), form.errors
            entry = form.save(
                tab=tab,
                splits=[
                    {
                        "recipient_type": "admin",
                        "guild": None,
                        "percent": Decimal("100"),
                    },
                ],
            )
            assert entry.splits.count() == 1
            only = entry.splits.first()
            assert only.recipient_type == TabEntrySplit.RecipientType.ADMIN

        def it_raises_when_custom_entry_has_no_splits():
            BillingSettingsFactory()
            tab = TabFactory()
            form = TabItemForm(
                data={
                    "description": "custom",
                    "amount": "10.00",
                    "member": tab.member.pk,
                },
                context=CONTEXT_ADMIN_DASHBOARD,
            )
            assert form.is_valid(), form.errors
            with pytest.raises(ValueError):
                form.save(tab=tab)

    def describe_custom_split_formset():
        def _make_data(rows: list[tuple[str, str, str]]) -> dict[str, str]:
            data: dict[str, str] = {
                "splits-TOTAL_FORMS": str(len(rows)),
                "splits-INITIAL_FORMS": "0",
                "splits-MIN_NUM_FORMS": "1",
                "splits-MAX_NUM_FORMS": "1000",
            }
            for i, (rtype, guild, percent) in enumerate(rows):
                data[f"splits-{i}-recipient_type"] = rtype
                data[f"splits-{i}-guild"] = guild
                data[f"splits-{i}-percent"] = percent
            return data

        def it_rejects_when_sum_not_100():
            data = _make_data([("admin", "", "50")])
            fs = CustomSplitFormSet(data=data, prefix="splits")
            assert not fs.is_valid()

        def it_accepts_valid_admin_only_split():
            data = _make_data([("admin", "", "100")])
            fs = CustomSplitFormSet(data=data, prefix="splits")
            assert fs.is_valid(), fs.errors
            dicts = fs.to_split_dicts()
            assert len(dicts) == 1
            assert dicts[0]["recipient_type"] == "admin"
            assert dicts[0]["percent"] == Decimal("100")

        def it_rejects_duplicate_guild_rows():
            guild = GuildFactory()
            data = _make_data(
                [
                    ("guild", str(guild.pk), "50"),
                    ("guild", str(guild.pk), "50"),
                ]
            )
            fs = CustomSplitFormSet(data=data, prefix="splits")
            assert not fs.is_valid()

        def it_rejects_admin_row_with_guild():
            guild = GuildFactory()
            data = _make_data([("admin", str(guild.pk), "100")])
            fs = CustomSplitFormSet(data=data, prefix="splits")
            assert not fs.is_valid()

        def it_rejects_guild_row_without_guild():
            data = _make_data([("guild", "", "100")])
            fs = CustomSplitFormSet(data=data, prefix="splits")
            assert not fs.is_valid()
