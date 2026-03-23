"""Management command to create a funding snapshot from current vote preferences."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from membership.models import FundingSnapshot


class Command(BaseCommand):
    """Create a FundingSnapshot from the current VotePreferences."""

    help = "Take a funding snapshot from current vote preferences."

    def handle(self, *args: object, **options: object) -> None:
        """Execute the snapshot command."""
        snapshot = FundingSnapshot.take()

        if snapshot is None:
            self.stdout.write("No vote preferences found. Skipping snapshot.")
            return

        self.stdout.write(
            f"Snapshot created: {snapshot.cycle_label} — {snapshot.contributor_count} contributor(s) — pool ${snapshot.funding_pool}"
        )
