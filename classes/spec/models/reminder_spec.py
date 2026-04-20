"""BDD specs for RegistrationReminder (skipped until Registration ships in Task 10)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Needs Registration + ClassSession — unskipped in Task 10.6")


def describe_RegistrationReminder():
    def it_enforces_unique_registration_session_pair(db):
        pass
