"""Toast notification utility for HTMX responses."""

from __future__ import annotations

import json

from django.http import HttpResponse


def trigger_toast(response: HttpResponse, message: str, toast_type: str = "success") -> None:
    """Set the HX-Trigger header to show a toast notification on the client.

    Args:
        response: The HttpResponse to add the header to.
        message: The toast message text.
        toast_type: One of "success", "error", "info".
    """
    response["HX-Trigger"] = json.dumps({"showToast": {"message": message, "type": toast_type}})
