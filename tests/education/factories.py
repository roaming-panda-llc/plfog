from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from education.models import (
    ClassDiscountCode,
    ClassImage,
    ClassSession,
    MakerClass,
    Orientation,
    ScheduledOrientation,
    Student,
)
from tests.core.factories import UserFactory
from tests.membership.factories import GuildFactory


class ClassDiscountCodeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClassDiscountCode

    code = factory.Sequence(lambda n: f"DISCOUNT{n}")
    discount_type = ClassDiscountCode.DiscountType.PERCENTAGE
    discount_value = Decimal("10.00")
    is_active = True


class MakerClassFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MakerClass

    name = factory.Sequence(lambda n: f"Class {n}")
    price = Decimal("50.00")
    status = MakerClass.Status.DRAFT
    guild = factory.SubFactory(GuildFactory)


class ClassSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClassSession

    maker_class = factory.SubFactory(MakerClassFactory)
    starts_at = factory.LazyFunction(timezone.now)
    ends_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=2))


class ClassImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClassImage

    maker_class = factory.SubFactory(MakerClassFactory)
    image_path = factory.django.ImageField()
    sort_order = factory.Sequence(lambda n: n)


class StudentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Student

    maker_class = factory.SubFactory(MakerClassFactory)
    name = factory.Faker("name")
    email = factory.Sequence(lambda n: f"student{n}@example.com")
    amount_paid = Decimal("50.00")


class OrientationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Orientation

    guild = factory.SubFactory(GuildFactory)
    name = factory.Sequence(lambda n: f"Orientation {n}")
    duration_minutes = 60
    price = Decimal("25.00")
    is_active = True


class ScheduledOrientationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScheduledOrientation

    orientation = factory.SubFactory(OrientationFactory)
    user = factory.SubFactory(UserFactory)
    scheduled_at = factory.LazyFunction(timezone.now)
    status = ScheduledOrientation.Status.PENDING
