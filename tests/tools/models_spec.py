"""Tests for tools app models."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from tools.models import Rentable, Rental, Tool, ToolReservation
from tests.core.factories import UserFactory
from tests.membership.factories import GuildFactory
from tests.tools.factories import (
    DocumentFactory,
    RentableFactory,
    RentalFactory,
    ToolFactory,
    ToolReservationFactory,
)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_tool():
    def it_has_str_representation():
        tool = ToolFactory(name="Band Saw")
        assert str(tool) == "Band Saw"

    def it_defaults_is_reservable_to_false():
        tool = ToolFactory()
        assert tool.is_reservable is False

    def it_defaults_is_rentable_to_false():
        tool = ToolFactory()
        assert tool.is_rentable is False

    def it_defaults_owner_type_to_org():
        tool = ToolFactory()
        assert tool.owner_type == Tool.OwnerType.ORG

    def it_can_be_set_as_reservable():
        tool = ToolFactory(is_reservable=True)
        assert tool.is_reservable is True

    def it_can_be_set_as_rentable():
        tool = ToolFactory(is_rentable=True)
        assert tool.is_rentable is True

    def it_belongs_to_a_guild():
        guild = GuildFactory(name="Woodworking Guild")
        tool = ToolFactory(guild=guild)
        tool.refresh_from_db()
        assert tool.guild == guild

    def it_allows_null_guild():
        tool = ToolFactory(guild=None)
        assert tool.guild is None

    def it_supports_all_owner_type_choices():
        assert Tool.OwnerType.GUILD == "guild"
        assert Tool.OwnerType.MEMBER == "member"
        assert Tool.OwnerType.ORG == "org"

    def it_guild_related_name_returns_tools():
        guild = GuildFactory(name="Metal Guild")
        tool = ToolFactory(guild=guild)
        assert tool in guild.tools.all()


# ---------------------------------------------------------------------------
# ToolReservation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_tool_reservation():
    def it_has_str_representation():
        tool = ToolFactory(name="Laser Cutter")
        user = UserFactory(username="alice")
        now = timezone.now()
        reservation = ToolReservationFactory(tool=tool, user=user, starts_at=now)
        expected = f"Laser Cutter - {user} ({now.date()})"
        assert str(reservation) == expected

    def it_defaults_status_to_active():
        reservation = ToolReservationFactory()
        assert reservation.status == ToolReservation.Status.ACTIVE

    def it_is_active_when_status_is_active():
        reservation = ToolReservationFactory(status=ToolReservation.Status.ACTIVE)
        assert reservation.is_active is True

    def it_is_not_active_when_status_is_completed():
        reservation = ToolReservationFactory(status=ToolReservation.Status.COMPLETED)
        assert reservation.is_active is False

    def it_is_not_active_when_status_is_cancelled():
        reservation = ToolReservationFactory(status=ToolReservation.Status.CANCELLED)
        assert reservation.is_active is False

    def it_belongs_to_a_tool():
        tool = ToolFactory(name="Drill Press")
        reservation = ToolReservationFactory(tool=tool)
        assert reservation.tool == tool

    def it_belongs_to_a_user():
        user = UserFactory(username="bob")
        reservation = ToolReservationFactory(user=user)
        assert reservation.user == user

    def it_supports_all_status_choices():
        assert ToolReservation.Status.ACTIVE == "active"
        assert ToolReservation.Status.COMPLETED == "completed"
        assert ToolReservation.Status.CANCELLED == "cancelled"


# ---------------------------------------------------------------------------
# Rentable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_rentable():
    def it_has_str_representation():
        tool = ToolFactory(name="3D Printer")
        rentable = RentableFactory(
            tool=tool, cost_per_period=Decimal("10.00"), rental_period=Rentable.RentalPeriod.HOURS
        )
        assert str(rentable) == "3D Printer - $10.00/hours"

    def it_has_formatted_cost_property():
        rentable = RentableFactory(cost_per_period=Decimal("25.00"), rental_period=Rentable.RentalPeriod.DAYS)
        assert rentable.formatted_cost == "$25.00/days"

    def it_is_available_when_active_with_no_rentals():
        rentable = RentableFactory(is_active=True)
        assert rentable.is_available() is True

    def it_is_not_available_when_inactive():
        rentable = RentableFactory(is_active=False)
        assert rentable.is_available() is False

    def it_is_not_available_when_has_active_rental():
        rentable = RentableFactory(is_active=True)
        RentalFactory(rentable=rentable, status=Rental.Status.ACTIVE)
        assert rentable.is_available() is False

    def it_is_available_when_all_rentals_are_returned():
        rentable = RentableFactory(is_active=True)
        RentalFactory(rentable=rentable, status=Rental.Status.RETURNED)
        assert rentable.is_available() is True

    def it_supports_all_rental_period_choices():
        assert Rentable.RentalPeriod.HOURS == "hours"
        assert Rentable.RentalPeriod.DAYS == "days"
        assert Rentable.RentalPeriod.WEEKS == "weeks"


# ---------------------------------------------------------------------------
# Rental
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_rental():
    def it_has_str_representation():
        tool = ToolFactory(name="Welding Machine")
        rentable = RentableFactory(tool=tool)
        user = UserFactory(username="charlie")
        rental = RentalFactory(rentable=rentable, user=user, status=Rental.Status.ACTIVE)
        assert str(rental) == f"Welding Machine - {user} (active)"

    def it_defaults_status_to_active():
        rental = RentalFactory()
        assert rental.status == Rental.Status.ACTIVE

    def it_is_active_when_status_is_active():
        rental = RentalFactory(status=Rental.Status.ACTIVE)
        assert rental.is_active is True

    def it_is_not_active_when_returned():
        rental = RentalFactory(status=Rental.Status.RETURNED)
        assert rental.is_active is False

    def it_is_overdue_when_active_and_past_due():
        past_due = timezone.now() - timedelta(hours=1)
        rental = RentalFactory(status=Rental.Status.ACTIVE, due_at=past_due)
        assert rental.is_overdue is True

    def it_is_not_overdue_when_active_and_not_yet_due():
        future_due = timezone.now() + timedelta(days=7)
        rental = RentalFactory(status=Rental.Status.ACTIVE, due_at=future_due)
        assert rental.is_overdue is False

    def it_is_not_overdue_when_returned():
        past_due = timezone.now() - timedelta(hours=1)
        rental = RentalFactory(status=Rental.Status.RETURNED, due_at=past_due)
        assert rental.is_overdue is False

    def it_is_returned_when_status_is_returned():
        rental = RentalFactory(status=Rental.Status.RETURNED)
        assert rental.is_returned is True

    def it_is_not_returned_when_active():
        rental = RentalFactory(status=Rental.Status.ACTIVE)
        assert rental.is_returned is False

    def it_mark_as_returned_updates_status_and_returned_at():
        rental = RentalFactory(status=Rental.Status.ACTIVE)
        assert rental.returned_at is None
        rental.mark_as_returned()
        rental.refresh_from_db()
        assert rental.status == Rental.Status.RETURNED
        assert rental.returned_at is not None

    def it_supports_all_status_choices():
        assert Rental.Status.ACTIVE == "active"
        assert Rental.Status.RETURNED == "returned"
        assert Rental.Status.OVERDUE == "overdue"

    def describe_calculate_rental_cost():
        def it_calculates_cost_for_hourly_rental():
            now = timezone.now()
            checked_out = now - timedelta(hours=3)
            rentable = RentableFactory(rental_period=Rentable.RentalPeriod.HOURS, cost_per_period=Decimal("10.00"))
            rental = RentalFactory(rentable=rentable, checked_out_at=checked_out, returned_at=now)
            cost = rental.calculate_rental_cost()
            assert cost == Decimal("30.00")

        def it_calculates_cost_for_daily_rental():
            now = timezone.now()
            checked_out = now - timedelta(hours=48)
            rentable = RentableFactory(rental_period=Rentable.RentalPeriod.DAYS, cost_per_period=Decimal("25.00"))
            rental = RentalFactory(rentable=rentable, checked_out_at=checked_out, returned_at=now)
            cost = rental.calculate_rental_cost()
            assert cost == Decimal("50.00")

        def it_calculates_cost_for_weekly_rental():
            now = timezone.now()
            checked_out = now - timedelta(days=14)
            rentable = RentableFactory(rental_period=Rentable.RentalPeriod.WEEKS, cost_per_period=Decimal("100.00"))
            rental = RentalFactory(rentable=rentable, checked_out_at=checked_out, returned_at=now)
            cost = rental.calculate_rental_cost()
            assert cost == Decimal("200.00")

        def it_rounds_up_to_nearest_whole_period():
            now = timezone.now()
            # 1.5 hours — should round up to 2 periods
            checked_out = now - timedelta(minutes=90)
            rentable = RentableFactory(rental_period=Rentable.RentalPeriod.HOURS, cost_per_period=Decimal("10.00"))
            rental = RentalFactory(rentable=rentable, checked_out_at=checked_out, returned_at=now)
            cost = rental.calculate_rental_cost()
            assert cost == Decimal("20.00")

        def it_uses_current_time_when_not_returned():
            now = timezone.now()
            checked_out = now - timedelta(hours=2)
            rentable = RentableFactory(rental_period=Rentable.RentalPeriod.HOURS, cost_per_period=Decimal("10.00"))
            rental = RentalFactory(rentable=rentable, checked_out_at=checked_out, returned_at=None)
            cost = rental.calculate_rental_cost()
            # At least 2 periods for 2 hours
            assert cost >= Decimal("20.00")


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_document():
    def it_has_str_representation():
        doc = DocumentFactory(name="Safety Manual")
        assert str(doc) == "Safety Manual"

    def it_has_generic_fk_pointing_to_tool():
        tool = ToolFactory(name="Router Table")
        ct = ContentType.objects.get_for_model(Tool)
        doc = DocumentFactory(name="Router Manual", content_type=ct, object_id=tool.pk)
        assert doc.documentable == tool

    def it_links_uploaded_by_user():
        user = UserFactory(username="dana")
        doc = DocumentFactory(uploaded_by=user)
        assert doc.uploaded_by == user

    def it_allows_null_uploaded_by():
        doc = DocumentFactory(uploaded_by=None)
        assert doc.uploaded_by is None
