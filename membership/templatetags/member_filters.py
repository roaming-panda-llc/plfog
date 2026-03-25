"""Template tags for rendering admin filter specs as dropdown options."""

from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


@register.filter
def filter_choices(spec: Any, cl: Any) -> list[dict[str, Any]]:
    """Return the list of choices for a filter spec, passing the changelist."""
    return list(spec.choices(cl))
