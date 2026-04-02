import pytest

from django.conf import settings


def pytest_configure():
    settings.DJANGO_SETTINGS_MODULE = "plfog.settings"


def pytest_sessionstart(session):
    from django.conf import settings as django_settings

    django_settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(autouse=True)
def _disable_airtable_sync(settings):
    """Disable Airtable sync in all tests by default."""
    settings.AIRTABLE_SYNC_ENABLED = False


@pytest.fixture(autouse=True)
def _fake_stripe_keys(settings):
    """Use fake Stripe keys in all tests to prevent accidental live calls."""
    settings.STRIPE_SECRET_KEY = "sk_test_fake_for_testing"
    settings.STRIPE_PUBLISHABLE_KEY = "pk_test_fake_for_testing"
    settings.STRIPE_WEBHOOK_SECRET = "whsec_fake_for_testing"
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test_fake_for_testing"
