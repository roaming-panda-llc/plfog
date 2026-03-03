"""Tests for MemberSchedule and ScheduleBlock models."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from membership.models import MemberSchedule, ScheduleBlock
from tests.membership.factories import MemberScheduleFactory, ScheduleBlockFactory
from tests.core.factories import UserFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# MemberSchedule
# ---------------------------------------------------------------------------


def describe_MemberSchedule():
    def it_links_to_user():
        user = UserFactory()
        schedule = MemberScheduleFactory(user=user)
        assert schedule.user == user

    def it_has_str_representation():
        user = UserFactory(username="scheduleuser")
        schedule = MemberScheduleFactory(user=user)
        assert str(schedule) == "Schedule for scheduleuser"

    def it_has_created_at():
        schedule = MemberScheduleFactory()
        assert schedule.created_at is not None

    def it_allows_blank_notes():
        schedule = MemberScheduleFactory(notes="")
        assert schedule.notes == ""

    def it_stores_notes():
        schedule = MemberScheduleFactory(notes="Available mornings only.")
        schedule.refresh_from_db()
        assert schedule.notes == "Available mornings only."

    def it_is_one_to_one_with_user():
        user = UserFactory()
        MemberScheduleFactory(user=user)
        assert MemberSchedule.objects.filter(user=user).count() == 1


# ---------------------------------------------------------------------------
# ScheduleBlock
# ---------------------------------------------------------------------------


def describe_ScheduleBlock():
    def it_has_day_name_property():
        block = ScheduleBlockFactory(day_of_week=1)
        assert block.day_name == "Monday"

    def it_has_day_name_for_sunday():
        block = ScheduleBlockFactory(day_of_week=0)
        assert block.day_name == "Sunday"

    def it_has_day_name_for_saturday():
        block = ScheduleBlockFactory(day_of_week=6)
        assert block.day_name == "Saturday"

    def it_has_str_representation():
        block = ScheduleBlockFactory(day_of_week=1, start_time="09:00", end_time="17:00")
        assert "Monday" in str(block)
        assert "09:00" in str(block)
        assert "17:00" in str(block)

    def it_belongs_to_member_schedule():
        schedule = MemberScheduleFactory()
        block = ScheduleBlockFactory(member_schedule=schedule)
        assert block.member_schedule == schedule

    def it_defaults_is_recurring_to_true():
        block = ScheduleBlockFactory()
        assert block.is_recurring is True

    def it_can_set_is_recurring_to_false():
        block = ScheduleBlockFactory(is_recurring=False)
        assert block.is_recurring is False

    def it_stores_start_and_end_time():
        block = ScheduleBlockFactory(start_time="08:30", end_time="12:00")
        block.refresh_from_db()
        assert str(block.start_time) == "08:30:00"
        assert str(block.end_time) == "12:00:00"

    def it_allows_multiple_blocks_per_schedule():
        schedule = MemberScheduleFactory()
        block_a = ScheduleBlockFactory(member_schedule=schedule, day_of_week=1, start_time="09:00", end_time="12:00")
        block_b = ScheduleBlockFactory(member_schedule=schedule, day_of_week=3, start_time="14:00", end_time="17:00")
        assert ScheduleBlock.objects.filter(member_schedule=schedule).count() == 2
        assert block_a.pk != block_b.pk


# ---------------------------------------------------------------------------
# Admin changelist HTTP tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="admin-schedule-test",
        password="admin-test-pw",
        email="admin-schedule@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


def describe_admin_member_schedule_views():
    def it_loads_changelist(admin_client):
        MemberScheduleFactory()
        resp = admin_client.get("/admin/membership/memberschedule/")
        assert resp.status_code == 200


def describe_admin_schedule_block_views():
    def it_loads_changelist(admin_client):
        ScheduleBlockFactory()
        resp = admin_client.get("/admin/membership/scheduleblock/")
        assert resp.status_code == 200
