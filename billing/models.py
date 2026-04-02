"""Billing models — BillingSettings, StripeAccount, Product, Tab, TabEntry, TabCharge."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models, transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .exceptions import NoPaymentMethodError, TabLimitExceededError, TabLockedError

if TYPE_CHECKING:
    from django.contrib.auth.models import User


# ---------------------------------------------------------------------------
# BillingSettings (singleton, pk=1)
# ---------------------------------------------------------------------------


class BillingSettings(models.Model):
    """Site-wide billing configuration. Singleton — always pk=1."""

    class ChargeFrequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        OFF = "off", "Off"

    charge_frequency = models.CharField(
        max_length=20,
        choices=ChargeFrequency.choices,
        default=ChargeFrequency.MONTHLY,
        help_text="How often to run the billing cycle.",
    )
    charge_time = models.TimeField(
        default="23:00",
        help_text="Time of day to run billing (Pacific time).",
    )
    charge_day_of_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Day of week for WEEKLY billing (0=Monday .. 6=Sunday).",
    )
    charge_day_of_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Day of month for MONTHLY billing (1-28).",
    )
    default_tab_limit = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("200.00"),
        help_text="Maximum tab balance before new entries are blocked.",
    )
    max_retry_attempts = models.PositiveSmallIntegerField(
        default=3,
        help_text="Number of times to retry a failed charge before locking the tab.",
    )
    retry_interval_hours = models.PositiveSmallIntegerField(
        default=24,
        help_text="Hours between retry attempts for failed charges.",
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="Last time billing settings were changed.")

    class Meta:
        verbose_name = "Billing Settings"
        verbose_name_plural = "Billing Settings"
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="billing_settings_singleton"),
            models.CheckConstraint(
                condition=(Q(charge_frequency="weekly") | Q(charge_day_of_week__isnull=True)),
                name="billing_settings_day_of_week_only_weekly",
            ),
            models.CheckConstraint(
                condition=(Q(charge_frequency="monthly") | Q(charge_day_of_month__isnull=True)),
                name="billing_settings_day_of_month_only_monthly",
            ),
            models.CheckConstraint(
                condition=(Q(charge_day_of_week__isnull=True) | Q(charge_day_of_week__lte=6)),
                name="billing_settings_day_of_week_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(charge_day_of_month__isnull=True)
                    | (Q(charge_day_of_month__gte=1) & Q(charge_day_of_month__lte=28))
                ),
                name="billing_settings_day_of_month_range",
            ),
        ]

    def __str__(self) -> str:
        return "Billing Settings"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Force singleton by always using pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> BillingSettings:
        """Load the singleton instance, creating it with defaults if needed."""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


# ---------------------------------------------------------------------------
# StripeAccount
# ---------------------------------------------------------------------------


class StripeAccount(models.Model):
    """A Stripe Connect account linked to a guild."""

    guild = models.OneToOneField(
        "membership.Guild",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stripe_account",
        help_text="The guild this Stripe account belongs to.",
    )
    stripe_account_id = models.CharField(
        max_length=255,
        help_text="Stripe Connect account ID (acct_xxx).",
    )
    display_name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this Stripe account.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this Stripe account is currently active.",
    )
    platform_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percentage of each charge kept by the platform (0-100).",
    )
    connected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this Stripe account was connected.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this record was created.")

    class Meta:
        verbose_name = "Stripe Account"
        verbose_name_plural = "Stripe Accounts"

    def __str__(self) -> str:
        return self.display_name

    def compute_fee(self, amount: Decimal) -> Decimal:
        """Calculate the platform fee for a given amount.

        Args:
            amount: The charge amount to compute the fee on.

        Returns:
            The platform fee rounded to 2 decimal places.
        """
        if self.platform_fee_percent == 0:
            return Decimal("0.00")
        return (amount * self.platform_fee_percent / Decimal("100")).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class Product(models.Model):
    """A purchasable product offered by a guild."""

    name = models.CharField(
        max_length=255,
        help_text="Display name of the product.",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Price in USD. Must be positive.",
    )
    guild = models.ForeignKey(
        "membership.Guild",
        on_delete=models.CASCADE,
        related_name="products",
        help_text="The guild that offers this product.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this product is currently available.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who created this product.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this product was created.")

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["guild__name", "name"]
        constraints = [
            models.CheckConstraint(condition=Q(price__gt=0), name="product_price_positive"),
        ]

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Tab
# ---------------------------------------------------------------------------


class Tab(models.Model):
    """A member's billing tab — accumulates charges between billing runs."""

    member = models.OneToOneField(
        "membership.Member",
        on_delete=models.PROTECT,
        related_name="tab",
        help_text="The member this tab belongs to.",
    )
    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe Customer ID for this member.",
    )
    stripe_payment_method_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Default Stripe PaymentMethod ID on file.",
    )
    payment_method_last4 = models.CharField(
        max_length=4,
        blank=True,
        help_text="Last 4 digits of the payment method on file.",
    )
    payment_method_brand = models.CharField(
        max_length=20,
        blank=True,
        help_text="Card brand (e.g. visa, mastercard).",
    )
    tab_limit = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Per-member tab limit override. Null means use the default from BillingSettings.",
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Locked tabs cannot accept new entries (usually due to failed payment).",
    )
    locked_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Why this tab is locked.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this tab was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last time this tab was modified.")

    class Meta:
        verbose_name = "Tab"
        verbose_name_plural = "Tabs"

    def __str__(self) -> str:
        return f"Tab for {self.member}"

    @property
    def effective_tab_limit(self) -> Decimal:
        """Per-member override if set, otherwise the global default."""
        if self.tab_limit is not None:
            return self.tab_limit
        return BillingSettings.load().default_tab_limit

    @property
    def current_balance(self) -> Decimal:
        """Sum of all pending (uncharged, non-voided) entry amounts."""
        result = self.entries.filter(
            tab_charge__isnull=True,
            voided_at__isnull=True,
        ).aggregate(total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField()))
        return result["total"]

    @property
    def has_payment_method(self) -> bool:
        return bool(self.stripe_payment_method_id)

    @property
    def can_add_entry(self) -> bool:
        """True if the tab is not locked and has a payment method."""
        return not self.is_locked and self.has_payment_method

    @property
    def remaining_limit(self) -> Decimal:
        """How much more can be added before hitting the tab limit."""
        return self.effective_tab_limit - self.current_balance

    def add_entry(
        self,
        *,
        description: str,
        amount: Decimal,
        added_by: User | None = None,
        is_self_service: bool = False,
    ) -> TabEntry:
        """Add a line item to this tab with race-condition protection.

        Uses select_for_update() inside transaction.atomic() to prevent
        concurrent requests from both passing the limit check.

        Raises:
            TabLockedError: If the tab is locked.
            NoPaymentMethodError: If no payment method is on file.
            TabLimitExceededError: If the entry would exceed the tab limit.
        """
        with transaction.atomic():
            # Lock this tab row for the duration of the transaction
            locked_self = Tab.objects.select_for_update().get(pk=self.pk)

            if locked_self.is_locked:
                raise TabLockedError(f"Tab is locked: {locked_self.locked_reason}")

            if not locked_self.has_payment_method:
                raise NoPaymentMethodError("No payment method on file.")

            # Compute current balance under the lock
            current = locked_self.current_balance
            if current + amount > locked_self.effective_tab_limit:
                raise TabLimitExceededError(
                    f"Entry of ${amount} would exceed tab limit "
                    f"(balance: ${current}, limit: ${locked_self.effective_tab_limit})."
                )

            return TabEntry.objects.create(
                tab=self,
                description=description,
                amount=amount,
                added_by=added_by,
                is_self_service=is_self_service,
            )

    def lock(self, reason: str) -> None:
        """Lock the tab, preventing new entries."""
        self.is_locked = True
        self.locked_reason = reason
        self.save(update_fields=["is_locked", "locked_reason", "updated_at"])

    def unlock(self) -> None:
        """Unlock the tab, allowing new entries."""
        self.is_locked = False
        self.locked_reason = ""
        self.save(update_fields=["is_locked", "locked_reason", "updated_at"])


