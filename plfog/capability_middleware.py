"""Middleware that attaches a ``Capabilities`` object to every request.

Runs after ``AuthenticationMiddleware`` and ``SessionMiddleware`` so that
``request.user`` and ``request.session`` are both available. Views and
template tags read ``request.capabilities`` to make permission decisions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from plfog.capabilities import Capabilities

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class CapabilityMiddleware:
    def __init__(self, get_response: "Callable[[HttpRequest], HttpResponse]") -> None:
        self.get_response = get_response

    def __call__(self, request: "HttpRequest") -> "HttpResponse":
        request.capabilities = Capabilities.for_request(request)
        return self.get_response(request)
