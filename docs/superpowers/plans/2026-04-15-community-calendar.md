# Community Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Community Calendar sidebar page that aggregates Google Calendar feeds from guilds + the makerspace, with week/month toggle, guild color filtering, HTMX auto-refresh, and iCal export.

**Architecture:** Guild officers add a Google Calendar iCal URL + hex color to their guild page. A `CalendarEvent` model in `membership` caches parsed iCal events (refreshed server-side every 15 min). The hub page serves a full calendar view (Alpine.js week/month toggle, filter toggles) that auto-refreshes via HTMX polling. A general makerspace calendar URL lives on `SiteConfiguration`.

**Tech Stack:** Django models/views, Alpine.js (week/month toggle, filter state, live clock), HTMX (auto-refresh every 5 min), `icalendar` Python library (iCal parsing), `urllib.request` (HTTP fetch), custom CSS calendar grid, iCal export endpoint.

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `hub/calendar_service.py` | Fetch iCal URLs, parse events, upsert `CalendarEvent` records, check staleness |
| `templates/hub/community_calendar.html` | Full calendar page (extends `hub/base.html`) |
| `templates/hub/partials/calendar_content.html` | HTMX-swappable partial: calendar grid + event list |
| `static/css/calendar.css` | Calendar grid, event chips, color coding, light/dark themes |
| `tests/hub/community_calendar_spec.py` | View + service tests |
| `tests/membership/calendar_event_spec.py` | CalendarEvent model tests |

### Modified files
| File | What changes |
|------|-------------|
| `membership/models.py` | Add `calendar_url`, `calendar_color`, `calendar_last_fetched_at` to `Guild`; add `CalendarEvent` model |
| `core/models.py` | Add `general_calendar_url`, `general_calendar_color`, `general_calendar_last_fetched_at` to `SiteConfiguration` |
| `hub/views.py` | Add `community_calendar`, `calendar_events_partial`, `calendar_export_ics` views |
| `hub/forms.py` | Add `calendar_url`, `calendar_color` to `GuildEditForm` |
| `hub/urls.py` | Register `/calendar/`, `/calendar/events/`, `/calendar/export.ics` |
| `templates/hub/base.html` | Add "Community Calendar" sidebar link above "Guild Voting" |
| `templates/hub/guild_detail.html` | Add calendar URL + color fields to guild edit section |
| `requirements.txt` | Add `icalendar>=6.0` |
| `plfog/version.py` | Version bump to 1.6.0 + changelog entry |

---

## Task 1: Create branch and install dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Confirm you are on `feature/community-calendar`**

```bash
git branch --show-current
# Expected output: feature/community-calendar
```

- [ ] **Step 2: Add `icalendar` to `requirements.txt`**

Open `requirements.txt`. After the last line, add:
```
icalendar>=6.0
```

- [ ] **Step 3: Install the dependency**

```bash
pip install icalendar>=6.0
# or: uv pip install icalendar
```

- [ ] **Step 4: Verify it imports**

```bash
python -c "import icalendar; print(icalendar.__version__)"
# Expected: 6.x.x
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: add icalendar dependency for Community Calendar"
```

---

## Task 2: Add calendar fields to `Guild` model

**Files:**
- Modify: `membership/models.py`
- Create: `membership/migrations/00XX_guild_calendar_fields.py` (auto-generated)
- Create: `tests/membership/calendar_event_spec.py` (start this file here, add more in Task 4)

- [ ] **Step 1: Write the failing test**

Create `tests/membership/calendar_event_spec.py`:

```python
"""BDD specs for CalendarEvent model and Guild calendar fields."""

from __future__ import annotations

import pytest
from django.utils import timezone

from membership.models import Guild
from tests.membership.factories import GuildFactory


@pytest.mark.django_db
def describe_Guild_calendar_fields():
    def it_has_default_calendar_color(db):
        guild = GuildFactory()
        assert guild.calendar_color == "#4B9FEE"

    def it_stores_calendar_url(db):
        guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test%40group.calendar.google.com/public/basic.ics")
        assert "calendar.google.com" in guild.calendar_url

    def it_calendar_last_fetched_at_defaults_to_null(db):
        guild = GuildFactory()
        assert guild.calendar_last_fetched_at is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/membership/calendar_event_spec.py -v
# Expected: AttributeError: type object 'Guild' has no attribute 'calendar_color'
```

- [ ] **Step 3: Add fields to `Guild` in `membership/models.py`**

Find the `Guild` class (currently ends with `leases = GenericRelation(...)` and `created_at`). Add these three fields after `created_at`:

```python
    calendar_url = models.URLField(
        blank=True,
        default="",
        help_text="Public iCal URL for this guild's Google Calendar (File → Share → Get shareable iCal link).",
    )
    calendar_color = models.CharField(
        max_length=7,
        default="#4B9FEE",
        blank=True,
        help_text="Hex color code for this guild's events on the Community Calendar (e.g. #4B9FEE).",
    )
    calendar_last_fetched_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this guild's iCal feed was last synced. Set by the calendar service.",
    )
```

- [ ] **Step 4: Create and apply the migration**

```bash
python manage.py makemigrations membership --name guild_calendar_fields
python manage.py migrate
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/membership/calendar_event_spec.py::describe_Guild_calendar_fields -v
# Expected: 3 passed
```

- [ ] **Step 6: Commit**

```bash
git add membership/models.py membership/migrations/
git add tests/membership/calendar_event_spec.py
git commit -m "feat(membership): add calendar_url, calendar_color, calendar_last_fetched_at to Guild"
```

---

## Task 3: Add general calendar fields to `SiteConfiguration`

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/00XX_siteconfiguration_calendar.py` (auto-generated)

- [ ] **Step 1: Write the failing test**

Add to `tests/membership/calendar_event_spec.py` (append after existing describes):

```python
@pytest.mark.django_db
def describe_SiteConfiguration_calendar_fields():
    def it_has_default_general_calendar_color(db):
        from core.models import SiteConfiguration
        config = SiteConfiguration.load()
        assert config.general_calendar_color == "#EEB44B"

    def it_general_calendar_url_defaults_to_blank(db):
        from core.models import SiteConfiguration
        config = SiteConfiguration.load()
        assert config.general_calendar_url == ""
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/membership/calendar_event_spec.py::describe_SiteConfiguration_calendar_fields -v
# Expected: AttributeError: 'SiteConfiguration' object has no attribute 'general_calendar_color'
```

- [ ] **Step 3: Add fields to `SiteConfiguration` in `core/models.py`**

In `SiteConfiguration`, after the `registration_mode` field, add:

```python
    general_calendar_url = models.URLField(
        blank=True,
        default="",
        verbose_name="General Calendar iCal URL",
        help_text="Public iCal URL for the general makerspace calendar. Paste the 'Secret address in iCal format' from Google Calendar settings.",
    )
    general_calendar_color = models.CharField(
        max_length=7,
        default="#EEB44B",
        verbose_name="General Calendar Color",
        help_text="Hex color for general makerspace events on the Community Calendar (e.g. #EEB44B).",
    )
    general_calendar_last_fetched_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the general calendar was last synced. Set by the calendar service.",
    )
