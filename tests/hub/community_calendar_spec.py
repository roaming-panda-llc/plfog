"""BDD specs for Community Calendar views and calendar service."""

from __future__ import annotations

import textwrap
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from membership.models import CalendarEvent
from tests.membership.factories import GuildFactory, MembershipPlanFactory

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

# iCal with an all-day event (DATE value, not DATETIME) and a naive datetime event
ALLDAY_ICAL = textwrap.dedent("""\
    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Test//Test//EN
    BEGIN:VEVENT
    UID:allday-001@test.com
    SUMMARY:All Day Workshop
    DTSTART;VALUE=DATE:20260510
    DTEND;VALUE=DATE:20260511
    END:VEVENT
    END:VCALENDAR
""").encode()

# iCal with a naive (floating) datetime — no Z suffix, no TZID
NAIVE_DATETIME_ICAL = textwrap.dedent("""\
    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Test//Test//EN
    BEGIN:VEVENT
    UID:naive-001@test.com
    SUMMARY:Floating Event
    DTSTART:20260515T100000
    DTEND:20260515T120000
    END:VEVENT
    END:VCALENDAR
""").encode()

# iCal with an event missing UID and one missing DTSTART — both should be skipped
SKIP_CASES_ICAL = textwrap.dedent("""\
    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Test//Test//EN
    BEGIN:VEVENT
    SUMMARY:No UID Event
    DTSTART:20260520T100000Z
    DTEND:20260520T120000Z
    END:VEVENT
    BEGIN:VEVENT
    UID:no-dtstart-001@test.com
    SUMMARY:No DTSTART Event
    END:VEVENT
    BEGIN:VEVENT
    UID:valid-001@test.com
    SUMMARY:Valid Event
    DTSTART:20260521T100000Z
    DTEND:20260521T120000Z
    END:VEVENT
    END:VCALENDAR
""").encode()


def _fake_urlopen(url, **kwargs):
    mock_response = MagicMock()
    mock_response.read.return_value = SAMPLE_ICAL
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def _make_urlopen(ical_bytes: bytes):
    def _fake(url, **kwargs):
        mock_response = MagicMock()
        mock_response.read.return_value = ical_bytes
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    return _fake


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

        def it_sets_source_to_guild():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                sync_guild_calendar(guild)
            assert CalendarEvent.objects.filter(guild=guild, source="guild").count() == 2

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

        def it_handles_all_day_events():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_make_urlopen(ALLDAY_ICAL)):
                count = sync_guild_calendar(guild)
            assert count == 1
            event = CalendarEvent.objects.get(guild=guild)
            assert event.all_day is True
            assert event.title == "All Day Workshop"

        def it_handles_naive_datetime_events():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_make_urlopen(NAIVE_DATETIME_ICAL)):
                count = sync_guild_calendar(guild)
            assert count == 1
            event = CalendarEvent.objects.get(guild=guild)
            assert event.title == "Floating Event"
            assert event.start_dt.tzinfo is not None

        def it_skips_events_with_empty_uid_or_missing_dtstart():
            from hub.calendar_service import sync_guild_calendar

            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_make_urlopen(SKIP_CASES_ICAL)):
                count = sync_guild_calendar(guild)
            # Only the one event with UID and DTSTART should be created
            assert count == 1
            assert CalendarEvent.objects.filter(guild=guild).count() == 1
            assert CalendarEvent.objects.get(guild=guild).title == "Valid Event"

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

        def it_sets_source_to_general():
            from core.models import SiteConfiguration
            from hub.calendar_service import sync_general_calendar

            config = SiteConfiguration.load()
            config.general_calendar_url = "https://calendar.google.com/calendar/ical/general.ics"
            config.save()
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                sync_general_calendar()
            assert CalendarEvent.objects.filter(source="general").count() == 2

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

        def it_swallows_exceptions_from_stale_guild_sync():
            from datetime import timedelta

            from hub.calendar_service import refresh_stale_sources

            stale_time = timezone.now() - timedelta(seconds=1000)
            GuildFactory(
                calendar_url="https://example.com/broken.ics",
                calendar_last_fetched_at=stale_time,
            )
            with patch("hub.calendar_service.sync_guild_calendar", side_effect=RuntimeError("network error")):
                # Should not raise — exceptions are swallowed
                refresh_stale_sources(max_age_seconds=900)

        def it_refreshes_stale_general_calendar():
            from datetime import timedelta

            from core.models import SiteConfiguration
            from hub.calendar_service import refresh_stale_sources

            config = SiteConfiguration.load()
            config.general_calendar_url = "https://example.com/general.ics"
            config.general_calendar_last_fetched_at = timezone.now() - timedelta(seconds=1000)
            config.save()
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                refresh_stale_sources(max_age_seconds=900)
            config.refresh_from_db()
            assert config.general_calendar_last_fetched_at >= timezone.now() - timedelta(seconds=5)

        def it_refreshes_general_calendar_never_fetched():
            from core.models import SiteConfiguration
            from hub.calendar_service import refresh_stale_sources

            config = SiteConfiguration.load()
            config.general_calendar_url = "https://example.com/general2.ics"
            config.general_calendar_last_fetched_at = None
            config.save()
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                refresh_stale_sources(max_age_seconds=900)
            config.refresh_from_db()
            assert config.general_calendar_last_fetched_at is not None

        def it_swallows_exceptions_from_stale_general_sync():
            from core.models import SiteConfiguration
            from hub.calendar_service import refresh_stale_sources

            config = SiteConfiguration.load()
            config.general_calendar_url = "https://example.com/broken-general.ics"
            config.general_calendar_last_fetched_at = None
            config.save()
            with patch("hub.calendar_service.sync_general_calendar", side_effect=RuntimeError("network error")):
                # Should not raise — exceptions are swallowed
                refresh_stale_sources(max_age_seconds=900)

        def it_skips_general_calendar_fetched_recently():
            from core.models import SiteConfiguration
            from hub.calendar_service import refresh_stale_sources

            config = SiteConfiguration.load()
            config.general_calendar_url = "https://example.com/recent-general.ics"
            config.general_calendar_last_fetched_at = timezone.now()
            config.save()
            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen) as mock_open:
                refresh_stale_sources(max_age_seconds=900)
            mock_open.assert_not_called()


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


