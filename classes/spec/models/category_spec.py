"""BDD specs for Category."""

from __future__ import annotations

from classes.factories import CategoryFactory
from classes.models import Category


def describe_Category():
    def it_stringifies_as_name(db):
        category = CategoryFactory(name="Woodworking")
        assert str(category) == "Woodworking"

    def it_orders_by_sort_then_name(db):
        CategoryFactory(name="Beta", sort_order=1)
        CategoryFactory(name="Alpha", sort_order=1)
        CategoryFactory(name="Zero", sort_order=0)
        names = list(Category.objects.values_list("name", flat=True))
        assert names == ["Zero", "Alpha", "Beta"]

    def it_enforces_name_uniqueness(db):
        CategoryFactory(name="Pottery")
        try:
            CategoryFactory(name="Pottery")
        except Exception:
            return
        raise AssertionError("duplicate name should have raised")
