"""Calendar service — fetches iCal feeds, parses events, and upserts CalendarEvent records."""

from __future__ import annotations

import urllib.request
from datetime import date as date_type
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any

from django.utils import timezone

from core.models import SiteConfiguration
from membership.models import CalendarEvent, Guild

DEFAULT_MAX_AGE_SECONDS = 900  # 15 minutes


def _to_datetime(val: Any) -> datetime:
    """Convert a date or datetime value to a UTC-aware datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=dt_timezone.utc)
        return val.astimezone(dt_timezone.utc)
    return datetime(val.year, val.month, val.day, tzinfo=dt_timezone.utc)


def _parse_ical_events(raw_bytes: bytes) -> list[dict[str, Any]]:
    """Parse raw iCal bytes into a list of event dicts."""
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
        all_day = isinstance(start_val, date_type) and not isinstance(start_val, datetime)

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
    """Fetch an iCal URL and return parsed event dicts."""
    with urllib.request.urlopen(url, timeout=10) as response:
        raw = response.read()
    return _parse_ical_events(raw)


def _upsert_events(events: list[dict[str, Any]], guild: Guild | None) -> int:
    """Insert or update CalendarEvent records for the given source."""
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
    """Fetch and sync a guild's iCal calendar. Returns events synced (0 if no URL)."""
    if not guild.calendar_url:
        return 0
    events = _fetch_and_parse(guild.calendar_url)
    count = _upsert_events(events, guild=guild)
    guild.calendar_last_fetched_at = timezone.now()
    guild.save(update_fields=["calendar_last_fetched_at"])
    return count


def sync_general_calendar() -> int:
    """Fetch and sync the general makerspace calendar. Returns events synced (0 if no URL)."""
    config = SiteConfiguration.load()
    if not config.general_calendar_url:
        return 0
    events = _fetch_and_parse(config.general_calendar_url)
    count = _upsert_events(events, guild=None)
    config.general_calendar_last_fetched_at = timezone.now()
    config.save(update_fields=["general_calendar_last_fetched_at"])
    return count


def refresh_stale_sources(max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> None:
    """Refresh any calendar sources not synced within max_age_seconds.

    Called by the calendar_events_partial view on each HTMX poll.
    Exceptions from individual sources are caught so one bad calendar
    cannot crash the page for all users.
    """
    cutoff = timezone.now() - timedelta(seconds=max_age_seconds)

    stale_guilds = Guild.objects.filter(
        is_active=True,
        calendar_url__gt="",
    ).exclude(calendar_last_fetched_at__gte=cutoff)

    for guild in stale_guilds:
        try:
            sync_guild_calendar(guild)
        except Exception:  # noqa: BLE001
            pass

    config = SiteConfiguration.load()
    if config.general_calendar_url:
        general_stale = (
            config.general_calendar_last_fetched_at is None or config.general_calendar_last_fetched_at < cutoff
        )
        if general_stale:
            try:
                sync_general_calendar()
            except Exception:  # noqa: BLE001
                pass
