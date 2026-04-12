"""Tests for billing.fields.EncryptedCharField."""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from billing.fields import EncryptedCharField, _fernet
from billing.models import BillingSettings

pytestmark = pytest.mark.django_db


def describe_EncryptedCharField():
    def it_round_trips_a_value_through_the_db():
        bs = BillingSettings.load()
        bs.connect_platform_secret_key = "sk_test_roundtrip"
        bs.save()
        bs.refresh_from_db()
        assert bs.connect_platform_secret_key == "sk_test_roundtrip"

    def it_stores_ciphertext_not_plaintext_in_db():
        from django.db import connection

        bs = BillingSettings.load()
        bs.connect_platform_secret_key = "sk_test_supersecret"
        bs.save()
        # Read the raw column with a SQL query to bypass from_db_value.
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT connect_platform_secret_key FROM {BillingSettings._meta.db_table} WHERE id = %s",
                [bs.pk],
            )
            (raw,) = cursor.fetchone()
        assert raw is not None
        assert "sk_test_supersecret" not in raw  # plaintext is not in the column
        assert raw.startswith("gAAAAA")  # Fernet token prefix

    def it_returns_blank_unchanged():
        bs = BillingSettings.load()
        bs.connect_platform_webhook_secret = ""
        bs.save()
        bs.refresh_from_db()
        assert bs.connect_platform_webhook_secret == ""

    def describe_fernet_key_validation():
        def it_raises_when_key_is_missing(settings):
            settings.STRIPE_FIELD_ENCRYPTION_KEY = ""
            with pytest.raises(ImproperlyConfigured, match="STRIPE_FIELD_ENCRYPTION_KEY"):
                _fernet()

        def it_raises_when_key_is_malformed(settings):
            settings.STRIPE_FIELD_ENCRYPTION_KEY = "not-a-valid-fernet-key"
            with pytest.raises(ImproperlyConfigured, match="malformed"):
                _fernet()

    def it_is_a_charfield_subclass():
        from django.db.models import CharField

        assert issubclass(EncryptedCharField, CharField)