# ---------------------------------------------------------------------------
# TabEntry
# ---------------------------------------------------------------------------


class TabEntryQuerySet(models.QuerySet):
    def pending(self) -> TabEntryQuerySet:
        """Entries not yet charged and not voided."""
        return self.filter(tab_charge__isnull=True, voided_at__isnull=True)

    def charged(self) -> TabEntryQuerySet:
        """Entries that have been included in a charge."""
        return self.filter(tab_charge__isnull=False)

    def voided(self) -> TabEntryQuerySet:
        """Entries that have been voided."""
        return self.filter(voided_at__isnull=False)


class TabEntry(models.Model):
    """A single line item on a member's tab."""

    class EntryType(models.TextChoices):
        MANUAL = "manual", "Manual"

    tab = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name="entries",
        help_text="The tab this entry belongs to.",
    )
    tab_charge = models.ForeignKey(
        "TabCharge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entries",
        help_text="The charge this entry was billed in. Null means pending.",
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tab_entries",
        help_text="The product this entry is for, if applicable.",
    )
    description = models.CharField(
        max_length=500,
        help_text="What this charge is for.",
    )
    amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Amount in USD. Must be positive.",
    )
    entry_type = models.CharField(
        max_length=20,
        choices=EntryType.choices,
        default=EntryType.MANUAL,
        help_text="Type of charge.",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tab_entries_added",
        help_text="User who added this entry.",
    )
    is_self_service = models.BooleanField(
        default=False,
        help_text="Whether the member added this themselves.",
    )
    voided_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this entry was voided. Null means active.",
    )
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tab_entries_voided",
        help_text="User who voided this entry.",
    )
    voided_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Why this entry was voided.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this entry was created.")
    notes = models.TextField(blank=True, help_text="Internal notes about this entry.")

    objects = TabEntryQuerySet.as_manager()

    class Meta:
        verbose_name = "Tab Entry"
        verbose_name_plural = "Tab Entries"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="tab_entry_amount_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.description} (${self.amount})"

    @property
    def is_pending(self) -> bool:
        return self.tab_charge is None and self.voided_at is None

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    def void(self, *, user: User, reason: str) -> None:
        """Void this entry. Only allowed on pending entries.

        Raises:
            ValueError: If already voided or already charged.
        """
        if self.voided_at is not None:
            raise ValueError("Entry is already voided.")
        if self.tab_charge is not None:
            raise ValueError("Cannot void an entry that has already been charged.")
        self.voided_at = timezone.now()
        self.voided_by = user
        self.voided_reason = reason
        self.save(update_fields=["voided_at", "voided_by", "voided_reason"])


