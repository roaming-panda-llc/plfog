from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import factory
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from tests.core.factories import UserFactory
from tests.membership.factories import GuildFactory
from tools.models import Document, Rentable, Rental, Tool, ToolReservation


class ToolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tool

    name = factory.Sequence(lambda n: f"Tool {n}")
    guild = factory.SubFactory(GuildFactory)
    owner_type = Tool.OwnerType.ORG


class ToolReservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ToolReservation

    tool = factory.SubFactory(ToolFactory)
    user = factory.SubFactory(UserFactory)
    starts_at = factory.LazyFunction(timezone.now)
    ends_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=2))
    status = ToolReservation.Status.ACTIVE


class RentableFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Rentable

    tool = factory.SubFactory(ToolFactory)
    rental_period = Rentable.RentalPeriod.DAYS
    cost_per_period = Decimal("25.00")
    is_active = True


class RentalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Rental

    rentable = factory.SubFactory(RentableFactory)
    user = factory.SubFactory(UserFactory)
    checked_out_at = factory.LazyFunction(timezone.now)
    due_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    status = Rental.Status.ACTIVE


class DocumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Document

    name = factory.Sequence(lambda n: f"Document {n}")
    file_path = factory.django.FileField(filename="test.pdf")
    uploaded_by = factory.SubFactory(UserFactory)
    content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(Tool))
    object_id = factory.LazyAttribute(lambda o: ToolFactory().pk)  # type: ignore[attr-defined]