def _logged_in_user(client: Client, *, username: str = "caluser") -> User:
    MembershipPlanFactory()
    user = User.objects.create_user(username=username, password="pass")
    client.login(username=username, password="pass")
    return user


def describe_community_calendar_view():
    def it_requires_login(client: Client):
        response = client.get("/calendar/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def it_renders_for_logged_in_user(client: Client):
        _logged_in_user(client)
        response = client.get("/calendar/")
        assert response.status_code == 200
        assert b"Community Calendar" in response.content

    def it_shows_only_guilds_with_calendars_in_context(client: Client):
        _logged_in_user(client, username="caluser2")
        GuildFactory(name="Ceramics Guild", calendar_url="https://calendar.google.com/calendar/ical/a.ics")
        GuildFactory(name="Woodshop")  # no calendar_url
        response = client.get("/calendar/")
        assert response.status_code == 200
        guilds = response.context["guilds_with_calendars"]
        names = [g.name for g in guilds]
        assert "Ceramics Guild" in names
        assert "Woodshop" not in names

    def it_includes_classes_color_in_context(client: Client):
        from core.models import SiteConfiguration

        _logged_in_user(client, username="caluser_classes")
        config = SiteConfiguration.load()
        config.sync_classes_enabled = True
        config.classes_calendar_color = "#AA33BB"
        config.save()
        response = client.get("/calendar/")
        assert response.status_code == 200
        assert response.context["classes_enabled"] is True
        assert response.context["classes_color"] == "#AA33BB"


def describe_calendar_events_partial_view():
    def it_returns_200_and_calls_refresh(client: Client):
        _logged_in_user(client, username="caluser3")
        with patch("hub.views.refresh_stale_sources") as mock_refresh:
            response = client.get("/calendar/events/")
        assert response.status_code == 200
        mock_refresh.assert_called_once()

    def it_renders_upcoming_events(client: Client):
        _logged_in_user(client, username="caluser4")
        guild = GuildFactory(name="Art Guild", calendar_url="https://example.com/cal.ics")
        now = timezone.now()
        # Create event in current week (tomorrow is always within the current week if today ≤ Thursday)
        CalendarEvent.objects.create(
            guild=guild,
            uid="test-001",
            title="Life Drawing Session",
            start_dt=now + timedelta(days=1),
            end_dt=now + timedelta(days=1, hours=2),
            fetched_at=now,
        )
        with patch("hub.views.refresh_stale_sources"):
            response = client.get("/calendar/events/")
        assert b"Life Drawing Session" in response.content

    def it_paginates_month_events_to_max_10_per_page(client: Client):
        _logged_in_user(client, username="caluser_page")
        guild = GuildFactory(name="Pagination Guild", calendar_url="https://example.com/pag.ics")
        now = timezone.now()
        # Place 15 events in the first 15 days of next month to avoid end-of-month spillover
        next_month_first = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=10, minute=0, second=0, microsecond=0)
        for i in range(15):
            event_dt = next_month_first + timedelta(days=i)
            CalendarEvent.objects.create(
                guild=guild,
                uid=f"page-event-{i}",
                title=f"Event {i:02d}",
                start_dt=event_dt,
                end_dt=event_dt + timedelta(hours=1),
                fetched_at=now,
            )
        with patch("hub.views.refresh_stale_sources"):
            response = client.get("/calendar/events/?month_offset=1")
        assert response.context["event_total_pages"] == 2
        assert len(response.context["month_events"]) == 10

    def it_returns_month_page_2_when_requested(client: Client):
        _logged_in_user(client, username="caluser_page2")
        guild = GuildFactory(name="Page2 Guild", calendar_url="https://example.com/pag2.ics")
        now = timezone.now()
        next_month_first = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=10, minute=0, second=0, microsecond=0)
        for i in range(15):
            event_dt = next_month_first + timedelta(days=i)
            CalendarEvent.objects.create(
                guild=guild,
                uid=f"p2-event-{i}",
                title=f"Page2 Event {i:02d}",
                start_dt=event_dt,
                end_dt=event_dt + timedelta(hours=1),
                fetched_at=now,
            )
        with patch("hub.views.refresh_stale_sources"):
            response = client.get("/calendar/events/?month_offset=1&page=2")
        assert response.context["event_page"] == 2
        assert len(response.context["month_events"]) == 5


