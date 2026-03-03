from __future__ import annotations

import factory
from django.contrib.auth.models import User

from core.models import Setting


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")


class SettingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Setting

    key = factory.Sequence(lambda n: f"setting_{n}")
    value = {"default": True}
    type = "json"
