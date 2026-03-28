"""Template context processors for core app."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest


def registration_mode(request: HttpRequest) -> dict[str, bool]:
    """Add registration_is_open flag to template context."""
    from core.models import SiteConfiguration

    config = SiteConfiguration.load()
    return {"registration_is_open": config.registration_mode == SiteConfiguration.RegistrationMode.OPEN}


def app_version(request: HttpRequest) -> dict[str, Any]:
    """Add app version and changelog to template context."""
    from plfog.version import CHANGELOG, VERSION

    return {"app_version": VERSION, "changelog": CHANGELOG}
