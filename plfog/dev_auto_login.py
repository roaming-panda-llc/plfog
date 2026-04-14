"""Dev-only middleware that force-logs-in a superuser on every request.

Enabled via the DEV_AUTO_LOGIN_EMAIL env var (typically set in local runserver
environments). Never include this middleware when DEBUG is False — it would
be a complete auth bypass in production.
"""

from __future__ import annotations

import os
from typing import Callable

from django.contrib.auth import get_user_model, login
from django.http import HttpRequest, HttpResponse


class DevAutoLoginMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.email = os.environ.get("DEV_AUTO_LOGIN_EMAIL", "").strip()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if self.email and not request.user.is_authenticated:
            User = get_user_model()
            user = User.objects.filter(email=self.email).first()
            if user is not None:
                user.backend = "django.contrib.auth.backends.ModelBackend"
                login(request, user)
        return self.get_response(request)
