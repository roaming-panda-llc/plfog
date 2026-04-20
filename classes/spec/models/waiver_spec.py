"""BDD specs for Waiver (skipped until Registration ships in Task 10)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Needs Registration — unskipped in Task 10.6")


def describe_Waiver():
    def it_placeholder(db):
        pass
