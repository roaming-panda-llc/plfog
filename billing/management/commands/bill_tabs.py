"""Management command to run the billing cycle — charge all pending tab entries."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from billing.models import BillingSettings, StripeAccount, Tab, TabCharge, TabEntry
from billing.notifications import notify_admin_charge_failed, send_receipt

logger = logging.getLogger(__name__)

# Advisory lock ID — arbitrary but unique to this command
ADVISORY_LOCK_ID = 889_201


class Command(BaseCommand):
    """Run the billing cycle: charge pending tab entries via Stripe."""

    help = "Process pending tab entries and charge members via Stripe."

    def add_arguments(self, parser: object) -> None:
        """Add --force flag to skip schedule check."""
        parser.add_argument(  # type: ignore[attr-defined]
            "--force",
            action="store_true",
            help="Skip schedule check and run billing immediately.",
        )

    def handle(self, *args: object, **options: object) -> None:
        """Execute the billing run."""
        if not self._acquire_lock():
            self.stdout.write("Another billing run is in progress. Exiting.")
            return

        try:
            self._run_billing(force=bool(options["force"]))
        finally:
            self._release_lock()

    def _acquire_lock(self) -> bool:
        """Acquire a PostgreSQL advisory lock. Returns True if acquired, False if already held."""
        if connection.vendor == "sqlite":
            return True  # SQLite doesn't support advisory locks
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_ID])
            row = cursor.fetchone()
            return bool(row and row[0])

    def _release_lock(self) -> None:
        """Release the advisory lock."""
        if connection.vendor == "sqlite":
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_ID])

    def _run_billing(self, *, force: bool) -> None:
        """Core billing logic."""
        settings = BillingSettings.load()

        if settings.charge_frequency == BillingSettings.ChargeFrequency.OFF:
            self.stdout.write("Billing is turned off. Exiting.")
            return

        if not force and not self._is_billing_time(settings):
            self.stdout.write("Not time to bill yet. Exiting.")
            return

        # Find tabs with pending entries for active members
        tabs_with_pending = (
            Tab.objects.filter(
                member__status="active",
                entries__tab_charge__isnull=True,
                entries__voided_at__isnull=True,
            )
            .distinct()
            .select_related("member")
        )

        billed_count = 0
        skipped_count = 0

        for tab in tabs_with_pending:
            result = self._process_tab(tab, settings)
            billed_count += result
            if result == 0:
                skipped_count += 1

        # Process retries for previously failed charges
        retry_count = self._process_retries(settings)

        self.stdout.write(f"Billing complete: {billed_count} charged, {skipped_count} skipped, {retry_count} retried.")

    def _is_billing_time(self, settings: BillingSettings) -> bool:
        """Check if the current time matches the billing schedule."""
        now = timezone.localtime()  # Uses TIME_ZONE from settings (Pacific)

        if settings.charge_frequency == BillingSettings.ChargeFrequency.DAILY:
            return True

        if settings.charge_frequency == BillingSettings.ChargeFrequency.WEEKLY:
            return now.weekday() == (settings.charge_day_of_week or 0)

        if settings.charge_frequency == BillingSettings.ChargeFrequency.MONTHLY:
            return now.day == (settings.charge_day_of_month or 1)

        return False

    def _process_tab(self, tab: Tab, settings: BillingSettings) -> int:
        """Process a single tab. Returns the count of charges created."""
        with transaction.atomic():
            locked_tab = Tab.objects.select_for_update().get(pk=tab.pk)

            # Compute pending balance (quick check before grouping)
            pending_total = locked_tab.entries.filter(
                tab_charge__isnull=True,
                voided_at__isnull=True,
            ).aggregate(total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField()))["total"]

            # Skip zero or sub-minimum balances
            if pending_total < Decimal("0.50"):
                if pending_total > Decimal("0.00"):
                    logger.info("Tab %s: $%s below Stripe minimum, skipping.", tab.pk, pending_total)
                return 0

            # Skip if no payment method
            if not locked_tab.has_payment_method:
                logger.warning("Tab %s: no payment method on file, skipping.", tab.pk)
                return 0

            if not locked_tab.stripe_customer_id:
                logger.warning("Tab %s: no Stripe customer ID, skipping.", tab.pk)
                return 0

            charges_to_process = self._build_charges_by_destination(locked_tab)

        # Stripe calls outside the DB transaction to avoid long locks
        charges_created = 0
        for charge, idempotency_key, fee_cents in charges_to_process:
            success = self._execute_charge(tab, charge, idempotency_key, fee_cents, settings)
            if success:
                charges_created += 1

        return charges_created

    def _build_charges_by_destination(self, locked_tab: Tab) -> list[tuple[TabCharge, str, int | None]]:
        """Group pending entries by guild and create a TabCharge per group."""
        pending_entries = list(
            locked_tab.entries.filter(
                tab_charge__isnull=True,
                voided_at__isnull=True,
            ).select_related("product__guild")
        )

        groups: dict[int | None, list[TabEntry]] = {}
        for entry in pending_entries:
            guild_id = entry.product.guild_id if entry.product else None
            groups.setdefault(guild_id, []).append(entry)

        charges_to_process: list[tuple[TabCharge, str, int | None]] = []

        for guild_id, entries in groups.items():
            group_total = sum((e.amount for e in entries), Decimal("0.00"))
            if group_total < Decimal("0.50"):
                continue

            stripe_account = self._resolve_stripe_account(locked_tab, guild_id, len(entries))
            if guild_id is not None and stripe_account is None:
                continue  # Disconnected guild — skip

            application_fee, fee_cents = self._compute_fee(stripe_account, group_total)

            idempotency_key = str(uuid.uuid4())
            charge = TabCharge.objects.create(
                tab=locked_tab,
                amount=group_total,
                status=TabCharge.Status.PROCESSING,
                stripe_account=stripe_account,
                application_fee=application_fee,
            )

            entry_ids = [e.pk for e in entries]
            TabEntry.objects.filter(pk__in=entry_ids).update(tab_charge=charge)
            charges_to_process.append((charge, idempotency_key, fee_cents))

        return charges_to_process

    def _resolve_stripe_account(self, tab: Tab, guild_id: int | None, entry_count: int) -> StripeAccount | None:
        """Look up the active StripeAccount for a guild. Returns None for platform charges."""
        if guild_id is None:
            return None
        try:
            return StripeAccount.objects.get(guild_id=guild_id, is_active=True)
        except StripeAccount.DoesNotExist:
            logger.warning(
                "Tab %s: no active StripeAccount for guild %s, skipping %d entries.",
                tab.pk,
                guild_id,
                entry_count,
            )
            return None

    @staticmethod
    def _compute_fee(stripe_account: StripeAccount | None, amount: Decimal) -> tuple[Decimal | None, int | None]:
        """Compute application fee for a destination charge."""
        if stripe_account is None:
            return None, None
        fee = stripe_account.compute_fee(amount)
        if fee > Decimal("0.00"):
            return fee, int(fee * 100)
        return None, None

    def _execute_charge(
        self,
        tab: Tab,
        charge: TabCharge,
        idempotency_key: str,
        fee_cents: int | None,
        settings: BillingSettings,
    ) -> bool:
        """Call Stripe for a single charge. Returns True on success."""
        success = charge.execute_stripe_charge(idempotency_key)
        if success:
            send_receipt(charge)
            return True
        logger.exception("Tab %s: Stripe charge failed.", tab.pk)
        charge.retry_count += 1
        charge.next_retry_at = timezone.now() + timedelta(hours=settings.retry_interval_hours)
        charge.save(update_fields=["retry_count", "next_retry_at"])
        notify_admin_charge_failed(charge)
        return False

    def _process_retries(self, settings: BillingSettings) -> int:
        """Retry failed charges that are due for retry. Returns count of retries attempted."""
        retryable = TabCharge.objects.needs_retry().select_related("tab", "tab__member", "stripe_account")
        retry_count = 0

        for charge in retryable:
            tab = charge.tab

            if not tab.has_payment_method or not tab.stripe_customer_id:
                continue

            idempotency_key = f"retry-{charge.pk}-{charge.retry_count}"
            success = charge.execute_stripe_charge(idempotency_key)
            if success:
                send_receipt(charge)
            else:
                logger.exception("Tab %s: retry %d failed.", tab.pk, charge.retry_count)
                charge.retry_count += 1
                if charge.retry_count >= settings.max_retry_attempts:
                    charge.next_retry_at = None
                    charge.save()
                    tab.lock(f"Payment failed after {charge.retry_count} attempts")
                    notify_admin_charge_failed(charge)
                else:
                    charge.next_retry_at = timezone.now() + timedelta(hours=settings.retry_interval_hours)
                    charge.save()

            retry_count += 1

        return retry_count
