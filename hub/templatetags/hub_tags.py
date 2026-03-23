from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import template
from django.db.models import QuerySet

if TYPE_CHECKING:
    from membership.models import Guild

register = template.Library()


@register.simple_tag(takes_context=True)
def active_nav(context: dict[str, Any], url_name: str, pk: int | None = None) -> str:
    """Return 'active' if the current URL matches the given URL name."""
    request = context.get("request")
    if request is None:
        return ""
    from django.urls import reverse

    if pk is not None:
        target = reverse(url_name, args=[pk])
    else:
        target = reverse(url_name)
    return "active" if request.path == target else ""


@register.simple_tag(takes_context=True)
def has_active_guild(context: dict[str, Any], guilds: QuerySet[Guild]) -> bool:
    """Return True if the current page is a guild detail page."""
    request = context.get("request")
    if request is None:
        return False
    from django.urls import reverse

    for guild in guilds:
        if request.path == reverse("hub_guild_detail", args=[guild.pk]):
            return True
    return False
