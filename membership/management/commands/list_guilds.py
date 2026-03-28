"""Management command to list all guilds in the database."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from membership.models import Guild


class Command(BaseCommand):
    """Print all Guild names, one per line."""

    help = "List all guilds in the database."

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        guilds = Guild.objects.all().order_by("name")
        count = guilds.count()
        self.stdout.write(f"Total guilds: {count}")
        for guild in guilds:
            self.stdout.write(f"  - {guild.name} (active={guild.is_active})")
