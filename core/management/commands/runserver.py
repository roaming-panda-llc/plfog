"""Override runserver to auto-apply pending migrations in DEBUG mode.

Prevents the \"no such column\" class of errors that bite local dev when
switching branches or pulling new migrations.
"""

from __future__ import annotations

import sys

from django.conf import settings
from django.core.management import call_command
from django.core.management.commands.runserver import Command as BaseRunserver


class Command(BaseRunserver):
    def handle(self, *args: object, **options: object) -> None:
        if settings.DEBUG:
            self.stdout.write(self.style.NOTICE("[dev] Checking for unapplied migrations…"))
            try:
                call_command("migrate", "--check", stdout=open("/dev/null", "w"))
                self.stdout.write(self.style.SUCCESS("[dev] All migrations applied."))
            except SystemExit:
                self.stdout.write(self.style.WARNING("[dev] Unapplied migrations detected — running migrate…"))
                call_command("migrate", verbosity=1, stdout=sys.stdout)
        super().handle(*args, **options)
