"""Thin wrapper around pyairtable for Django settings integration."""

from __future__ import annotations

from django.conf import settings
from pyairtable import Api
from pyairtable import Table


def get_api() -> Api:
    """Return a pyairtable Api instance configured from Django settings."""
    return Api(settings.AIRTABLE_API_TOKEN)


def get_table(table_id: str) -> Table:
    """Return a pyairtable Table bound to the configured base."""
    return get_api().table(settings.AIRTABLE_BASE_ID, table_id)