def describe_calendar_export_ics_view():
    def it_returns_ics_content_type(client: Client):
        _logged_in_user(client, username="caluser5")
        response = client.get("/calendar/export.ics")
        assert response.status_code == 200
        assert "text/calendar" in response["Content-Type"]

    def it_includes_events_in_ics_output(client: Client):
        from datetime import timedelta as td

        _logged_in_user(client, username="caluser6")
        guild = GuildFactory(name="Ceramics", calendar_url="https://example.com/a.ics")
        now = timezone.now()
        CalendarEvent.objects.create(
            guild=guild,
            uid="export-001",
            title="Glaze Workshop",
            start_dt=now + td(days=3),
            end_dt=now + td(days=3, hours=2),
            fetched_at=now,
        )
        response = client.get("/calendar/export.ics")
        assert b"Glaze Workshop" in response.content
        assert b"BEGIN:VEVENT" in response.content

    def it_escapes_newlines_in_description(client: Client):
        from datetime import timedelta as td

        _logged_in_user(client, username="caluser7")
        guild = GuildFactory(name="Printmaking", calendar_url="https://example.com/b.ics")
        now = timezone.now()
        CalendarEvent.objects.create(
            guild=guild,
            uid="escape-001",
            title="Printmaking Open Night",
            description="Line one\nLine two\nLine three",
            start_dt=now + td(days=2),
            end_dt=now + td(days=2, hours=2),
            fetched_at=now,
        )
        response = client.get("/calendar/export.ics")
        content = response.content.decode()
        # Escaped newlines must appear; bare newlines in the middle of a field must not
        assert "\\n" in content
        # The description field should contain the escaped version
        assert "DESCRIPTION:Line one\\nLine two\\nLine three" in content

    def it_exports_all_day_events_with_date_format(client: Client):
        from datetime import timedelta as td

        _logged_in_user(client, username="caluser8")
        guild = GuildFactory(name="Fiber Arts", calendar_url="https://example.com/c.ics")
        now = timezone.now()
        CalendarEvent.objects.create(
            guild=guild,
            uid="allday-export-001",
            title="All Day Fiber Fest",
            all_day=True,
            start_dt=now + td(days=5),
            end_dt=now + td(days=6),
            fetched_at=now,
        )
        response = client.get("/calendar/export.ics")
        content = response.content.decode()
        assert "DTSTART;VALUE=DATE:" in content
        assert "DTEND;VALUE=DATE:" in content
        # Should NOT export as datetime format for all-day events
        assert "DTSTART:20" not in content or "DTSTART;VALUE=DATE:" in content
