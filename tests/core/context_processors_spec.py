"""BDD-style tests for core.context_processors — registration_mode."""

import pytest
from django.test import RequestFactory

from core.context_processors import registration_mode
from core.models import SiteConfiguration

pytestmark = pytest.mark.django_db


def describe_registration_mode():
    def it_returns_true_when_open():
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.OPEN
        config.save()

        rf = RequestFactory()
        request = rf.get("/")
        result = registration_mode(request)
        assert result == {"registration_is_open": True}

    def it_returns_false_when_invite_only():
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
        config.save()

        rf = RequestFactory()
        request = rf.get("/")
        result = registration_mode(request)
        assert result == {"registration_is_open": False}

    def it_defaults_to_invite_only():
        rf = RequestFactory()
        request = rf.get("/")
        result = registration_mode(request)
        assert result == {"registration_is_open": False}
