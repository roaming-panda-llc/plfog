"""Custom allauth adapter for auto-admin domain privileges and login redirect."""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse

logger = logging.getLogger(__name__)


class AdminRedirectAccountAdapter(DefaultAccountAdapter):
    """Grant admin privileges on login and redirect staff users to /admin/.

    On every login, if the user's email domain matches any domain in the
    ADMIN_DOMAINS setting (case-insensitive), the user gets is_staff=True
    and is_superuser=True.

    After login, staff users are redirected to the admin panel; everyone
    else goes to the member hub.
    """

    def login(self, request: HttpRequest, user: object) -> None:
        """Grant admin privileges if email domain matches, then log in."""
        self._maybe_grant_admin(user)
        super().login(request, user)

    def get_login_redirect_url(self, request: HttpRequest) -> str:
        """Redirect staff to /admin/, everyone else to the member hub."""
        if request.user.is_staff:
            return reverse("admin:index")
        return reverse("hub_guild_voting")

    def _maybe_grant_admin(self, user: object) -> None:
        """Check user's email domain and grant admin if it matches ADMIN_DOMAINS.

        Skips the database save if the user already has both ``is_staff``
        and ``is_superuser`` set to ``True``.
        """
        admin_domains: list[str] = getattr(settings, "ADMIN_DOMAINS", [])
        if not admin_domains:
            return

        email: str = getattr(user, "email", "") or ""
        if not email or "@" not in email:
            return

        domain = email.rsplit("@", 1)[1].lower()
        if domain in admin_domains:
            if user.is_staff and user.is_superuser:  # type: ignore[attr-defined]
                return
            user.is_staff = True  # type: ignore[attr-defined]
            user.is_superuser = True  # type: ignore[attr-defined]
            user.save(update_fields=["is_staff", "is_superuser"])  # type: ignore[attr-defined]
            logger.info("Auto-admin granted to %s (domain: %s)", email, domain)
