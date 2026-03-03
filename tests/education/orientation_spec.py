"""BDD-style tests for Orientation and ScheduledOrientation models and admin."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client

from education.admin import OrientationAdmin, ScheduledOrientationAdmin, ScheduledOrientationInline
from education.models import Orientation, ScheduledOrientation
from tests.core.factories import UserFactory
from tests.education.factories import OrientationFactory, ScheduledOrientationFactory
from tests.membership.factories import GuildFactory
from tests.tools.factories import ToolFactory

User = get_user_model()


# ---------------------------------------------------------------------------
# Orientation model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_orientation():
    def it_has_str_representation():
        orientation = OrientationFactory(name="Laser Cutter Orientation")
        assert str(orientation) == "Laser Cutter Orientation"

    def it_belongs_to_a_guild():
        guild = GuildFactory(name="Fabrication Guild")
        orientation = OrientationFactory(guild=guild)
        orientation.refresh_from_db()
        assert orientation.guild == guild

    def it_defaults_is_active_to_true():
        orientation = OrientationFactory()
        assert orientation.is_active is True

    def it_can_be_set_inactive():
        orientation = OrientationFactory(is_active=False)
        assert orientation.is_active is False

    def it_formats_price_correctly():
        orientation = OrientationFactory(price=Decimal("25.00"))
        assert orientation.formatted_price == "$25.00"

    def it_formats_price_with_cents():
        orientation = OrientationFactory(price=Decimal("12.50"))
        assert orientation.formatted_price == "$12.50"

    def it_stores_duration_minutes():
        orientation = OrientationFactory(duration_minutes=90)
        orientation.refresh_from_db()
        assert orientation.duration_minutes == 90

    def it_supports_m2m_tools():
        orientation = OrientationFactory()
        tool = ToolFactory()
        orientation.tools.add(tool)
        assert tool in orientation.tools.all()

    def it_supports_m2m_orienters():
        orientation = OrientationFactory()
        user = UserFactory()
        orientation.orienters.add(user)
        assert user in orientation.orienters.all()

    def it_allows_blank_tools_m2m():
        orientation = OrientationFactory()
        assert orientation.tools.count() == 0

    def it_allows_blank_orienters_m2m():
        orientation = OrientationFactory()
        assert orientation.orienters.count() == 0

    def it_orders_by_name():
        OrientationFactory(name="Z Orientation")
        OrientationFactory(name="A Orientation")
        names = list(Orientation.objects.values_list("name", flat=True))
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# ScheduledOrientation model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_scheduled_orientation():
    def it_has_str_representation():
        user = UserFactory(username="testuser")
        orientation = OrientationFactory(name="Wood Shop Safety")
        scheduled = ScheduledOrientationFactory(
            orientation=orientation,
            user=user,
            status=ScheduledOrientation.Status.PENDING,
        )
        assert str(scheduled) == f"Wood Shop Safety - {user} (pending)"

    def it_defaults_status_to_pending():
        scheduled = ScheduledOrientationFactory()
        assert scheduled.status == ScheduledOrientation.Status.PENDING

    def it_is_pending_when_status_is_pending():
        scheduled = ScheduledOrientationFactory(status=ScheduledOrientation.Status.PENDING)
        assert scheduled.is_pending is True
        assert scheduled.is_claimed is False
        assert scheduled.is_completed is False

    def it_is_claimed_when_status_is_claimed():
        scheduled = ScheduledOrientationFactory(status=ScheduledOrientation.Status.CLAIMED)
        assert scheduled.is_claimed is True
        assert scheduled.is_pending is False
        assert scheduled.is_completed is False

    def it_is_completed_when_status_is_completed():
        scheduled = ScheduledOrientationFactory(status=ScheduledOrientation.Status.COMPLETED)
        assert scheduled.is_completed is True
        assert scheduled.is_pending is False
        assert scheduled.is_claimed is False

    def it_belongs_to_an_orientation():
        orientation = OrientationFactory(name="CNC Router Orientation")
        scheduled = ScheduledOrientationFactory(orientation=orientation)
        scheduled.refresh_from_db()
        assert scheduled.orientation == orientation

    def it_has_a_user_fk():
        user = UserFactory()
        scheduled = ScheduledOrientationFactory(user=user)
        scheduled.refresh_from_db()
        assert scheduled.user == user

    def it_has_nullable_claimed_by_fk():
        scheduled = ScheduledOrientationFactory()
        assert scheduled.claimed_by is None

    def it_allows_claimed_by_to_be_set():
        claimer = UserFactory()
        scheduled = ScheduledOrientationFactory(claimed_by=claimer)
        scheduled.refresh_from_db()
        assert scheduled.claimed_by == claimer

    def it_has_nullable_order_fk():
        scheduled = ScheduledOrientationFactory()
        assert scheduled.order is None

    def it_is_not_completed_when_cancelled():
        scheduled = ScheduledOrientationFactory(status=ScheduledOrientation.Status.CANCELLED)
        assert scheduled.is_completed is False
        assert scheduled.is_pending is False
        assert scheduled.is_claimed is False


# ---------------------------------------------------------------------------
# Admin registration
# ---------------------------------------------------------------------------


def describe_admin_registration():
    def it_registers_orientation():
        assert Orientation in admin.site._registry
        assert isinstance(admin.site._registry[Orientation], OrientationAdmin)

    def it_registers_scheduled_orientation():
        assert ScheduledOrientation in admin.site._registry
        assert isinstance(admin.site._registry[ScheduledOrientation], ScheduledOrientationAdmin)


def describe_orientation_admin():
    def it_has_expected_list_display():
        orientation_admin = admin.site._registry[Orientation]
        assert orientation_admin.list_display == ["name", "guild", "price", "duration_minutes", "is_active"]

    def it_has_expected_list_filter():
        orientation_admin = admin.site._registry[Orientation]
        assert orientation_admin.list_filter == ["is_active", "guild"]

    def it_has_expected_search_fields():
        orientation_admin = admin.site._registry[Orientation]
        assert orientation_admin.search_fields == ["name"]

    def it_has_scheduled_orientation_inline():
        orientation_admin = admin.site._registry[Orientation]
        assert ScheduledOrientationInline in orientation_admin.inlines


def describe_scheduled_orientation_admin():
    def it_has_expected_list_display():
        so_admin = admin.site._registry[ScheduledOrientation]
        assert so_admin.list_display == ["orientation", "user", "scheduled_at", "claimed_by", "status"]

    def it_has_expected_list_filter():
        so_admin = admin.site._registry[ScheduledOrientation]
        assert so_admin.list_filter == ["status"]

    def it_has_expected_search_fields():
        so_admin = admin.site._registry[ScheduledOrientation]
        assert so_admin.search_fields == ["orientation__name", "user__username"]


# ---------------------------------------------------------------------------
# Admin changelist HTTP tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="edu-orientation-admin",
        password="edu-orientation-pw",
        email="edu-orientation@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def describe_orientation_admin_changelist():
    def it_loads_with_200(admin_client):
        OrientationFactory(name="Changelist Orientation")
        resp = admin_client.get("/admin/education/orientation/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_scheduled_orientation_admin_changelist():
    def it_loads_with_200(admin_client):
        ScheduledOrientationFactory()
        resp = admin_client.get("/admin/education/scheduledorientation/")
        assert resp.status_code == 200
