"""Template tags for the capability system.

Usage::

    {% load capabilities %}
    {% if request.capabilities|has:"admin" %}...{% endif %}
    {% if request.capabilities|can_manage:guild %}...{% endif %}

The filter form keeps templates readable and avoids quoting noise from
the ``{% if %}`` tag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import template

if TYPE_CHECKING:
    from membership.models import Guild

    from plfog.capabilities import Capabilities

register = template.Library()


@register.filter(name="has")
def has_capability(capabilities: "Capabilities | None", name: str) -> bool:
    if capabilities is None:
        return False
    return capabilities.has(name)


@register.filter(name="can_manage")
def can_manage(capabilities: "Capabilities | None", guild: "Guild") -> bool:
    if capabilities is None:
        return False
    return capabilities.can_manage_guild(guild)
