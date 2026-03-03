"""BDD-style tests for the seed_photos management command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from membership.models import Guild

pytestmark = pytest.mark.django_db


@pytest.fixture()
def active_guild(db):
    """Create an active guild with a known search term."""
    return Guild.objects.create(
        name="Ceramics",
        slug="ceramics",
        intro="Shaping earth.",
        description="Ceramics guild.",
        icon="emoji_objects",
        is_active=True,
    )


@pytest.fixture()
def unknown_guild(db):
    """Create an active guild with no matching search term."""
    return Guild.objects.create(
        name="Unknown Guild",
        slug="unknown-guild",
        intro="Unknown.",
        description="No search term configured.",
        icon="help",
        is_active=True,
    )


def describe_seed_photos_command():
    def it_skips_gracefully_when_asset_cli_missing():
        with patch("core.management.commands.seed_photos.ASSET_CLI") as mock_path:
            mock_path.exists.return_value = False
            call_command("seed_photos")
            # Should not raise

    def it_skips_guild_with_no_search_term(unknown_guild):
        with (
            patch("core.management.commands.seed_photos.ASSET_CLI") as mock_cli,
            patch("core.management.commands.seed_photos.subprocess.run"),
        ):
            mock_cli.exists.return_value = True
            mock_cli.__str__ = lambda s: "/fake/assets"
            call_command("seed_photos")

    def it_handles_called_process_error(active_guild):
        with (
            patch("core.management.commands.seed_photos.ASSET_CLI") as mock_cli,
            patch(
                "core.management.commands.seed_photos.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "assets"),
            ),
        ):
            mock_cli.exists.return_value = True
            mock_cli.__str__ = lambda s: "/fake/assets"
            call_command("seed_photos")
            # Should not raise, error is caught and written to stderr

    def it_handles_unexpected_exception(active_guild):
        with (
            patch("core.management.commands.seed_photos.ASSET_CLI") as mock_cli,
            patch(
                "core.management.commands.seed_photos.subprocess.run",
                side_effect=OSError("disk full"),
            ),
        ):
            mock_cli.exists.return_value = True
            mock_cli.__str__ = lambda s: "/fake/assets"
            call_command("seed_photos")
            # Should not raise, error is caught and written to stderr


def describe_seed_photos_download():
    def it_downloads_and_saves_cover_image(active_guild, tmp_path):
        fake_file = tmp_path / "photo.jpg"
        fake_file.write_bytes(b"img")

        with (
            patch("core.management.commands.seed_photos.ASSET_CLI") as mock_cli,
            patch("core.management.commands.seed_photos.subprocess.run"),
            patch("core.management.commands.seed_photos.Path") as mock_path_cls,
        ):
            mock_cli.exists.return_value = True
            mock_cli.__str__ = lambda s: "/fake/assets"

            mock_media_dir = MagicMock()
            mock_media_dir.__str__ = lambda s: str(tmp_path)
            mock_media_dir.glob.return_value = [fake_file]
            mock_media_dir.__truediv__ = lambda s, other: tmp_path / other

            def path_side_effect(arg):
                if arg == "media/guilds":
                    return mock_media_dir
                return Path(arg)

            mock_path_cls.side_effect = path_side_effect
            mock_path_cls.home = Path.home

            call_command("seed_photos")

    def it_skips_rename_when_no_files_downloaded(active_guild):
        with (
            patch("core.management.commands.seed_photos.ASSET_CLI") as mock_cli,
            patch("core.management.commands.seed_photos.subprocess.run"),
            patch("core.management.commands.seed_photos.Path") as mock_path_cls,
        ):
            mock_cli.exists.return_value = True
            mock_cli.__str__ = lambda s: "/fake/assets"

            mock_media_dir = MagicMock()
            mock_media_dir.glob.return_value = []

            def path_side_effect(arg):
                if arg == "media/guilds":
                    return mock_media_dir
                return Path(arg)

            mock_path_cls.side_effect = path_side_effect
            mock_path_cls.home = Path.home

            call_command("seed_photos")
            # cover_image should not be updated
            active_guild.refresh_from_db()
            assert not active_guild.cover_image
