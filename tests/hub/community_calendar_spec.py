"""BDD specs for Community Calendar views and calendar service."""

from __future__ import annotations

import textwrap
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from membership.models import CalendarEvent
from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Minimal valid iCal fixture
# ---------------------------------------------------------------------------

SAMPLE_ICAL = textwrap.dedent("""\
    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Test//Test//EN
    BEGIN:VEVENT
    UID:event-001@test.com
    SUMMARY:Open Studio Hours
    DTSTART:20260501T160000Z
    DTEND:20260501T200000Z
    DESCRIPTION:All members welcome
    LOCATION:Common Area
    END:VEVENT
    BEGIN:VEVENT
    UID:event-002@test.com
    SUMMARY:Woodshop Safety Class
    DTSTART:20260503T180000Z
    DTEND:20260503T200000Z
    END:VEVENT
    END:VCALENDAR
""").encode()


def _fake_urlopen(url, **kwargs):
    mock_response = MagicMock()
    mock_response.read.return_value = SAMPLE_ICAL
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def describe_calendar_service():
    def describe_sync_guild_calendar():
        def it_creates_calendar_events_for_a_guild():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                count = sync_guild_calendar(guild)
            assert count == 2
            events = CalendarEvent.objects.filter(guild=guild)
            assert events.count() == 2
            titles = set(events.values_list("title", flat=True))
            assert titles == {"Open Studio Hours", "Woodshop Safety Class"}

        def it_updates_existing_events_on_resync():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                sync_guild_calendar(guild)
                count = sync_guild_calendar(guild)
            assert count == 2
            assert CalendarEvent.objects.filter(guild=guild).count() == 2

        def it_sets_calendar_last_fetched_at_on_guild():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            assert guild.calendar_last_fetched_at is None
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                sync_guild_calendar(guild)
            guild.refresh_from_db()
            assert guild.calendar_last_fetched_at is not None

        def it_returns_zero_when_guild_has_no_calendar_url():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="")
            count = sync_guild_calendar(guild)
            assert count == 0

    def describe_sync_general_calendar():
        def it_creates_general_events_with_null_guild():
            from core.models import SiteConfiguration
            from hub.calendar_service import sync_general_calendar

            config = SiteConfiguration.load()
            config.general_calendar_url = "https://calendar.google.com/calendar/ical/general.ics"
            config.save()
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                count = sync_general_calendar()
            assert count == 2
            assert CalendarEvent.objects.filter(guild__isnull=True).count() == 2

        def it_returns_zero_when_no_general_calendar_configured():
            from hub.calendar_service import sync_general_calendar

            count = sync_general_calendar()
            assert count == 0

    def describe_refresh_stale_sources():
        def it_skips_sources_fetched_recently():
            from hub.calendar_service import refresh_stale_sources

            recent = timezone.now()
            GuildFactory(
                calendar_url="https://example.com/cal.ics",
                calendar_last_fetched_at=recent,
            )
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen) as mock_open:
                refresh_stale_sources(max_age_seconds=900)
            mock_open.assert_not_called()

        def it_refreshes_stale_guild_sources():
            from datetime import timedelta

            from hub.calendar_service import refresh_stale_sources

            stale_time = timezone.now() - timedelta(seconds=1000)
            guild = GuildFactory(
                calendar_url="https://example.com/cal.ics",
                calendar_last_fetched_at=stale_time,
            )
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                refresh_stale_sources(max_age_seconds=900)
            guild.refresh_from_db()
            assert guild.calendar_last_fetched_at >= timezone.now() - timedelta(seconds=5)


def describe_GuildEditForm():
    def it_saves_calendar_url_and_color():
        from hub.forms import GuildEditForm

        guild = GuildFactory()
        form = GuildEditForm(
            data={
                "name": guild.name,
                "about": "Some about text",
                "calendar_url": "https://calendar.google.com/calendar/ical/test.ics",
                "calendar_color": "#FF6B6B",
            },
            instance=guild,
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.calendar_url == "https://calendar.google.com/calendar/ical/test.ics"
        assert saved.calendar_color == "#FF6B6B"

    def it_accepts_empty_calendar_url():
        from hub.forms import GuildEditForm

        guild = GuildFactory()
        form = GuildEditForm(
            data={"name": guild.name, "about": "", "calendar_url": "", "calendar_color": "#4B9FEE"},
            instance=guild,
        )
        assert form.is_valid(), form.errors

    def it_rejects_invalid_calendar_url():
        from hub.forms import GuildEditForm

        guild = GuildFactory()
        form = GuildEditForm(
            data={"name": guild.name, "about": "", "calendar_url": "not-a-url", "calendar_color": "#4B9FEE"},
            instance=guild,
        )
        assert not form.is_valid()
        assert "calendar_url" in form.errors
