"""Tests for airtable_sync.client — thin pyairtable wrapper."""

from __future__ import annotations

from unittest.mock import patch

from airtable_sync.client import get_api, get_table


def describe_get_api():
    def it_returns_api_with_token(settings):
        settings.AIRTABLE_API_TOKEN = "test-token-123"
        with patch("airtable_sync.client.Api") as MockApi:
            api = get_api()
            MockApi.assert_called_once_with("test-token-123")
            assert api == MockApi.return_value


def describe_get_table():
    def it_returns_table_bound_to_base(settings):
        settings.AIRTABLE_API_TOKEN = "test-token-123"
        settings.AIRTABLE_BASE_ID = "appTEST123"
        with patch("airtable_sync.client.Api") as MockApi:
            table = get_table("tblTEST456")
            MockApi.return_value.table.assert_called_once_with("appTEST123", "tblTEST456")
            assert table == MockApi.return_value.table.return_value