```

- [ ] **Step 4: Create and apply the migration**

```bash
python manage.py makemigrations core --name siteconfiguration_calendar_fields
python manage.py migrate
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/membership/calendar_event_spec.py::describe_SiteConfiguration_calendar_fields -v
# Expected: 2 passed
```

- [ ] **Step 6: Commit**

```bash
git add core/models.py core/migrations/
git add tests/membership/calendar_event_spec.py
git commit -m "feat(core): add general calendar URL and color to SiteConfiguration"
```

---

## Task 4: Add `CalendarEvent` model

**Files:**
- Modify: `membership/models.py`
- Create: migration (auto-generated)
- Modify: `tests/membership/calendar_event_spec.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/membership/calendar_event_spec.py`:

```python
@pytest.mark.django_db
def describe_CalendarEvent():
    def it_can_be_created_for_a_guild(db):
        from membership.models import CalendarEvent
        from django.utils import timezone
        guild = GuildFactory()
        now = timezone.now()
        event = CalendarEvent.objects.create(
            guild=guild,
            uid="abc123@google.com",
            title="Open Studio",
            start_dt=now,
            end_dt=now,
            fetched_at=now,
        )
        assert event.guild == guild
        assert str(event) == "Open Studio"

    def it_can_be_created_without_a_guild_for_general_events(db):
        from membership.models import CalendarEvent
        from django.utils import timezone
        now = timezone.now()
        event = CalendarEvent.objects.create(
            guild=None,
            uid="general-123@google.com",
            title="Potluck Night",
            start_dt=now,
            end_dt=now,
            fetched_at=now,
        )
        assert event.guild is None

    def it_orders_by_start_dt(db):
        from membership.models import CalendarEvent
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        guild = GuildFactory()
        CalendarEvent.objects.create(guild=guild, uid="later", title="B", start_dt=now + timedelta(hours=2), end_dt=now + timedelta(hours=3), fetched_at=now)
        CalendarEvent.objects.create(guild=guild, uid="earlier", title="A", start_dt=now, end_dt=now + timedelta(hours=1), fetched_at=now)
        titles = list(CalendarEvent.objects.values_list("title", flat=True))
        assert titles == ["A", "B"]

    def describe_upcoming():
        def it_returns_events_starting_from_now_onwards(db):
            from membership.models import CalendarEvent
            from datetime import timedelta
            from django.utils import timezone
            now = timezone.now()
            guild = GuildFactory()
            CalendarEvent.objects.create(guild=guild, uid="past", title="Past", start_dt=now - timedelta(days=1), end_dt=now - timedelta(hours=23), fetched_at=now)
            CalendarEvent.objects.create(guild=guild, uid="future", title="Future", start_dt=now + timedelta(days=1), end_dt=now + timedelta(days=1, hours=1), fetched_at=now)
            results = list(CalendarEvent.objects.upcoming())
            assert len(results) == 1
            assert results[0].title == "Future"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/membership/calendar_event_spec.py::describe_CalendarEvent -v
# Expected: ImportError or AttributeError — CalendarEvent does not exist
```

- [ ] **Step 3: Add `CalendarEvent` model to `membership/models.py`**

Add a new manager class and the model at the bottom of `membership/models.py` (before the final line), after the `Lease` class:

```python
# ---------------------------------------------------------------------------
# CalendarEvent
# ---------------------------------------------------------------------------


class CalendarEventQuerySet(models.QuerySet):
    def upcoming(self) -> CalendarEventQuerySet:
        """Events that start from now onwards (includes in-progress events)."""
        return self.filter(end_dt__gte=timezone.now())


class CalendarEvent(models.Model):
    """Cached calendar event fetched from a guild's or the general makerspace's iCal feed.

    The calendar service updates these records periodically. Treat as a
    read-through cache — do not edit records directly; re-sync from the source.
    """

    guild = models.ForeignKey(
        "Guild",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="calendar_events",
        help_text="Guild this event belongs to. Null for general makerspace events.",
    )
    uid = models.CharField(max_length=500, db_index=True, help_text="iCal UID, unique within a source.")
    title = models.CharField(max_length=500, help_text="Event title from iCal SUMMARY field.")
    description = models.TextField(blank=True, help_text="Event description from iCal DESCRIPTION field.")
    location = models.CharField(max_length=500, blank=True, help_text="Event location from iCal LOCATION field.")
    url = models.URLField(blank=True, help_text="Event URL from iCal URL field.")
    start_dt = models.DateTimeField(help_text="Event start time, UTC-normalized.")
    end_dt = models.DateTimeField(help_text="Event end time, UTC-normalized.")
    all_day = models.BooleanField(default=False, help_text="True for all-day events (DATE not DATETIME in iCal).")
    fetched_at = models.DateTimeField(help_text="When this record was last synced from the iCal source.")

    objects = CalendarEventQuerySet.as_manager()

    class Meta:
        ordering = ["start_dt"]
        indexes = [
            models.Index(fields=["start_dt", "end_dt"], name="idx_calendarevent_start_end"),
            models.Index(fields=["guild", "uid"], name="idx_calendarevent_guild_uid"),
        ]
        verbose_name = "Calendar Event"
        verbose_name_plural = "Calendar Events"

    def __str__(self) -> str:
        return self.title
```

- [ ] **Step 4: Generate and apply migration**

```bash
python manage.py makemigrations membership --name calendarevent
python manage.py migrate
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/membership/calendar_event_spec.py -v
# Expected: all tests pass
```

- [ ] **Step 6: Commit**

```bash
git add membership/models.py membership/migrations/
git add tests/membership/calendar_event_spec.py
git commit -m "feat(membership): add CalendarEvent model with upcoming() queryset"
```

---

## Task 5: Calendar service — fetch, parse, and sync

**Files:**
- Create: `hub/calendar_service.py`
- Create: `tests/hub/community_calendar_spec.py` (start this file here, add view tests later)

The service fetches iCal URLs using `urllib.request`, parses them with `icalendar`, and upserts `CalendarEvent` records. It also checks if sources are stale.

- [ ] **Step 1: Write the failing tests**

Create `tests/hub/community_calendar_spec.py`:

```python
"""BDD specs for Community Calendar views and calendar service."""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from membership.models import CalendarEvent, Guild
from tests.membership.factories import GuildFactory, MembershipPlanFactory


# ---------------------------------------------------------------------------
# Minimal valid iCal fixture (two events)
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


def _fake_urlopen(url: str):
    """Mock urllib.request.urlopen — returns bytes for any URL."""
    mock_response = MagicMock()
    mock_response.read.return_value = SAMPLE_ICAL
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


@pytest.mark.django_db
def describe_calendar_service():
    def describe_sync_guild_calendar():
        def it_creates_calendar_events_for_a_guild(db):
            from hub.calendar_service import sync_guild_calendar
            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")

            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                count = sync_guild_calendar(guild)

            assert count == 2
            events = CalendarEvent.objects.filter(guild=guild)
            assert events.count() == 2
            titles = set(events.values_list("title", flat=True))
            assert titles == {"Open Studio Hours", "Woodshop Safety Class"}

        def it_updates_existing_events_on_resync(db):
            from hub.calendar_service import sync_guild_calendar
            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")

            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                sync_guild_calendar(guild)
                # Second sync — should update, not duplicate
                count = sync_guild_calendar(guild)

            assert count == 2
            assert CalendarEvent.objects.filter(guild=guild).count() == 2

        def it_sets_calendar_last_fetched_at_on_guild(db):
            from hub.calendar_service import sync_guild_calendar
            guild = GuildFactory(calendar_url="https://calendar.google.com/calendar/ical/test.ics")
            assert guild.calendar_last_fetched_at is None

            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                sync_guild_calendar(guild)

            guild.refresh_from_db()
            assert guild.calendar_last_fetched_at is not None

        def it_returns_zero_when_guild_has_no_calendar_url(db):
            from hub.calendar_service import sync_guild_calendar
            guild = GuildFactory(calendar_url="")
            count = sync_guild_calendar(guild)
            assert count == 0

    def describe_sync_general_calendar():
        def it_creates_general_events_with_null_guild(db):
            from core.models import SiteConfiguration
            from hub.calendar_service import sync_general_calendar
            config = SiteConfiguration.load()
            config.general_calendar_url = "https://calendar.google.com/calendar/ical/general.ics"
            config.save()

            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen):
                count = sync_general_calendar()

            assert count == 2
            assert CalendarEvent.objects.filter(guild__isnull=True).count() == 2

        def it_returns_zero_when_no_general_calendar_configured(db):
            from hub.calendar_service import sync_general_calendar
            count = sync_general_calendar()
            assert count == 0

    def describe_refresh_stale_sources():
        def it_skips_sources_fetched_recently(db):
            from hub.calendar_service import refresh_stale_sources
            recent = timezone.now()
            guild = GuildFactory(
                calendar_url="https://example.com/cal.ics",
                calendar_last_fetched_at=recent,
            )

            with patch("hub.calendar_service.urllib.request.urlopen", side_effect=_fake_urlopen) as mock_open:
                refresh_stale_sources(max_age_seconds=900)

            mock_open.assert_not_called()

        def it_refreshes_stale_guild_sources(db):
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
            assert guild.calendar_last_fetched_at > stale_time
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/hub/community_calendar_spec.py::describe_calendar_service -v
# Expected: ModuleNotFoundError: No module named 'hub.calendar_service'
```

- [ ] **Step 3: Create `hub/calendar_service.py`**

```python
"""Calendar service — fetches iCal feeds, parses events, and upserts CalendarEvent records.

Usage:
    from hub.calendar_service import refresh_stale_sources
    refresh_stale_sources()  # called by the calendar_events_partial view
"""

