"""Download the production database into local PostgreSQL.

Usage:
    python manage.py pull_prod_db          # interactive confirmation
    python manage.py pull_prod_db --no-input  # skip confirmation (CI/scripts)

Requires:
    - PROD_DATABASE_URL env var (Render external connection string)
    - Local DATABASE_URL pointing to PostgreSQL (not SQLite)
    - pg_dump and psql available on PATH
    - DEBUG=True (refuses to run in production)
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Download the production database into your local PostgreSQL."

    def add_arguments(self, parser: object) -> None:
        parser.add_argument("--no-input", action="store_true", help="Skip confirmation prompt")

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            raise CommandError("Refusing to run: DEBUG is not True.")

        prod_url = os.environ.get("PROD_DATABASE_URL", "")
        if not prod_url:
            raise CommandError("PROD_DATABASE_URL is not set. Add it to your .env file.")

        db_engine = settings.DATABASES["default"].get("ENGINE", "")
        if "sqlite" in db_engine:
            raise CommandError(
                "Your local database must be PostgreSQL, not SQLite. "
                "Set DATABASE_URL in your .env and run 'make db-up'."
            )

        local_url = os.environ.get("DATABASE_URL", "")

        if not options["no_input"]:
            confirm = input("This will REPLACE your local database with production data. Continue? [y/N] ")
            if confirm.lower() != "y":
                self.stdout.write("Aborted.")
                return

        self.stdout.write(self.style.NOTICE("Dumping production database..."))

        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as dump_file:
            dump_path = dump_file.name

        try:
            result = subprocess.run(
                ["pg_dump", "--no-owner", "--no-acl", "--clean", "--if-exists", "-f", dump_path, prod_url],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise CommandError(f"pg_dump failed: {result.stderr}")

            self.stdout.write(self.style.NOTICE("Loading into local database..."))

            result = subprocess.run(
                ["psql", "-f", dump_path, local_url],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise CommandError(f"psql failed: {result.stderr}")

        finally:
            os.unlink(dump_path)

        self.stdout.write(self.style.NOTICE("Running migrations..."))
        call_command("migrate", verbosity=1, stdout=self.stdout)

        self.stdout.write(self.style.SUCCESS("Done — loaded production data into local database."))
