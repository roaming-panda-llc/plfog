"""BDD-style tests for the setup_roles management command."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def describe_setup_roles_command():
    def it_creates_all_ten_groups():
        call_command("setup_roles")
        assert Group.objects.count() == 10

    def it_creates_super_admin_group():
        call_command("setup_roles")
        group = Group.objects.get(name="super-admin")
        assert group.permissions.count() == Permission.objects.count()

    def it_creates_guild_manager_group():
        call_command("setup_roles")
        group = Group.objects.get(name="guild-manager")
        assert group.permissions.count() > 0
        assert group.permissions.filter(codename="change_guild").exists()

    def it_creates_membership_manager_group():
        call_command("setup_roles")
        group = Group.objects.get(name="membership-manager")
        assert group.permissions.filter(codename="change_member").exists()

    def it_creates_guild_lead_group():
        call_command("setup_roles")
        group = Group.objects.get(name="guild-lead")
        assert group.permissions.filter(codename="change_guild").exists()
        # guild-lead should NOT have delete_guild
        assert not group.permissions.filter(codename="delete_guild").exists()

    def it_is_idempotent():
        call_command("setup_roles")
        call_command("setup_roles")
        assert Group.objects.count() == 10


def describe_setup_roles_placeholder_groups():
    """Future-app groups are created now but have no permissions until those apps are installed."""

    def it_creates_class_manager_group():
        call_command("setup_roles")
        # class-manager exists but has no permissions in this branch (education app not installed)
        group = Group.objects.get(name="class-manager")
        assert group is not None

    def it_creates_orientation_manager_group():
        call_command("setup_roles")
        # orientation-manager exists but has no permissions in this branch
        group = Group.objects.get(name="orientation-manager")
        assert group is not None

    def it_creates_accountant_group():
        call_command("setup_roles")
        # accountant exists but has no permissions in this branch (billing app not installed)
        group = Group.objects.get(name="accountant")
        assert group is not None

    def it_creates_tour_guide_group():
        call_command("setup_roles")
        # tour-guide exists but has no permissions in this branch (outreach app not installed)
        group = Group.objects.get(name="tour-guide")
        assert group is not None

    def it_creates_orienter_group():
        call_command("setup_roles")
        # orienter exists but has no permissions in this branch (outreach app not installed)
        group = Group.objects.get(name="orienter")
        assert group is not None

    def it_creates_teacher_group():
        call_command("setup_roles")
        # teacher exists but has no permissions in this branch (education app not installed)
        group = Group.objects.get(name="teacher")
        assert group is not None
