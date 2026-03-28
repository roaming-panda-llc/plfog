"""BDD specs for the default Site setup and _update_default_site."""

from __future__ import annotations

import pytest
from django.contrib.sites.models import Site

from core.apps import _update_default_site


@pytest.mark.django_db
def describe_default_site():
    def it_has_past_lives_domain():
        site = Site.objects.get(pk=1)
        assert site.domain == "pastlives.plaza.codes"

    def it_has_past_lives_name():
        site = Site.objects.get(pk=1)
        assert site.name == "Past Lives Makerspace"


@pytest.mark.django_db
def describe_update_default_site():
    def it_does_nothing_when_site_does_not_exist():
        Site.objects.filter(pk=1).delete()
        _update_default_site(sender=type("FakeSender", (), {}))  # should not raise

    def it_does_nothing_when_domain_is_already_set():
        site = Site.objects.get(pk=1)
        site.domain = "custom.example.org"
        site.name = "Custom"
        site.save(update_fields=["domain", "name"])

        _update_default_site(sender=type("FakeSender", (), {}))

        site.refresh_from_db()
        assert site.domain == "custom.example.org"
        assert site.name == "Custom"
