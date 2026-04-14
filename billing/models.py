"""Billing models — BillingSettings, Product, Tab, TabEntry, TabCharge."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .exceptions import TabLimitExceededError, TabLockedError
from .fields import EncryptedCharField

if TYPE_CHECKING:
    from django.contrib.auth.models import User


_CENTS = Decimal("0.01")
_ZERO = Decimal("0.00")
_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class EntrySplit:
    """One row of a TabEntry's revenue breakdown — see TabEntry.compute_splits().

    ``guild_id`` of ``None`` means the Admin recipient (Past Lives Makerspace
    itself). Every other row is a guild payout.
    """

    guild_id: int | None
    amount: Decimal

    @property
    def is_admin(self) -> bool:
        return self.guild_id is None


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
    default_admin_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=(
            "Site-wide default admin percentage on each charge (0-100). Overridden per-product "
            "on Product.admin_percent_override."
        ),
    )

    # ---- Stripe platform configuration ----
    # Credentials for the single Past Lives platform Stripe account. All charges
    # and SetupIntents run through these keys.
    connect_enabled = models.BooleanField(
        default=False,
        help_text="Master switch for Stripe Connect platform billing. When off, the OAuth tab is hidden.",
    )
    connect_client_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Stripe Connect application client ID (ca_…). From dashboard.stripe.com/settings/connect.",
    )
    connect_platform_publishable_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="PL platform Stripe publishable key (pk_…). Sent to the browser for the payment-method setup flow.",
    )
    connect_platform_secret_key = EncryptedCharField(
        max_length=512,
        blank=True,
        default="",
        help_text="PL platform Stripe secret key (sk_…). Used for OAuth Connect destination charges. Encrypted at rest.",
    )
    connect_platform_webhook_secret = EncryptedCharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Webhook signing secret for the global /billing/webhooks/stripe/ endpoint. Encrypted at rest.",
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
            models.CheckConstraint(
                condition=(Q(default_admin_percent__gte=0) & Q(default_admin_percent__lte=100)),
                name="billing_settings_default_admin_percent_range",
            ),
        ]

    def __str__(self) -> str:
        return "Billing Settings"

    def clean(self) -> None:
        """If Connect is enabled, all four platform credential fields must be non-empty."""
        super().clean()
        if self.connect_enabled:
            missing = []
            if not self.connect_client_id:
                missing.append("connect_client_id")
            if not self.connect_platform_publishable_key:
                missing.append("connect_platform_publishable_key")
            if not self.connect_platform_secret_key:
                missing.append("connect_platform_secret_key")
            if not self.connect_platform_webhook_secret:
                missing.append("connect_platform_webhook_secret")
            if missing:
                raise ValidationError({field: "Required when Stripe Connect is enabled." for field in missing})

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
# RevenueSplit + SplitRecipient
# ---------------------------------------------------------------------------


class RevenueSplit(models.Model):
    """A reusable container for a set of payout recipients.

    Attached 1:1 to a Product (and, eventually, to other billable objects like
    class registrations or shelf rentals). Recipients must sum to exactly 100%.
    """

    name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional label for this split (e.g. 'Default glass guild split'). Blank for private per-product splits.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this split was created.")

    class Meta:
        verbose_name = "Revenue Split"
        verbose_name_plural = "Revenue Splits"

    def __str__(self) -> str:
        return self.name or f"Split #{self.pk}"

    def clean(self) -> None:
        """Enforce sum-to-100 across child recipients. No-op until recipients exist."""
        super().clean()
        if self.pk is None:
            return
        total = self.recipients.aggregate(total=Coalesce(Sum("percent"), Value(_ZERO), output_field=DecimalField()))[
            "total"
        ]
        if self.recipients.exists() and total != _HUNDRED:
            raise ValidationError(f"Revenue split recipients must sum to 100% (got {total}%).")

    def snapshot(self) -> list[dict[str, Any]]:
        """Return the current recipients as a frozen JSON-serializable list.

        Stored on TabEntry.split_snapshot so historical reports stay stable
        when the underlying split changes later.
        """
        return [
            {"guild_id": r.guild_id, "percent": str(r.percent)}
            for r in self.recipients.order_by("pk").all()
        ]


class SplitRecipient(models.Model):
    """One payout row in a RevenueSplit. ``guild=None`` means Admin."""

    split = models.ForeignKey(
        RevenueSplit,
        on_delete=models.CASCADE,
        related_name="recipients",
        help_text="The parent revenue split.",
    )
    guild = models.ForeignKey(
        "membership.Guild",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="split_recipients",
        help_text="Payout recipient. Null means the Admin (Past Lives) share.",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100"))],
        help_text="Share of the charged amount (0 < p ≤ 100).",
    )

    class Meta:
        verbose_name = "Split Recipient"
        verbose_name_plural = "Split Recipients"
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(percent__gt=0) & Q(percent__lte=100)),
                name="split_recipient_percent_range",
            ),
            models.UniqueConstraint(
                fields=["split", "guild"],
                name="uq_split_recipient_split_guild",
                condition=Q(guild__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["split"],
                name="uq_split_recipient_split_admin",
                condition=Q(guild__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        target = self.guild.name if self.guild_id is not None else "Admin"
        return f"{target}: {self.percent}%"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class Product(models.Model):
    """A purchasable product. Revenue is split per its attached RevenueSplit."""

    name = models.CharField(
        max_length=255,
        help_text="Display name of the product.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="What this product is. Shown to members on the guild page.",
    )
    photo = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True,
        help_text="Optional product image.",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Price in USD. Must be positive.",
    )
    guild = models.ForeignKey(
        "membership.Guild",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        help_text=(
            "Owning guild — controls which guild page the product appears on. "
            "Independent from the revenue split (a product owned by one guild can "
            "pay out to any combination of Admin + guilds). Null means gallery/unattributed."
        ),
    )
    revenue_split = models.OneToOneField(
        RevenueSplit,
        on_delete=models.PROTECT,
        related_name="product",
        help_text="How this product's revenue is split between Admin and guilds.",
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

    def clean(self) -> None:
        super().clean()
        if self.revenue_split_id is not None:
            self.revenue_split.clean()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Auto-provision a default RevenueSplit on first save if none is set.

        Default shape: site default_admin_percent to Admin, remainder to
        ``self.guild`` (if set), else 100% to Admin. This keeps the inline
        product creation flow ergonomic — the admin can refine the split
        afterward on the Product change page.
        """
        if self.revenue_split_id is None:
            admin_percent = BillingSettings.load().default_admin_percent
            split = RevenueSplit.objects.create()
            if self.guild_id is not None and admin_percent < _HUNDRED:
                guild_percent = _HUNDRED - admin_percent
                if admin_percent > _ZERO:
                    SplitRecipient.objects.create(split=split, guild=None, percent=admin_percent)
                SplitRecipient.objects.create(split=split, guild_id=self.guild_id, percent=guild_percent)
            else:
                SplitRecipient.objects.create(split=split, guild=None, percent=_HUNDRED)
            self.revenue_split = split
        super().save(*args, **kwargs)


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
        """True if the tab is not locked AND a payment method is on file.

        A saved card is required because every charge now runs through the
        single platform Stripe account via an off-session PaymentIntent.
        """
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
        product: Product | None = None,
        revenue_split: RevenueSplit | None = None,
    ) -> TabEntry:
        """Add a line item to this tab with race-condition protection.

        Uses select_for_update() inside transaction.atomic() to prevent
        concurrent requests from both passing the limit check. Resolves the
        revenue split and snapshots it onto the entry's ``split_snapshot``
        JSON so historical reports stay stable when the underlying
        RevenueSplit changes later.

        Resolution: explicit ``revenue_split`` kwarg > ``product.revenue_split``
        > implicit 100%-Admin (for unattributed manual entries).

        Raises:
            TabLockedError: If the tab is locked.
            TabLimitExceededError: If the entry would exceed the tab limit.
        """
        resolved_split = revenue_split if revenue_split is not None else (product.revenue_split if product else None)
        if resolved_split is not None:
            snapshot = resolved_split.snapshot()
        else:
            snapshot = [{"guild_id": None, "percent": "100.00"}]

        with transaction.atomic():
            locked_self = Tab.objects.select_for_update().get(pk=self.pk)

            if locked_self.is_locked:
                raise TabLockedError(f"Tab is locked: {locked_self.locked_reason}")

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
                product=product,
                split_snapshot=snapshot,
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

    def get_or_create_stripe_customer(self) -> str:
        """Return the Stripe Customer ID, creating one if it does not exist yet."""
        from billing import stripe_utils as _stripe_utils

        if not self.stripe_customer_id:
            self.stripe_customer_id = _stripe_utils.create_customer(
                email=self.member.primary_email,
                name=self.member.display_name,
                member_pk=self.member.pk,
            )
            self.save(update_fields=["stripe_customer_id"])
        return self.stripe_customer_id

    def set_payment_method(self, payment_method_id: str) -> None:
        """Attach a payment method to this tab's Stripe customer and persist the details."""
        from billing import stripe_utils as _stripe_utils

        if self.stripe_customer_id:
            _stripe_utils.attach_payment_method(
                customer_id=self.stripe_customer_id,
                payment_method_id=payment_method_id,
            )
        pm_details = _stripe_utils.retrieve_payment_method(payment_method_id=payment_method_id)
        self.stripe_payment_method_id = pm_details["id"]
        self.payment_method_last4 = pm_details["last4"]
        self.payment_method_brand = pm_details["brand"]
        self.save(
            update_fields=[
                "stripe_payment_method_id",
                "payment_method_last4",
                "payment_method_brand",
                "updated_at",
            ]
        )

    def clear_payment_method(self) -> None:
        """Detach the current payment method from Stripe and clear all payment fields."""
        from billing import stripe_utils as _stripe_utils

        if self.stripe_payment_method_id:
            _stripe_utils.detach_payment_method(payment_method_id=self.stripe_payment_method_id)
            self.stripe_payment_method_id = ""
            self.payment_method_last4 = ""
            self.payment_method_brand = ""
            self.save(
                update_fields=[
                    "stripe_payment_method_id",
                    "payment_method_last4",
                    "payment_method_brand",
                    "updated_at",
                ]
            )


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
    # ---- Snapshot split (frozen at entry creation) ----
    # See Tab.add_entry(). Never recomputed at read time so historical reports
    # stay stable if the product's RevenueSplit changes later.
    #
    # Format: list[{"guild_id": int | None, "percent": "20.00"}]
    # A guild_id of None means the Admin (Past Lives) share.
    split_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="Frozen list of payout recipients resolved from the product's RevenueSplit at creation time.",
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

    def compute_splits(self) -> list[EntrySplit]:
        """Return the per-recipient breakdown for this entry.

        Walks ``split_snapshot`` in order and assigns each recipient
        ``floor(amount_cents * percent / 100)`` cents, then distributes any
        rounding remainder one cent at a time to recipients in snapshot order.
        This is deterministic and always sums exactly to ``self.amount``.

        Empty snapshot falls back to a single Admin row for the full amount.
        """
        snapshot = self.split_snapshot or []
        if not snapshot:
            return [EntrySplit(guild_id=None, amount=self.amount)]

        total_cents = int((self.amount * _HUNDRED).to_integral_value(rounding=ROUND_HALF_UP))
        raw_cents: list[int] = []
        for row in snapshot:
            percent = Decimal(str(row["percent"]))
            raw_cents.append(int((Decimal(total_cents) * percent / _HUNDRED).to_integral_value(rounding=ROUND_DOWN)))

        # Deterministic remainder distribution — one cent at a time to recipients
        # in snapshot order. Always nets exactly to total_cents.
        remainder = total_cents - sum(raw_cents)
        for i in range(remainder):
            raw_cents[i % len(raw_cents)] += 1

        return [
            EntrySplit(
                guild_id=row["guild_id"],
                amount=(Decimal(cents) / _HUNDRED).quantize(_CENTS),
            )
            for row, cents in zip(snapshot, raw_cents)
        ]


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
        PENDING_CHECKOUT = "pending_checkout", "Awaiting member checkout"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    tab = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name="charges",
        help_text="The tab this charge belongs to.",
    )
    application_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
        help_text="DEPRECATED — historical only, not written after v1.5.0.",
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
    stripe_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
        help_text="DEPRECATED — historical only, not written after v1.5.0.",
    )
    stripe_checkout_url = models.URLField(
        blank=True,
        editable=False,
        help_text="DEPRECATED — historical only, not written after v1.5.0.",
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

    def execute_stripe_charge(self, idempotency_key: str) -> bool:
        """Call Stripe for this charge via the single platform account. Returns True on success.

        On success: sets status=SUCCEEDED, stripe_payment_intent_id, stripe_charge_id,
        stripe_receipt_url, charged_at, and saves.
        On failure: sets status=FAILED, failure_reason, and saves.
        """
        from billing import stripe_utils as _stripe_utils

        tab = self.tab
        amount_cents = int(self.amount * 100)
        description = f"Past Lives Makerspace tab — {self.entry_count} items"
        metadata = {"tab_id": str(tab.pk), "charge_id": str(self.pk)}

        try:
            result = _stripe_utils.create_payment_intent(
                customer_id=tab.stripe_customer_id,
                payment_method_id=tab.stripe_payment_method_id,
                amount_cents=amount_cents,
                description=description,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
            self.stripe_payment_intent_id = result["id"]
            self.stripe_charge_id = result["charge_id"]
            self.stripe_receipt_url = result["receipt_url"]
            self.status = self.Status.SUCCEEDED
            self.charged_at = timezone.now()
            self.save(
                update_fields=[
                    "stripe_payment_intent_id",
                    "stripe_charge_id",
                    "stripe_receipt_url",
                    "status",
                    "charged_at",
                ]
            )
            return True
        except Exception:
            self.status = self.Status.FAILED
            self.failure_reason = "Stripe charge failed"
            self.save(update_fields=["status", "failure_reason"])
            return False