# ---------------------------------------------------------------------------
# TabCharge
# ---------------------------------------------------------------------------


class TabChargeQuerySet(models.QuerySet):
    def succeeded(self) -> TabChargeQuerySet:
        return self.filter(status=TabCharge.Status.SUCCEEDED)

    def failed(self) -> TabChargeQuerySet:
        return self.filter(status=TabCharge.Status.FAILED)

    def needs_retry(self) -> TabChargeQuerySet:
        """Failed charges whose next_retry_at is in the past."""
        return self.filter(
            status=TabCharge.Status.FAILED,
            next_retry_at__isnull=False,
            next_retry_at__lte=timezone.now(),
        )


class TabCharge(models.Model):
    """A batched Stripe charge against a member's tab entries."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    tab = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name="charges",
        help_text="The tab this charge belongs to.",
    )
    stripe_account = models.ForeignKey(
        StripeAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges",
        help_text="The Stripe Connect account this charge was sent to.",
    )
    application_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Platform application fee collected on this charge.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current status of the charge.",
    )
    amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Total amount charged in USD.",
    )
    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe PaymentIntent ID.",
    )
    stripe_charge_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe Charge ID.",
    )
    stripe_receipt_url = models.URLField(
        blank=True,
        help_text="Link to Stripe-hosted receipt.",
    )
    failure_reason = models.TextField(
        blank=True,
        help_text="Error message from Stripe if the charge failed.",
    )
    retry_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of retry attempts so far.",
    )
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to attempt the next retry.",
    )
    receipt_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the receipt email was sent.",
    )
    charged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the charge was confirmed successful.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this charge record was created.")

    objects = TabChargeQuerySet.as_manager()

    class Meta:
        verbose_name = "Tab Charge"
        verbose_name_plural = "Tab Charges"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Charge ${self.amount} ({self.get_status_display()})"

    @property
    def is_retriable(self) -> bool:
        """True if this charge has failed and hasn't exhausted retries."""
        if self.status != self.Status.FAILED:
            return False
        settings = BillingSettings.load()
        return self.retry_count < settings.max_retry_attempts

    @property
    def entry_count(self) -> int:
        return self.entries.count()
