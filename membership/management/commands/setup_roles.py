from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


# Map role names to their permission codenames.
# Only includes permissions for models that exist in this branch (membership app + Django auth).
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super-admin": [],  # Gets all permissions
    "guild-manager": [
        "view_guild",
        "change_guild",
        "add_guild",
        "delete_guild",
        "view_guildmembership",
        "change_guildmembership",
        "add_guildmembership",
        "delete_guildmembership",
        "view_guilddocument",
        "change_guilddocument",
        "add_guilddocument",
        "delete_guilddocument",
        "view_guildwishlistitem",
        "change_guildwishlistitem",
        "add_guildwishlistitem",
        "delete_guildwishlistitem",
        "view_guildvote",
        "change_guildvote",
    ],
    "class-manager": [],
    "orientation-manager": [],
    "accountant": [],
    "tour-guide": [],
    "membership-manager": [
        "view_member",
        "change_member",
        "add_member",
        "view_membershipplan",
        "change_membershipplan",
        "view_space",
        "change_space",
        "view_lease",
        "change_lease",
        "add_lease",
        "delete_lease",
        "view_memberschedule",
        "change_memberschedule",
        "view_scheduleblock",
        "change_scheduleblock",
        "add_scheduleblock",
        "delete_scheduleblock",
    ],
    "guild-lead": [
        "view_guild",
        "change_guild",
        "view_guildmembership",
        "change_guildmembership",
        "add_guildmembership",
        "view_guilddocument",
        "change_guilddocument",
        "add_guilddocument",
        "view_guildwishlistitem",
        "change_guildwishlistitem",
        "add_guildwishlistitem",
    ],
    "orienter": [],
    "teacher": [],
}


class Command(BaseCommand):
    help = "Create permission groups and assign permissions for all roles"

    def handle(self, *args: object, **options: object) -> None:
        all_permissions = Permission.objects.all()

        for role_name, perm_codenames in ROLE_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=role_name)
            action = "Created" if created else "Updated"

            if role_name == "super-admin":
                group.permissions.set(all_permissions)
            else:
                perms = Permission.objects.filter(codename__in=perm_codenames)
                group.permissions.set(perms)

            self.stdout.write(
                self.style.SUCCESS(f"{action} group '{role_name}' with {group.permissions.count()} permissions")
            )
