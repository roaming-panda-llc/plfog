"""BDD-style tests for BillingSettings model."""

from decimal import Decimal

import pytest
from django.db import IntegrityError

from billing.models import BillingSettings
from tests.billing.factories import BillingSettingsFactory

pytestmark = pytest.mark.django_db


def describe_BillingSettings():
    def it_is_a_singleton():
        settings = BillingSettingsFactory()
        assert settings.pk == 1

    def it_forces_pk_1_on_save():
        settings = BillingSettings(pk=99, default_tab_limit=Decimal("100.00"))
        settings.save()
        settings.refresh_from_db()
        assert settings.pk == 1

    def it_loads_with_defaults():
        settings = BillingSettings.load()
        assert settings.pk == 1
        assert settings.charge_frequency == BillingSettings.ChargeFrequency.MONTHLY
        assert settings.default_tab_limit == Decimal("200.00")
        assert settings.max_retry_attempts == 3
        assert settings.retry_interval_hours == 24

    def it_has_str_representation():
        settings = BillingSettingsFactory()
        assert str(settings) == "Billing Settings"

    def describe_next_charge_at():
        def it_returns_none_when_off():
            settings = BillingSettingsFactory(charge_frequency=BillingSettings.ChargeFrequency.OFF)
            assert settings.next_charge_at() is None

        def it_returns_a_future_datetime_for_daily():
            from django.utils import timezone as _tz

            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.DAILY,
                charge_time="23:00",
            )
            result = settings.next_charge_at()
            assert result is not None
            assert result > _tz.localtime()

        def it_returns_a_future_datetime_for_weekly():
            from django.utils import timezone as _tz

            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.WEEKLY,
                charge_day_of_week=0,
                charge_day_of_month=None,
                charge_time="12:00",
            )
            result = settings.next_charge_at()
            assert result is not None
            assert result > _tz.localtime()
            assert result.weekday() == 0

        def it_returns_a_future_datetime_for_monthly():
            from django.utils import timezone as _tz

            settings = BillingSettingsFactory(
                charge_frequency=BillingSettings.ChargeFrequency.MONTHLY,
                charge_day_of_month=15,
                charge_day_of_week=None,
                charge_time="09:00",
            )
            result = settings.next_charge_at()
            assert result is not None
            assert result > _tz.localtime()
            assert result.day == 15

    def describe_charge_frequency():
        def it_defaults_to_monthly():
            settings = BillingSettings.load()
            assert settings.charge_frequency == BillingSettings.ChargeFrequency.MONTHLY

        def it_accepts_all_valid_frequencies():
            for freq in BillingSettings.ChargeFrequency:
                settings = BillingSettings.load()
                settings.charge_frequency = freq
                if freq == BillingSettings.ChargeFrequency.WEEKLY:
                    settings.charge_day_of_week = 0
                    settings.charge_day_of_month = None
                elif freq == BillingSettings.ChargeFrequency.MONTHLY:
                    settings.charge_day_of_week = None
                    settings.charge_day_of_month = 1
                else:
                    settings.charge_day_of_week = None
                    settings.charge_day_of_month = None
                settings.save()
                settings.refresh_from_db()
                assert settings.charge_frequency == freq

    def describe_cross_field_constraints():
        def it_rejects_day_of_week_when_not_weekly():
            settings = BillingSettings.load()
            settings.charge_frequency = BillingSettings.ChargeFrequency.MONTHLY
            settings.charge_day_of_week = 3
            with pytest.raises(IntegrityError):
                settings.save()

        def it_rejects_day_of_month_when_not_monthly():
            settings = BillingSettings.load()
            settings.charge_frequency = BillingSettings.ChargeFrequency.WEEKLY
            settings.charge_day_of_month = 15
            settings.charge_day_of_week = 0
            with pytest.raises(IntegrityError):
                settings.save()

        def it_rejects_day_of_week_above_6():
            settings = BillingSettings.load()
            settings.charge_frequency = BillingSettings.ChargeFrequency.WEEKLY
            settings.charge_day_of_week = 7
            settings.charge_day_of_month = None
            with pytest.raises(IntegrityError):
                settings.save()

        def it_rejects_day_of_month_above_28():
            settings = BillingSettings.load()
            settings.charge_frequency = BillingSettings.ChargeFrequency.MONTHLY
            settings.charge_day_of_month = 29
            settings.charge_day_of_week = None
            with pytest.raises(IntegrityError):
                settings.save()

        def it_rejects_day_of_month_below_1():
            settings = BillingSettings.load()
            settings.charge_frequency = BillingSettings.ChargeFrequency.MONTHLY
            settings.charge_day_of_month = 0
            settings.charge_day_of_week = None
            with pytest.raises(IntegrityError):
                settings.save()

        def it_allows_day_of_week_when_weekly():
            settings = BillingSettings.load()
            settings.charge_frequency = BillingSettings.ChargeFrequency.WEEKLY
            settings.charge_day_of_week = 4
            settings.charge_day_of_month = None
            settings.save()
            settings.refresh_from_db()
            assert settings.charge_day_of_week == 4

        def it_allows_day_of_month_when_monthly():
            settings = BillingSettings.load()
            settings.charge_frequency = BillingSettings.ChargeFrequency.MONTHLY
            settings.charge_day_of_month = 28
            settings.charge_day_of_week = None
            settings.save()
            settings.refresh_from_db()
            assert settings.charge_day_of_month == 28

    def describe_clean_connect_validation():
        def it_passes_when_connect_disabled_and_fields_empty():
            settings = BillingSettings.load()
            settings.connect_enabled = False
            settings.clean()  # should not raise

        def it_passes_when_connect_enabled_and_all_fields_set():
            settings = BillingSettings.load()
            settings.connect_enabled = True
            settings.connect_client_id = "ca_test_1"
            settings.connect_platform_publishable_key = "pk_test_1"
            settings.connect_platform_secret_key = "sk_test_1"
            settings.connect_platform_webhook_secret = "whsec_1"
            settings.clean()  # should not raise

        def it_raises_when_enabled_with_missing_client_id():
            from django.core.exceptions import ValidationError

            settings = BillingSettings.load()
            settings.connect_enabled = True
            settings.connect_platform_publishable_key = "pk_x"
            settings.connect_platform_secret_key = "sk_x"
            settings.connect_platform_webhook_secret = "whsec_x"
            settings.connect_client_id = ""
            with pytest.raises(ValidationError) as excinfo:
                settings.clean()
            assert "connect_client_id" in excinfo.value.message_dict

        def it_raises_when_enabled_with_all_fields_missing():
            from django.core.exceptions import ValidationError

            settings = BillingSettings.load()
            settings.connect_enabled = True
            settings.connect_client_id = ""
            settings.connect_platform_publishable_key = ""
            settings.connect_platform_secret_key = ""
            settings.connect_platform_webhook_secret = ""
            with pytest.raises(ValidationError) as excinfo:
                settings.clean()
            assert "connect_client_id" in excinfo.value.message_dict
            assert "connect_platform_publishable_key" in excinfo.value.message_dict
            assert "connect_platform_secret_key" in excinfo.value.message_dict
            assert "connect_platform_webhook_secret" in excinfo.value.message_dict
