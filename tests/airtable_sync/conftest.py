from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def mock_airtable_table():
    """Provide a mock pyairtable Table and patch get_table to return it."""
    mock_table = MagicMock()
    mock_table.create.return_value = {"id": "recTEST123456789", "fields": {}}
    mock_table.update.return_value = {"id": "recTEST123456789", "fields": {}}
    mock_table.delete.return_value = {"id": "recTEST123456789", "deleted": True}
    mock_table.all.return_value = []
    with patch("airtable_sync.service.get_table", return_value=mock_table):
        yield mock_table


@pytest.fixture()
def enable_airtable_sync(settings):
    """Enable Airtable sync for a specific test."""
    settings.AIRTABLE_SYNC_ENABLED = True
