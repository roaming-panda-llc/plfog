"""Template context processors for core app."""

from __future__ import annotations

from django.http import HttpRequest


def registration_mode(request: HttpRequest) -> dict[str, bool]:
    """Add registration_is_open flag to template context."""
    from core.models import SiteConfiguration

    config = SiteConfiguration.load()
    return {"registration_is_open": config.registration_mode == SiteConfiguration.RegistrationMode.OPEN}
