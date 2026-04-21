"""BDD specs for Instructor."""

from __future__ import annotations

import pytest

from classes.factories import InstructorFactory
from classes.models import Instructor


def describe_Instructor():
    def it_stringifies_as_display_name(db):
        instructor = InstructorFactory(display_name="Jane Doe")
        assert str(instructor) == "Jane Doe"

    def it_requires_unique_slug(db):
        InstructorFactory(slug="jane-doe")
        with pytest.raises(Exception):
            InstructorFactory(slug="jane-doe")

    def it_orders_by_display_name(db):
        InstructorFactory(display_name="Zach")
        InstructorFactory(display_name="Alice")
        names = list(Instructor.objects.values_list("display_name", flat=True))
        assert names == ["Alice", "Zach"]

    def it_is_reachable_from_user_via_related_name(db):
        instructor = InstructorFactory()
        assert instructor.user.instructor.pk == instructor.pk
