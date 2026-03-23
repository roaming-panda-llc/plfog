"""Seed the default MembershipPlan and backfill Member records for existing users."""

from __future__ import annotations

from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def create_default_plan_and_backfill_members(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    MembershipPlan = apps.get_model("membership", "MembershipPlan")
    Member = apps.get_model("membership", "Member")
    User = apps.get_model("auth", "User")

    plan, _ = MembershipPlan.objects.get_or_create(
        name="Standard Membership",
        defaults={"monthly_price": Decimal("150.00")},
    )

    users_without_member = User.objects.filter(member__isnull=True)
    for user in users_without_member:
        Member.objects.create(
            user=user,
            full_legal_name=f"{user.first_name} {user.last_name}".strip() or user.username,
            email=user.email or "",
            membership_plan=plan,
            status="active",
        )


def remove_default_plan_and_backfilled_members(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    MembershipPlan = apps.get_model("membership", "MembershipPlan")
    Member = apps.get_model("membership", "Member")

    plan = MembershipPlan.objects.filter(name="Standard Membership").first()
    if plan:
        Member.objects.filter(membership_plan=plan).delete()
        plan.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("membership", "0010_alter_guild_is_active"),
    ]

    operations = [
        migrations.RunPython(
            create_default_plan_and_backfill_members,
            remove_default_plan_and_backfilled_members,
        ),
    ]
