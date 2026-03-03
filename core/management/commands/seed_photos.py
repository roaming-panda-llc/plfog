"""Download stock photos for guild cover images using asset-cli."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand

from membership.models import Guild

ASSET_CLI = Path.home() / "Code" / "hexagonstorms" / "asset-cli" / "assets"

GUILD_SEARCH_TERMS = {
    "Art Framing": "picture framing workshop",
    "Ceramics": "pottery wheel studio",
    "Events": "community event makerspace",
    "Gardeners": "community garden raised beds",
    "Jewelry": "jewelry making bench",
    "Leather": "leather crafting workshop",
    "Metalworkers": "welding sparks workshop",
    "Glass": "glassblowing studio",
    "Prison Outreach": "art class community",
    "Tech": "electronics soldering lab",
    "Textiles": "sewing machine studio",
    "Visual Arts": "painting studio easels",
    "Woodworkers": "woodworking shop tools",
    "Writers": "writing group workshop",
}


class Command(BaseCommand):
    help = "Download stock photos for guild cover images using asset-cli"

    def handle(self, *args: object, **options: object) -> None:
        if not ASSET_CLI.exists():
            self.stderr.write(self.style.WARNING(f"asset-cli not found at {ASSET_CLI}. Skipping photo downloads."))
            return

        media_dir = Path("media/guilds")
        media_dir.mkdir(parents=True, exist_ok=True)

        for guild in Guild.objects.filter(is_active=True).order_by("name"):
            search_term = GUILD_SEARCH_TERMS.get(guild.name)
            if not search_term:
                self.stdout.write(f"  No search term for {guild.name}, skipping")
                continue

            self.stdout.write(f'  Searching for {guild.name}: "{search_term}"')

            try:
                subprocess.run(
                    [str(ASSET_CLI), "search", search_term, "--landscape", "--per-page", "1"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    [str(ASSET_CLI), "download", "1", str(media_dir), "--medium"],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                downloaded_files = list(media_dir.glob("*"))
                if downloaded_files:
                    latest = max(downloaded_files, key=os.path.getmtime)
                    new_name = media_dir / f"{guild.slug}.jpg"
                    latest.rename(new_name)
                    guild.cover_image = f"guilds/{guild.slug}.jpg"
                    guild.save()
                    self.stdout.write(self.style.SUCCESS(f"  {guild.name} -> {new_name}"))

            except subprocess.CalledProcessError as e:
                self.stderr.write(self.style.WARNING(f"  {guild.name}: {e}"))
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"  {guild.name}: {e}"))
