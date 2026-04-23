"""Send upcoming-class reminder emails. Scheduled every ~15 minutes."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from classes.tasks import send_due_class_reminders


class Command(BaseCommand):
    help = "Send reminder emails for class sessions starting soon."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--window-minutes",
            type=int,
            default=15,
            help="Width of the 'starting soon' window in minutes (default: 15).",
        )

    def handle(self, *args, **options) -> None:
        window = options["window_minutes"]
        sent = send_due_class_reminders(window_minutes=window)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder email(s)."))
