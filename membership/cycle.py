"""Voting cycle date calculations."""

from __future__ import annotations

import calendar
from typing import Any

from django.utils import timezone


def get_cycle_context() -> dict[str, Any]:
    """Build voting cycle context variables for the current month.

    Returns:
        Dict with current_cycle_label, cycle_closes_on, and next_cycle_begins.
    """
    now = timezone.now()
    current_cycle_label = now.strftime("%B %Y")
    last_day = calendar.monthrange(now.year, now.month)[1]
    cycle_closes_on = now.replace(day=last_day).strftime("%B %d, %Y").replace(" 0", " ")
    if now.month == 12:
        next_year = now.year + 1
        next_month = 1
    else:
        next_year = now.year
        next_month = now.month + 1
    next_cycle_begins = now.replace(year=next_year, month=next_month, day=1).strftime("%B %d, %Y").replace(" 0", " ")
    return {
        "current_cycle_label": current_cycle_label,
        "cycle_closes_on": cycle_closes_on,
        "next_cycle_begins": next_cycle_begins,
    }
