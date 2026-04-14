from __future__ import annotations

from django import template

from membership.models import Guild

register = template.Library()


@register.simple_tag
def active_guilds() -> list[dict]:
    """Return the active guild list as plain dicts for embedding in Alpine data."""
    return list(Guild.objects.filter(is_active=True).order_by("name").values("pk", "name"))
