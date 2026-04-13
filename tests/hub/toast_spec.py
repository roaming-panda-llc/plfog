"""BDD specs for the toast notification utility."""

from __future__ import annotations

import json

from django.http import HttpResponse

from hub.toast import trigger_toast


def describe_trigger_toast():
    def it_sets_hx_trigger_header_with_success_type():
        response = HttpResponse(status=204)
        trigger_toast(response, "Item added!", "success")
        payload = json.loads(response["HX-Trigger"])
        assert payload == {"showToast": {"message": "Item added!", "type": "success"}}

    def it_defaults_to_success_type():
        response = HttpResponse(status=204)
        trigger_toast(response, "Done!")
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["type"] == "success"

    def it_supports_error_type():
        response = HttpResponse(status=200)
        trigger_toast(response, "Something went wrong", "error")
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["type"] == "error"

    def it_supports_info_type():
        response = HttpResponse(status=200)
        trigger_toast(response, "FYI", "info")
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["type"] == "info"

    def it_preserves_existing_response_content():
        response = HttpResponse("OK", status=200)
        trigger_toast(response, "Added!")
        assert response.content == b"OK"
        assert response.status_code == 200
        assert "HX-Trigger" in response
