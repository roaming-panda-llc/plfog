"""factory-boy factories for classes models."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from classes import models


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = models.Category

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    sort_order = 0