from __future__ import annotations

import urllib.request
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.utils import timezone

from core.models import SiteConfiguration
from membership.models import CalendarEvent, Guild


# How long (seconds) before a cached source is considered stale and re-fetched.
DEFAULT_MAX_AGE_SECONDS = 900  # 15 minutes


def _parse_ical_events(raw_bytes: bytes) -> list[dict[str, Any]]:
    """Parse raw iCal bytes into a list of event dicts.

    Returns:
        List of dicts with keys: uid, title, description, location, url,
        start_dt, end_dt, all_day.
    """
    import icalendar

    cal = icalendar.Calendar.from_ical(raw_bytes)
    events: list[dict[str, Any]] = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID", ""))
        if not uid:
            continue

        summary = component.get("SUMMARY", "")
        title = str(summary) if summary else "(No title)"

        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if dtstart is None:
            continue

        start_val = dtstart.dt
        end_val = dtend.dt if dtend else start_val

        # Determine if all-day (date only, no time component)
        all_day = isinstance(start_val, datetime.__class__) and not isinstance(start_val, datetime)
        # In icalendar, all-day events use datetime.date, timed events use datetime.datetime.
        from datetime import date as date_type
        all_day = isinstance(start_val, date_type) and not isinstance(start_val, datetime)

        def _to_datetime(val: Any) -> datetime:
            if isinstance(val, datetime):
                if val.tzinfo is None:
                    return val.replace(tzinfo=dt_timezone.utc)
                return val.astimezone(dt_timezone.utc)
            # date (all-day) — treat as midnight UTC
            return datetime(val.year, val.month, val.day, tzinfo=dt_timezone.utc)

        events.append(
            {
                "uid": uid,
                "title": title,
                "description": str(component.get("DESCRIPTION", "")),
                "location": str(component.get("LOCATION", "")),
                "url": str(component.get("URL", "")),
                "start_dt": _to_datetime(start_val),
                "end_dt": _to_datetime(end_val),
                "all_day": all_day,
            }
        )

    return events


def _fetch_and_parse(url: str) -> list[dict[str, Any]]:
    """Fetch an iCal URL and return parsed event dicts.

    Raises:
        urllib.error.URLError: If the URL cannot be fetched.
        ValueError: If the response cannot be parsed as iCal.
    """
    with urllib.request.urlopen(url, timeout=10) as response:
        raw = response.read()
    return _parse_ical_events(raw)


def _upsert_events(events: list[dict[str, Any]], guild: Guild | None) -> int:
    """Insert or update CalendarEvent records for the given source.

    Args:
        events: Parsed event dicts from _fetch_and_parse.
        guild: Guild instance for guild events; None for general events.

    Returns:
        Number of events processed.
    """
    now = timezone.now()
    for evt in events:
        CalendarEvent.objects.update_or_create(
            guild=guild,
            uid=evt["uid"],
            defaults={
                "title": evt["title"],
                "description": evt["description"],
                "location": evt["location"],
                "url": evt["url"],
                "start_dt": evt["start_dt"],
                "end_dt": evt["end_dt"],
                "all_day": evt["all_day"],
                "fetched_at": now,
            },
        )
    return len(events)


def sync_guild_calendar(guild: Guild) -> int:
    """Fetch and sync a guild's iCal calendar.

    Args:
        guild: Guild instance with a calendar_url set.

    Returns:
        Number of events synced. 0 if guild has no calendar_url.
    """
    if not guild.calendar_url:
        return 0

    events = _fetch_and_parse(guild.calendar_url)
    count = _upsert_events(events, guild=guild)
    guild.calendar_last_fetched_at = timezone.now()
    guild.save(update_fields=["calendar_last_fetched_at"])
    return count


def sync_general_calendar() -> int:
    """Fetch and sync the general makerspace calendar from SiteConfiguration.

    Returns:
        Number of events synced. 0 if no general_calendar_url is configured.
    """
    config = SiteConfiguration.load()
    if not config.general_calendar_url:
        return 0

    events = _fetch_and_parse(config.general_calendar_url)
    count = _upsert_events(events, guild=None)
    config.general_calendar_last_fetched_at = timezone.now()
    config.save(update_fields=["general_calendar_last_fetched_at"])
    return count


