"""BDD specs for CalendarEvent model and Guild calendar fields."""

from __future__ import annotations

import pytest

from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db


def describe_Guild_calendar_fields():
    def it_has_default_calendar_color():
        guild = GuildFactory()
        assert guild.calendar_color == "#4B9FEE"

    def it_stores_calendar_url():
        guild = GuildFactory(
            calendar_url="https://calendar.google.com/calendar/ical/test%40group.calendar.google.com/public/basic.ics"
        )
        assert "calendar.google.com" in guild.calendar_url

    def it_calendar_last_fetched_at_defaults_to_null():
        guild = GuildFactory()
        assert guild.calendar_last_fetched_at is None


def describe_SiteConfiguration_calendar_fields():
    def it_has_default_general_calendar_color():
        from core.models import SiteConfiguration

        config = SiteConfiguration.load()
        assert config.general_calendar_color == "#EEB44B"

    def it_general_calendar_url_defaults_to_blank():
        from core.models import SiteConfiguration

        config = SiteConfiguration.load()
        assert config.general_calendar_url == ""

    def it_general_calendar_last_fetched_at_defaults_to_null():
        from core.models import SiteConfiguration

        config = SiteConfiguration.load()
        assert config.general_calendar_last_fetched_at is None
