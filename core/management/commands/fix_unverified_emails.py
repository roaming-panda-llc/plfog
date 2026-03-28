"""One-shot command to verify all unverified EmailAddress records.

With ACCOUNT_EMAIL_VERIFICATION = "none", allauth should not create unverified
records going forward. This command fixes existing ones that block passwordless login.

Usage:
    python manage.py fix_unverified_emails --dry-run   # preview
    python manage.py fix_unverified_emails              # fix
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    """Mark all unverified EmailAddress records as verified."""

    help = "Mark all unverified allauth EmailAddress records as verified."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Preview without making changes.")

    def handle(self, *args: Any, **options: Any) -> None:
        from allauth.account.models import EmailAddress

        dry_run = options["dry_run"]
        unverified = EmailAddress.objects.filter(verified=False)
        count = unverified.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No unverified EmailAddress records found."))
            return

        for ea in unverified:
            self.stdout.write(f"  {ea.email} (user_id={ea.user_id}, primary={ea.primary})")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\nDRY RUN — {count} records would be marked verified."))
        else:
            updated = unverified.update(verified=True)
            self.stdout.write(self.style.SUCCESS(f"\nMarked {updated} EmailAddress records as verified."))
