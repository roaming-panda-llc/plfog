from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import template

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from membership.models import Guild

register = template.Library()


@register.simple_tag(takes_context=True)
def active_nav(context: dict[str, Any], *args: str | int) -> str:
    """Return 'active' if the current URL matches any of the given URL names.

    Examples:
        {% active_nav 'hub_guild_voting' %}
        {% active_nav 'hub_guild_detail' guild.pk %}
        {% active_nav 'hub_tab_detail' 'hub_tab_history' %}
    """
    request = context.get("request")
    if request is None:
        return ""
    from django.urls import reverse

    url_names: list[str] = []
    pk: int | None = None
    for arg in args:
        if isinstance(arg, int):
            pk = arg
        else:
            url_names.append(arg)

    for name in url_names:
        target = reverse(name, args=[pk] if pk is not None else [])
        if request.path == target:
            return "active"
    return ""


@register.filter
def get_item(dictionary: dict, key: str) -> Any:
    """Look up a key in a dict: {{ my_dict|get_item:key }}"""
    return dictionary.get(str(key))


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