def refresh_stale_sources(max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> None:
    """Refresh any calendar sources that have not been synced recently.

    Called by the `calendar_events_partial` view on each HTMX poll.
    Skips sources fetched within the last ``max_age_seconds``.

    Args:
        max_age_seconds: Sources older than this are re-fetched. Default: 900 (15 min).
    """
    cutoff = timezone.now() - timedelta(seconds=max_age_seconds)

    # Guild sources
    stale_guilds = Guild.objects.filter(
        is_active=True,
        calendar_url__gt="",
    ).exclude(calendar_last_fetched_at__gte=cutoff)

    for guild in stale_guilds:
        try:
            sync_guild_calendar(guild)
        except Exception:
            pass  # Don't crash the page if one calendar is unreachable

    # General source
    config = SiteConfiguration.load()
    if config.general_calendar_url:
        general_stale = (
            config.general_calendar_last_fetched_at is None
            or config.general_calendar_last_fetched_at < cutoff
        )
        if general_stale:
            try:
                sync_general_calendar()
            except Exception:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/hub/community_calendar_spec.py::describe_calendar_service -v
# Expected: all tests pass
```

- [ ] **Step 5: Commit**

```bash
git add hub/calendar_service.py
git add tests/hub/community_calendar_spec.py
git commit -m "feat(hub): add calendar service for iCal fetch, parse, and sync"
```

---

## Task 6: Extend `GuildEditForm` with calendar fields

**Files:**
- Modify: `hub/forms.py`
- Modify: `tests/hub/community_calendar_spec.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/hub/community_calendar_spec.py`:

```python
@pytest.mark.django_db
def describe_GuildEditForm():
    def it_saves_calendar_url_and_color(db):
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

    def it_accepts_empty_calendar_url(db):
        from hub.forms import GuildEditForm
        guild = GuildFactory()
        form = GuildEditForm(
            data={"name": guild.name, "about": "", "calendar_url": "", "calendar_color": "#4B9FEE"},
            instance=guild,
        )
        assert form.is_valid(), form.errors

    def it_rejects_invalid_calendar_url(db):
        from hub.forms import GuildEditForm
        guild = GuildFactory()
        form = GuildEditForm(
            data={"name": guild.name, "about": "", "calendar_url": "not-a-url", "calendar_color": "#4B9FEE"},
            instance=guild,
        )
        assert not form.is_valid()
        assert "calendar_url" in form.errors
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/hub/community_calendar_spec.py::describe_GuildEditForm -v
# Expected: AssertionError — form missing calendar_url
```

- [ ] **Step 3: Update `GuildEditForm` in `hub/forms.py`**

Replace the existing `GuildEditForm`:

```python
class GuildEditForm(forms.ModelForm):
    """Edit form for a guild's public-facing fields, including calendar integration."""

    class Meta:
        model = Guild
        fields = ["name", "about", "calendar_url", "calendar_color"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Guild name"}),
            "about": forms.Textarea(
                attrs={"rows": 5, "placeholder": "Tell members what this guild is about..."},
            ),
            "calendar_url": forms.URLInput(
                attrs={"placeholder": "https://calendar.google.com/calendar/ical/..."}
            ),
            "calendar_color": forms.TextInput(
                attrs={"type": "color", "style": "width: 56px; height: 36px; padding: 2px;"},
            ),
        }
        labels = {
            "about": "About",
            "calendar_url": "Google Calendar iCal URL",
            "calendar_color": "Calendar Color",
        }
        help_texts = {
            "calendar_url": "In Google Calendar → Settings → your calendar → 'Secret address in iCal format'. Leave blank if you don't use Google Calendar.",
            "calendar_color": "Color used for your guild's events on the Community Calendar.",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/hub/community_calendar_spec.py::describe_GuildEditForm -v
# Expected: 3 passed
```

- [ ] **Step 5: Commit**

```bash
git add hub/forms.py
git add tests/hub/community_calendar_spec.py
git commit -m "feat(hub): add calendar_url and calendar_color to GuildEditForm"
```

---

## Task 7: Add Community Calendar views

**Files:**
- Modify: `hub/views.py`
- Modify: `hub/urls.py`
- Modify: `tests/hub/community_calendar_spec.py`

Three new views:
1. `community_calendar` — full page with server-rendered events + HTMX scaffold
2. `calendar_events_partial` — HTMX partial: triggers stale refresh, returns updated HTML
3. `calendar_export_ics` — generates a downloadable combined `.ics` file

- [ ] **Step 1: Write the failing tests**

Append to `tests/hub/community_calendar_spec.py`:

```python
# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _logged_in_user(client: Client, *, username: str = "caluser") -> User:
    MembershipPlanFactory()
    user = User.objects.create_user(username=username, password="pass")
    client.login(username=username, password="pass")
    return user


@pytest.mark.django_db
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

    def it_shows_guild_filter_toggles_for_guilds_with_calendars(client: Client):
        _logged_in_user(client)
        GuildFactory(name="Ceramics Guild", calendar_url="https://calendar.google.com/calendar/ical/a.ics")
        GuildFactory(name="Woodshop")  # no calendar_url — should not appear
        response = client.get("/calendar/")
        assert b"Ceramics Guild" in response.content
        assert b"Woodshop" not in response.content


@pytest.mark.django_db
def describe_calendar_events_partial_view():
    def it_returns_200_and_calls_refresh(client: Client):
        _logged_in_user(client)
        with patch("hub.views.refresh_stale_sources") as mock_refresh:
            response = client.get("/calendar/events/")
        assert response.status_code == 200
        mock_refresh.assert_called_once()

    def it_renders_events_from_database(client: Client):
        from django.utils import timezone as tz
        from datetime import timedelta
        _logged_in_user(client)
        guild = GuildFactory(name="Art Guild", calendar_url="https://example.com/cal.ics")
        now = tz.now()
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


@pytest.mark.django_db
def describe_calendar_export_ics_view():
    def it_returns_ics_content_type(client: Client):
        _logged_in_user(client)
        response = client.get("/calendar/export.ics")
        assert response.status_code == 200
        assert "text/calendar" in response["Content-Type"]

    def it_includes_events_in_ics_output(client: Client):
        from django.utils import timezone as tz
        from datetime import timedelta
        _logged_in_user(client)
        guild = GuildFactory(name="Ceramics", calendar_url="https://example.com/a.ics")
        now = tz.now()
        CalendarEvent.objects.create(
            guild=guild,
            uid="export-001",
            title="Glaze Workshop",
            start_dt=now + timedelta(days=3),
            end_dt=now + timedelta(days=3, hours=2),
            fetched_at=now,
        )
        response = client.get("/calendar/export.ics")
        assert b"Glaze Workshop" in response.content
        assert b"BEGIN:VEVENT" in response.content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/hub/community_calendar_spec.py::describe_community_calendar_view tests/hub/community_calendar_spec.py::describe_calendar_events_partial_view tests/hub/community_calendar_spec.py::describe_calendar_export_ics_view -v
# Expected: 404 or URL resolution errors — views don't exist yet
```

- [ ] **Step 3: Add views to `hub/views.py`**

Add these imports at the top of `hub/views.py` (merge with existing imports):

```python
from datetime import timedelta
from django.utils import timezone as dj_timezone
```

Add these three views at the end of `hub/views.py`:

```python
def _get_calendar_context(request: HttpRequest) -> dict[str, Any]:
    """Build context for both the full calendar page and the HTMX partial.

    Returns events for the next 90 days, guild sources with their colors,
    and the general calendar source metadata.
    """
    from core.models import SiteConfiguration
    from membership.models import CalendarEvent, Guild

    now = dj_timezone.now()
    horizon = now + timedelta(days=90)

    events = (
        CalendarEvent.objects.filter(start_dt__gte=now, start_dt__lte=horizon)
        .select_related("guild")
        .order_by("start_dt")
    )

    guilds_with_calendars = Guild.objects.filter(is_active=True, calendar_url__gt="").order_by("name")

    config = SiteConfiguration.load()
    general_enabled = bool(config.general_calendar_url)
    general_color = config.general_calendar_color

    # Build a source lookup for color resolution in templates
    # {source_key: color} — source_key is "general" or str(guild.pk)
    source_colors: dict[str, str] = {"general": general_color}
    for g in guilds_with_calendars:
        source_colors[str(g.pk)] = g.calendar_color

    return {
        "events": list(events),
        "guilds_with_calendars": list(guilds_with_calendars),
        "general_enabled": general_enabled,
        "general_color": general_color,
        "source_colors": source_colors,
        "now": now,
    }


@login_required
def community_calendar(request: HttpRequest) -> HttpResponse:
    """Community Calendar page — shows upcoming events from all guild and general calendars."""
    ctx = _get_hub_context(request)
    cal_ctx = _get_calendar_context(request)
    return render(request, "hub/community_calendar.html", {**ctx, **cal_ctx})


@login_required
def calendar_events_partial(request: HttpRequest) -> HttpResponse:
    """HTMX partial — refreshes stale calendar sources, then returns updated event HTML.

    Called by the calendar page every 5 minutes via hx-trigger="every 300s".
    """
    from hub.calendar_service import refresh_stale_sources

    refresh_stale_sources()
    cal_ctx = _get_calendar_context(request)
    return render(request, "hub/partials/calendar_content.html", cal_ctx)


@login_required
def calendar_export_ics(request: HttpRequest) -> HttpResponse:
    """Download a combined iCal file of all upcoming events.

    Generates a valid .ics file from cached CalendarEvent records.
    Members can import this into Apple Calendar, Outlook, or Google Calendar.
    """
    from membership.models import CalendarEvent

    now = dj_timezone.now()
    horizon = now + timedelta(days=90)
    events = (
        CalendarEvent.objects.filter(start_dt__gte=now, start_dt__lte=horizon)
        .select_related("guild")
        .order_by("start_dt")
    )

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Past Lives Makerspace//Community Calendar//EN",
        "X-WR-CALNAME:Past Lives Community Calendar",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for evt in events:
        def _fmt_dt(dt: Any) -> str:
            return dt.strftime("%Y%m%dT%H%M%SZ")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{evt.uid}",
            f"SUMMARY:{evt.title}",
            f"DTSTART:{_fmt_dt(evt.start_dt)}",
            f"DTEND:{_fmt_dt(evt.end_dt)}",
        ]
        if evt.description:
            lines.append(f"DESCRIPTION:{evt.description[:250]}")
        if evt.location:
            lines.append(f"LOCATION:{evt.location}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    ical_content = "\r\n".join(lines) + "\r\n"

    response = HttpResponse(ical_content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="past-lives-calendar.ics"'
    return response
```

- [ ] **Step 4: Register URLs in `hub/urls.py`**

Add to the imports at the top of `hub/urls.py` (already imports `views`).

Add these URL patterns to `urlpatterns`:

```python
    path("calendar/", views.community_calendar, name="hub_community_calendar"),
    path("calendar/events/", views.calendar_events_partial, name="hub_community_calendar_events"),
    path("calendar/export.ics", views.calendar_export_ics, name="hub_calendar_export_ics"),
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/hub/community_calendar_spec.py -v
# Expected: all tests pass (templates may be missing — create stubs next)
```

If templates are missing, create temporary stubs:
```bash
mkdir -p templates/hub/partials
echo "{% for e in events %}{{ e.title }}{% endfor %}" > templates/hub/community_calendar.html
echo "{% for e in events %}{{ e.title }}{% endfor %}" > templates/hub/partials/calendar_content.html
```
Then run tests again. Full templates are built in Task 9.

- [ ] **Step 6: Commit**

```bash
git add hub/views.py hub/urls.py
git add tests/hub/community_calendar_spec.py
git commit -m "feat(hub): add community_calendar, calendar_events_partial, and calendar_export_ics views"
```

---

## Task 8: Add sidebar link

**Files:**
- Modify: `templates/hub/base.html`

- [ ] **Step 1: Add the Community Calendar nav link above Guild Voting in `templates/hub/base.html`**

Find this block in `templates/hub/base.html` (around line 51-58):
```html
        <nav class="hub-sidebar__nav" aria-label="Hub navigation" @click="if ($event.target.closest('a') && window.innerWidth <= 768) sidebarOpen = false">
            <a href="{% url 'hub_guild_voting' %}" class="hub-sidebar__link {% active_nav 'hub_guild_voting' %}">
```

Insert the Community Calendar link **before** the Guild Voting link:

```html
        <nav class="hub-sidebar__nav" aria-label="Hub navigation" @click="if ($event.target.closest('a') && window.innerWidth <= 768) sidebarOpen = false">
            <a href="{% url 'hub_community_calendar' %}" class="hub-sidebar__link {% active_nav 'hub_community_calendar' 'hub_community_calendar_events' %}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                Community Calendar
            </a>

            <a href="{% url 'hub_guild_voting' %}" class="hub-sidebar__link {% active_nav 'hub_guild_voting' %}">
```

- [ ] **Step 2: Verify the sidebar renders without error**

```bash
python manage.py runserver &
# Open http://localhost:8000/calendar/ in browser — confirm sidebar shows "Community Calendar" above "Guild Voting"
# Ctrl+C to stop server
```

- [ ] **Step 3: Commit**

```bash
git add templates/hub/base.html
git commit -m "feat(hub): add Community Calendar sidebar link above Guild Voting"
```

---

## Task 9: Full calendar page templates

**Files:**
- Create/replace: `templates/hub/community_calendar.html`
- Create/replace: `templates/hub/partials/calendar_content.html`

The calendar page uses:
- Alpine.js for week/month toggle, filter toggles, and live clock
- HTMX for auto-refresh every 5 min
- Custom CSS grid for the calendar (added in Task 10)

The page layout (from the screenshot):
- **Top:** "Community Calendar" heading (left) | live date/time (right) | export button
- **Filter bar:** colored toggle pills for General + each guild with a calendar
- **View toggle:** Week / Month buttons
- **Calendar grid:** 7 columns (days), rows for weeks
- **Event list:** ordered list with time, colored left-border, title, description, location

- [ ] **Step 1: Create `templates/hub/community_calendar.html`**

```django
{% extends "hub/base.html" %}
{% load static hub_tags %}

{% block title %}Community Calendar{% endblock %}

{% block extra_js %}
<link rel="stylesheet" href="{% static 'css/calendar.css' %}">
{% endblock %}

{% block content %}
<div class="hub-page-header">
    <h1 class="hub-page-title">Community Calendar</h1>
</div>

<div
    x-data="{
        calView: localStorage.getItem('calView') || 'week',
        activeFilters: JSON.parse(localStorage.getItem('calFilters') || '{{ default_filters_json }}'),
        setView(v) { this.calView = v; localStorage.setItem('calView', v); },
        toggleFilter(key) {
            if (this.activeFilters.includes(key)) {
                this.activeFilters = this.activeFilters.filter(k => k !== key);
            } else {
                this.activeFilters.push(key);
            }
            localStorage.setItem('calFilters', JSON.stringify(this.activeFilters));
        },
        isActive(key) { return this.activeFilters.includes(key); }
    }"
    class="pl-calendar-page"
>
    {# ── Top bar: live clock + export ── #}
    <div class="pl-calendar-topbar">
        <div class="pl-calendar-topbar__left">
            {# View toggle #}
            <div class="pl-calendar-view-toggle">
                <button class="pl-calendar-view-toggle__btn"
                        :class="{ 'pl-calendar-view-toggle__btn--active': calView === 'week' }"
                        @click="setView('week')">Week</button>
                <button class="pl-calendar-view-toggle__btn"
                        :class="{ 'pl-calendar-view-toggle__btn--active': calView === 'month' }"
                        @click="setView('month')">Month</button>
            </div>
        </div>
        <div class="pl-calendar-topbar__right">
            {# Live clock #}
            <div class="pl-calendar-clock"
                 x-data="{ now: new Date() }"
                 x-init="setInterval(() => now = new Date(), 1000)">
                <span class="pl-calendar-clock__time"
                      x-text="now.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit'})"></span>
                <span class="pl-calendar-clock__date"
                      x-text="now.toLocaleDateString('en-US', {weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'})"></span>
            </div>
            {# Export dropdown #}
            <div class="pl-calendar-export" x-data="{ open: false }">
                <button class="pl-btn pl-btn--secondary pl-btn--sm" @click="open = !open" @click.away="open = false">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Add to Calendar
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 4.5l3 3 3-3"/>
                    </svg>
                </button>
                <div class="pl-calendar-export__dropdown" x-show="open" x-transition>
                    <a href="{% url 'hub_calendar_export_ics' %}" class="pl-calendar-export__item" download>
                        Download .ics (Apple / Outlook)
                    </a>
                    <a href="webcal://{{ request.get_host }}{% url 'hub_calendar_export_ics' %}"
                       class="pl-calendar-export__item">
                        Subscribe (webcal)
                    </a>
                </div>
            </div>
        </div>
    </div>

    {# ── Filter toggles ── #}
    <div class="pl-calendar-filters">
        {% if general_enabled %}
        <button class="pl-calendar-filter"
                :class="{ 'pl-calendar-filter--active': isActive('general') }"
                @click="toggleFilter('general')"
                style="--filter-color: {{ general_color }};">
            <span class="pl-calendar-filter__dot" style="background: {{ general_color }};"></span>
            General
        </button>
        {% endif %}
        {% for guild in guilds_with_calendars %}
        <button class="pl-calendar-filter"
                :class="{ 'pl-calendar-filter--active': isActive('{{ guild.pk }}') }"
                @click="toggleFilter('{{ guild.pk }}')"
                style="--filter-color: {{ guild.calendar_color }};">
            <span class="pl-calendar-filter__dot" style="background: {{ guild.calendar_color }};"></span>
            {{ guild.name }}
        </button>
        {% endfor %}
        {% if not general_enabled and not guilds_with_calendars %}
        <p class="pl-calendar-empty-notice">No calendars configured yet. Guild officers can add a Google Calendar link from their guild page.</p>
        {% endif %}
    </div>

    {# ── Calendar events area (HTMX auto-refresh every 5 min) ── #}
    <div id="pl-calendar-events-area"
         hx-get="{% url 'hub_community_calendar_events' %}"
         hx-trigger="every 300s"
         hx-swap="innerHTML">
        {% include "hub/partials/calendar_content.html" %}
    </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Update `community_calendar` view to pass `default_filters_json`**

In `hub/views.py`, update the `community_calendar` view to pass `default_filters_json`:

```python
@login_required
def community_calendar(request: HttpRequest) -> HttpResponse:
    """Community Calendar page — shows upcoming events from all guild and general calendars."""
    import json as _json
    ctx = _get_hub_context(request)
    cal_ctx = _get_calendar_context(request)

    # Build default filter keys (all sources enabled by default)
    default_filters = []
    if cal_ctx["general_enabled"]:
        default_filters.append("general")
    for g in cal_ctx["guilds_with_calendars"]:
        default_filters.append(str(g.pk))

    cal_ctx["default_filters_json"] = _json.dumps(default_filters).replace('"', '\\"')
    return render(request, "hub/community_calendar.html", {**ctx, **cal_ctx})
```

- [ ] **Step 3: Create `templates/hub/partials/calendar_content.html`**

This partial renders the calendar grid (week or month) and the event list below it. Since Alpine.js controls the view toggle, both grids are rendered in the DOM; Alpine hides the inactive one.

```django
{# calendar_content.html — HTMX-swappable calendar grid + event list.
   Rendered server-side initially; replaced by HTMX every 5 min.
   Alpine x-data is on the parent page; this partial reads from it via x-show. #}
{% load hub_tags %}

{# ── Week grid ── #}
<div class="pl-calendar-grid pl-calendar-grid--week" x-show="calView === 'week'">
    {% for day in week_days %}
    <div class="pl-calendar-grid__day {% if day.is_today %}pl-calendar-grid__day--today{% endif %}">
        <div class="pl-calendar-grid__day-header">
            <span class="pl-calendar-grid__day-name">{{ day.date|date:"D" }}</span>
            <span class="pl-calendar-grid__day-num {% if day.is_today %}pl-calendar-grid__day-num--today{% endif %}">{{ day.date|date:"j" }}</span>
        </div>
        <div class="pl-calendar-grid__day-dots">
            {% for event in day.events %}
            {% with src=event.guild.pk|default:"general"|stringformat:"s" %}
            <span class="pl-calendar-grid__dot"
                  style="background: {{ source_colors|get_item:src|default:'#888' }};"
                  x-show="isActive('{{ src }}')"
                  title="{{ event.title }}"></span>
            {% endwith %}
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>

{# ── Month grid ── #}
<div class="pl-calendar-grid pl-calendar-grid--month" x-show="calView === 'month'">
    {# Day-of-week headers #}
    {% for header in month_headers %}
    <div class="pl-calendar-grid__week-header">{{ header }}</div>
    {% endfor %}
    {# Month cells #}
    {% for day in month_days %}
    <div class="pl-calendar-grid__day
                {% if day.is_today %}pl-calendar-grid__day--today{% endif %}
                {% if not day.in_month %}pl-calendar-grid__day--faded{% endif %}">
        <div class="pl-calendar-grid__day-header">
            <span class="pl-calendar-grid__day-num {% if day.is_today %}pl-calendar-grid__day-num--today{% endif %}">{{ day.date|date:"j" }}</span>
        </div>
        <div class="pl-calendar-grid__day-dots">
            {% for event in day.events %}
            {% with src=event.guild.pk|default:"general"|stringformat:"s" %}
            <span class="pl-calendar-grid__dot"
                  style="background: {{ source_colors|get_item:src|default:'#888' }};"
                  x-show="isActive('{{ src }}')"
                  title="{{ event.title }}"></span>
            {% endwith %}
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>

{# ── Event List ── #}
<div class="pl-calendar-list">
    {% if events %}
    {% for event in events %}
    {% with src=event.guild.pk|default:"general"|stringformat:"s" %}
    <div class="pl-calendar-list__item"
         x-show="isActive('{{ src }}')"
         style="--event-color: {{ source_colors|get_item:src|default:'#888' }};">
        <div class="pl-calendar-list__time">
            {% if event.all_day %}
                <span class="pl-calendar-list__time-day">{{ event.start_dt|date:"D, M j" }}</span>
                <span class="pl-calendar-list__time-hour">All day</span>
            {% else %}
                <span class="pl-calendar-list__time-day">{{ event.start_dt|date:"D, M j" }}</span>
                <span class="pl-calendar-list__time-hour">{{ event.start_dt|date:"g:i A" }}</span>
            {% endif %}
        </div>
        <div class="pl-calendar-list__body">
            <div class="pl-calendar-list__title">{{ event.title }}</div>
            {% if event.description %}
            <div class="pl-calendar-list__desc">{{ event.description|truncatechars:120 }}</div>
            {% endif %}
            {% if event.location %}
            <div class="pl-calendar-list__location">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                {{ event.location }}
            </div>
            {% endif %}
            {% if event.guild %}
            <div class="pl-calendar-list__guild" style="color: {{ source_colors|get_item:src|default:'#888' }};">
                {{ event.guild.name }}
            </div>
            {% else %}
            <div class="pl-calendar-list__guild" style="color: {{ general_color }};">
                General
            </div>
            {% endif %}
        </div>
    </div>
    {% endwith %}
    {% endfor %}
    {% else %}
    <div class="pl-calendar-empty">
        <p>No upcoming events in the next 90 days.</p>
        <p class="pl-calendar-empty__hint">Guild officers can add a Google Calendar link from their guild page.</p>
    </div>
    {% endif %}
</div>
```

- [ ] **Step 4: Update `_get_calendar_context` in `hub/views.py` to supply week/month grid data**

Replace the `_get_calendar_context` function:

```python
def _get_calendar_context(request: HttpRequest) -> dict[str, Any]:
    """Build context for both the full calendar page and the HTMX partial."""
    import calendar as _cal
    from core.models import SiteConfiguration
    from membership.models import CalendarEvent, Guild

    now = dj_timezone.now()
    today = now.date()
    horizon = now + timedelta(days=90)

    events = list(
        CalendarEvent.objects.filter(start_dt__gte=now, start_dt__lte=horizon)
        .select_related("guild")
        .order_by("start_dt")
    )

    guilds_with_calendars = list(Guild.objects.filter(is_active=True, calendar_url__gt="").order_by("name"))

    config = SiteConfiguration.load()
    general_enabled = bool(config.general_calendar_url)
    general_color = config.general_calendar_color

    source_colors: dict[str, str] = {"general": general_color}
    for g in guilds_with_calendars:
        source_colors[str(g.pk)] = g.calendar_color

    # Group events by date for calendar grid
    from collections import defaultdict
    events_by_date: dict = defaultdict(list)
    for evt in events:
        events_by_date[evt.start_dt.date()].append(evt)

    # Week grid: 7 days starting from the Monday of the current week
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        week_days.append({"date": d, "is_today": d == today, "events": events_by_date.get(d, [])})

    # Month grid: current month, with leading/trailing days to fill 7-col rows
    month_headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    first_of_month = today.replace(day=1)
    # Python weekday(): Monday=0, Sunday=6
    leading = first_of_month.weekday()  # days to pad before the 1st
    last_day = _cal.monthrange(today.year, today.month)[1]
    last_of_month = today.replace(day=last_day)
    trailing = (6 - last_of_month.weekday()) % 7

    month_days = []
    for i in range(leading):
        d = first_of_month - timedelta(days=leading - i)
        month_days.append({"date": d, "is_today": False, "in_month": False, "events": events_by_date.get(d, [])})
    for day_num in range(1, last_day + 1):
        d = today.replace(day=day_num)
        month_days.append({"date": d, "is_today": d == today, "in_month": True, "events": events_by_date.get(d, [])})
    for i in range(1, trailing + 1):
        d = last_of_month + timedelta(days=i)
        month_days.append({"date": d, "is_today": False, "in_month": False, "events": events_by_date.get(d, [])})

    return {
        "events": events,
        "guilds_with_calendars": guilds_with_calendars,
        "general_enabled": general_enabled,
        "general_color": general_color,
        "source_colors": source_colors,
        "week_days": week_days,
        "month_days": month_days,
        "month_headers": month_headers,
        "now": now,
    }
```

- [ ] **Step 5: Add `get_item` template filter to `hub/templatetags/hub_tags.py`**

Open `hub/templatetags/hub_tags.py`. Add this filter (needed by `calendar_content.html` to look up colors from the dict):

```python
@register.filter
def get_item(dictionary: dict, key: str) -> Any:
    """Look up a key in a dict within a template: {{ my_dict|get_item:key }}"""
    return dictionary.get(str(key))
```

Make sure `from typing import Any` is imported in that file.

- [ ] **Step 6: Run all calendar tests**

```bash
pytest tests/hub/community_calendar_spec.py -v
# Expected: all tests pass
```

- [ ] **Step 7: Commit**

```bash
git add templates/hub/community_calendar.html templates/hub/partials/calendar_content.html
git add hub/views.py hub/templatetags/hub_tags.py
git commit -m "feat(hub): add Community Calendar full page and HTMX partial templates"
```

---

## Task 10: Calendar CSS

**Files:**
- Create: `static/css/calendar.css`
- Modify: `templates/hub/community_calendar.html` (already links the file)

- [ ] **Step 1: Create `static/css/calendar.css`**

```css
/* ============================================================
   Community Calendar — Past Lives Makerspace
   Uses the same CSS variables as hub.css for dark/light theme.
   ============================================================ */

/* ── Page layout ── */
.pl-calendar-page {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
}

/* ── Top bar ── */
.pl-calendar-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
}

.pl-calendar-topbar__left,
.pl-calendar-topbar__right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

/* ── View toggle ── */
.pl-calendar-view-toggle {
    display: flex;
    background: var(--hub-card-bg);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    overflow: hidden;
}

.pl-calendar-view-toggle__btn {
    padding: 0.375rem 0.875rem;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--hub-text-muted);
    background: transparent;
    border: none;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
}

.pl-calendar-view-toggle__btn--active {
    background: var(--color-tuscan-yellow);
    color: #1a1a2e;
}

/* ── Clock ── */
.pl-calendar-clock {
    text-align: right;
    line-height: 1.2;
}

.pl-calendar-clock__time {
    display: block;
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--hub-text);
    font-family: 'Lato', sans-serif;
}

.pl-calendar-clock__date {
    display: block;
    font-size: 0.75rem;
    color: var(--hub-text-muted);
}

/* ── Export dropdown ── */
.pl-calendar-export {
    position: relative;
}

.pl-calendar-export__dropdown {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    background: var(--hub-card-bg);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    min-width: 220px;
    z-index: 100;
    overflow: hidden;
}

.pl-calendar-export__item {
    display: block;
    padding: 0.625rem 1rem;
    font-size: 0.8125rem;
    color: var(--hub-text);
    text-decoration: none;
    transition: background 0.15s;
}

.pl-calendar-export__item:hover {
    background: rgba(255,255,255,0.06);
}

/* ── Filter toggles ── */
.pl-calendar-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
}

.pl-calendar-filter {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    border: 1.5px solid var(--filter-color, #888);
    background: transparent;
    color: var(--hub-text-muted);
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s, color 0.15s, opacity 0.15s;
    opacity: 0.5;
}

.pl-calendar-filter--active {
    background: color-mix(in srgb, var(--filter-color, #888) 18%, transparent);
    color: var(--hub-text);
    opacity: 1;
}

.pl-calendar-filter__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}

.pl-calendar-empty-notice {
    font-size: 0.8125rem;
    color: var(--hub-text-muted);
}

/* ── Calendar grid (shared week + month) ── */
.pl-calendar-grid {
    background: var(--hub-card-bg);
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.06);
    overflow: hidden;
}

/* Week grid: 7 equal columns */
.pl-calendar-grid--week {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
}

/* Month grid: 7 columns (day headers + day cells share the same grid) */
.pl-calendar-grid--month {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
}

.pl-calendar-grid__week-header {
    padding: 0.5rem 0;
    font-size: 0.6875rem;
    font-weight: 600;
    text-align: center;
    color: var(--hub-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}

.pl-calendar-grid__day {
    padding: 0.625rem 0.5rem;
    border-right: 1px solid rgba(255,255,255,0.04);
    border-bottom: 1px solid rgba(255,255,255,0.04);
    min-height: 72px;
}

.pl-calendar-grid--week .pl-calendar-grid__day {
    min-height: 96px;
}

.pl-calendar-grid__day:last-child,
.pl-calendar-grid__day:nth-child(7n) {
    border-right: none;
}

.pl-calendar-grid__day--today {
    background: rgba(238, 180, 75, 0.06);
}

.pl-calendar-grid__day--faded {
    opacity: 0.4;
}

.pl-calendar-grid__day-header {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 0.5rem;
    gap: 2px;
}

.pl-calendar-grid--week .pl-calendar-grid__day-header {
    flex-direction: row;
    justify-content: center;
    gap: 0.375rem;
}

.pl-calendar-grid__day-name {
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--hub-text-muted);
}

.pl-calendar-grid__day-num {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--hub-text-muted);
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
}

.pl-calendar-grid__day-num--today {
    background: var(--color-tuscan-yellow);
    color: #1a1a2e;
    font-weight: 700;
}

.pl-calendar-grid__day-dots {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    justify-content: center;
}

.pl-calendar-grid__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
}

/* ── Event list ── */
.pl-calendar-list {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
    margin-top: 0.25rem;
}

.pl-calendar-list__item {
    display: flex;
    gap: 1rem;
    background: var(--hub-card-bg);
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.06);
    border-left: 4px solid var(--event-color, #888);
    padding: 0.875rem 1rem;
    align-items: flex-start;
}

.pl-calendar-list__time {
    flex-shrink: 0;
    min-width: 72px;
    text-align: right;
}

.pl-calendar-list__time-day {
    display: block;
    font-size: 0.6875rem;
    color: var(--hub-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.pl-calendar-list__time-hour {
    display: block;
    font-size: 1rem;
    font-weight: 700;
    color: var(--hub-text);
    font-family: 'Lato', sans-serif;
}

.pl-calendar-list__body {
    flex: 1;
    min-width: 0;
}

.pl-calendar-list__title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--hub-text);
    line-height: 1.3;
}

.pl-calendar-list__desc {
    margin-top: 0.25rem;
    font-size: 0.8125rem;
    color: var(--hub-text-muted);
    line-height: 1.5;
}

.pl-calendar-list__location {
    margin-top: 0.375rem;
    font-size: 0.75rem;
    color: var(--hub-text-muted);
    display: flex;
    align-items: center;
    gap: 4px;
}

.pl-calendar-list__guild {
    margin-top: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.pl-calendar-empty {
    text-align: center;
    padding: 2.5rem 1rem;
    color: var(--hub-text-muted);
}

.pl-calendar-empty__hint {
    font-size: 0.8125rem;
    margin-top: 0.5rem;
}

/* ── Light theme overrides ── */
[data-theme="light"] .pl-calendar-view-toggle {
    border-color: rgba(0,0,0,0.1);
}

[data-theme="light"] .pl-calendar-grid {
    border-color: rgba(0,0,0,0.08);
}

[data-theme="light"] .pl-calendar-grid__day {
    border-color: rgba(0,0,0,0.06);
}

[data-theme="light"] .pl-calendar-list__item {
    border-color: rgba(0,0,0,0.08);
    border-left-color: var(--event-color, #888);
}

[data-theme="light"] .pl-calendar-export__dropdown {
    border-color: rgba(0,0,0,0.1);
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}

/* ── Responsive ── */
@media (max-width: 600px) {
    .pl-calendar-grid__day-name {
        display: none;
    }
    .pl-calendar-list__item {
        flex-direction: column;
        gap: 0.5rem;
    }
    .pl-calendar-list__time {
        text-align: left;
        display: flex;
        gap: 0.5rem;
        align-items: baseline;
    }
}
```

- [ ] **Step 2: Link the CSS in the template**

The template already has `{% static 'css/calendar.css' %}` in `{% block extra_js %}`. Verify it's correct:
```django
{% block extra_js %}
<link rel="stylesheet" href="{% static 'css/calendar.css' %}">
{% endblock %}
```

- [ ] **Step 3: Visual check in browser**

```bash
python manage.py runserver
# Open http://localhost:8000/calendar/
# Verify: page loads without errors, calendar grid shows, event list renders
# Toggle week/month — both views switch
# Toggle filter pills — events show/hide by source
# Clock ticks in real time
```

- [ ] **Step 4: Commit**

```bash
git add static/css/calendar.css
git add templates/hub/community_calendar.html
git commit -m "feat(hub): add Community Calendar CSS — grid, event list, filters, light/dark themes"
```

---

## Task 11: Guild edit — add calendar fields to guild page UI

**Files:**
- Modify: `templates/hub/guild_detail.html`

Guild officers see a "Calendar" section in their guild edit panel with a URL field and a color picker.

- [ ] **Step 1: Open `templates/hub/guild_detail.html` and locate the guild edit section**

Find the `can_edit_this_guild` block that renders `guild_edit_form`. It will have the name and about fields. Add a calendar section below them.

Look for the block that renders the guild edit form fields (something like `{% include "components/form_field.html" with field=guild_edit_form.about %}`).

After the existing form fields (name, about), add:

```django
{# Calendar section — only for guild editors #}
<div class="hub-card" style="margin-top: 1rem;">
    <h3 class="hub-card__title">Calendar Integration</h3>
    <p class="hub-card__subtitle">Connect your guild's Google Calendar so events appear on the Community Calendar.</p>
    <form method="post" action="{% url 'hub_guild_edit' guild.pk %}">
        {% csrf_token %}
        {% include "components/form_field.html" with field=guild_edit_form.calendar_url %}
        <div style="display: flex; align-items: center; gap: 0.75rem; margin-top: 0.75rem;">
            {% include "components/form_field.html" with field=guild_edit_form.calendar_color field_label="Event Color" %}
        </div>
        <button type="submit" class="pl-btn pl-btn--primary pl-btn--sm" style="margin-top: 0.75rem;">Save Calendar Settings</button>
    </form>
</div>
```

> **Note:** The guild edit form already handles `name` and `about` in a separate section. This adds a new card for calendar settings. The form posts to the same `hub_guild_edit` endpoint — since `GuildEditForm` now includes `calendar_url` and `calendar_color`, the existing view handles them automatically.

- [ ] **Step 2: Test that guild officers see the calendar section**

```bash
pytest tests/hub/guild_edit_spec.py -v
# All existing tests should still pass
```

Manually verify in browser:
- Log in as a guild officer, navigate to your guild's page
- Confirm "Calendar Integration" section is visible with URL field and color picker
- Submit the form — verify `guild.calendar_url` and `guild.calendar_color` are saved

- [ ] **Step 3: Commit**

```bash
git add templates/hub/guild_detail.html
git commit -m "feat(hub): add calendar URL and color fields to guild edit panel"
```

---

## Task 12: Admin — expose general calendar in SiteConfiguration

**Files:**
- Identify: `plfog/auto_admin.py` or wherever `SiteConfiguration` is registered in admin
- Modify: the admin registration for `SiteConfiguration`

- [ ] **Step 1: Find how SiteConfiguration is registered**

```bash
grep -r "SiteConfiguration" /home/josh/Code/plfog/plfog/ --include="*.py" -l
grep -r "SiteConfiguration" /home/josh/Code/plfog/core/ --include="*.py" -l
```

Check `plfog/auto_admin.py` or `core/admin.py` for the registration.

- [ ] **Step 2: Add `general_calendar_url` and `general_calendar_color` to the admin fieldsets**

If `SiteConfiguration` uses a custom `ModelAdmin`, add the fields to the fieldsets:

```python
class SiteConfigurationAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Registration", {
            "fields": ["registration_mode"],
        }),
        ("Community Calendar", {
            "fields": ["general_calendar_url", "general_calendar_color"],
            "description": "Configure the general makerspace calendar shown on the Community Calendar page.",
        }),
    ]
```

If it uses auto-registration (no custom admin), create a custom `ModelAdmin` in `core/admin.py`.

- [ ] **Step 3: Verify in admin**

```bash
python manage.py runserver
# Open http://localhost:8000/admin/core/siteconfiguration/1/change/
# Confirm new calendar fields are present
```

- [ ] **Step 4: Commit**

```bash
git add core/admin.py  # or plfog/auto_admin.py — wherever the change was made
git commit -m "feat(admin): expose general calendar URL and color in SiteConfiguration admin"
```

---

## Task 13: Run full test suite and fix any gaps

**Files:**
- Modify: tests as needed

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v
```

- [ ] **Step 2: Fix any failing tests**

Common failures to expect:
- Coverage gaps in new view code — add tests to `tests/hub/community_calendar_spec.py`
- Template tag `get_item` not tested — add a test in `tests/hub/templatetags_spec.py`
- Missing test for `calendar_export_ics` content structure

Add to `tests/hub/community_calendar_spec.py` if coverage is below 100%:

```python
@pytest.mark.django_db
def describe_get_calendar_context():
    def it_builds_week_days_with_7_entries(client: Client):
        from hub.views import _get_calendar_context
        _logged_in_user(client)
        # Make a fake request
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/calendar/")
        from django.contrib.auth.models import User
        request.user = User.objects.get(username="caluser")
        ctx = _get_calendar_context(request)
        assert len(ctx["week_days"]) == 7
        assert any(d["is_today"] for d in ctx["week_days"])

    def it_builds_month_days_in_complete_weeks(client: Client):
        from hub.views import _get_calendar_context
        _logged_in_user(client)
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/calendar/")
        from django.contrib.auth.models import User
        request.user = User.objects.get(username="caluser")
        ctx = _get_calendar_context(request)
        assert len(ctx["month_days"]) % 7 == 0
```

- [ ] **Step 3: Verify 100% coverage**

```bash
pytest --cov=hub --cov=membership --cov=core --cov-report=term-missing
# Ensure coverage is 100% on new code
```

- [ ] **Step 4: Run ruff and mypy**

```bash
ruff format . && ruff check --fix .
mypy .
```

- [ ] **Step 5: Commit any fixes**

```bash
git add -p  # stage only the relevant test and code fixes
git commit -m "test: achieve 100% coverage on Community Calendar code"
```

---

## Task 14: Version bump and changelog

**Files:**
- Modify: `plfog/version.py`

- [ ] **Step 1: Bump version to 1.6.0 in `plfog/version.py`**

Change:
```python
VERSION = "1.5.7"
```
to:
```python
VERSION = "1.6.0"
```

- [ ] **Step 2: Add changelog entry at the top of `CHANGELOG`**

Insert as the first entry:

```python
    {
        "version": "1.6.0",
        "date": "2026-04-15",
        "title": "Community Calendar",
        "changes": [
            "New Community Calendar page in the sidebar (above Guild Voting) — see upcoming events from all guilds and the makerspace in one place",
            "Week view shows the current 7-day window with colored dots for events; month view shows the full calendar grid — toggle between them with the Week / Month buttons",
            "Each source (guild or general makerspace) has a color-coded filter pill — click to show or hide events from that source",
            "Guild leads and officers can link their Google Calendar from the guild page edit section — paste the 'Secret address in iCal format' URL and pick a color",
            "Events refresh automatically in the background every 5 minutes — no manual reload needed",
            "The event list below the calendar shows full details: time, location, description, and source guild",
            "Top-right clock shows the current time and date at a glance",
            "Export button lets you download all events as a .ics file (works with Apple Calendar, Outlook, and Google Calendar) or subscribe via webcal link",
            "Admins can configure the general makerspace calendar URL and color in Site Settings in the admin panel",
        ],
    },
```

- [ ] **Step 3: Run tests to confirm nothing is broken**

```bash
pytest -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add plfog/version.py
git commit -m "chore: bump version to 1.6.0 — Community Calendar"
```

---

## Self-Review Checklist

### Spec Coverage

| Requirement | Task(s) |
|---|---|
| Community Calendar sidebar link above Guild Voting | Task 8 |
| Full month view (toggleable) | Task 9 (Alpine.js month grid) |
| 1-week view | Task 9 (Alpine.js week grid) |
| Toggle filters by guild + general option | Task 9 template, Task 10 CSS |
| HTMX auto-refresh (every 5 min) | Task 7 (calendar_events_partial), Task 9 template |
| Pull events from Google Calendars (iCal) | Task 5 (calendar_service.py) |
| Guild officers add Google Calendar link | Task 6 (GuildEditForm), Task 11 (template) |
| Color-coded guilds | Tasks 2/3 (model fields), Task 9/10 (CSS) |
| Guild officer chooses color | Task 6 (color picker in form), Task 11 |
| Calendar view (grid) | Task 9 |
| Event list below with details | Task 9 |
| Current date/time top right | Task 9 (Alpine clock) |
| Export to Apple/Outlook/Google | Task 7 (export_ics view), Task 9 (export dropdown) |
| Admin configures general calendar | Task 12 |
| Version bump + changelog | Task 14 |

All requirements covered.

### Placeholder Scan

No TBD, TODO, or placeholder steps found — each step has complete code.

### Type Consistency

- `CalendarEvent` model fields match what the service writes: `uid`, `title`, `description`, `location`, `url`, `start_dt`, `end_dt`, `all_day`, `fetched_at`
- `_get_calendar_context` returns `week_days`, `month_days`, `month_headers`, `events`, `guilds_with_calendars`, `general_enabled`, `general_color`, `source_colors` — all referenced consistently in templates
- `sync_guild_calendar(guild: Guild) -> int` / `sync_general_calendar() -> int` — return type consistent with test assertions
- `refresh_stale_sources(max_age_seconds: int = 900) -> None` — mocked in view tests as `hub.views.refresh_stale_sources`
- `GuildEditForm.Meta.fields` adds `calendar_url`, `calendar_color` — matches model field names

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-15-community-calendar.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
