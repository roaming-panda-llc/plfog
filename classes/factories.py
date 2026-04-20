"""factory-boy factories for classes models."""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

from classes import models


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = models.Category

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    sort_order = 0


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}@example.com")
    email = factory.LazyAttribute(lambda o: o.username)


class InstructorFactory(DjangoModelFactory):
    class Meta:
        model = models.Instructor

    user = factory.SubFactory(UserFactory)
    display_name = factory.Sequence(lambda n: f"Instructor {n}")
    slug = factory.LazyAttribute(lambda o: o.display_name.lower().replace(" ", "-"))
    bio = "A great teacher."
    is_active = True
