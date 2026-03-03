from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class RevenueSplit(models.Model):
    name = models.CharField(max_length=255, unique=True)
    splits = models.JSONField(default=list, help_text="List of {entity_type, entity_id, percentage}")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Revenue Split"
        verbose_name_plural = "Revenue Splits"

    def __str__(self) -> str:
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        ON_TAB = "on_tab", "On Tab"
        BILLED = "billed", "Billed"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    description = models.CharField(max_length=500)
    amount = models.IntegerField(help_text="Amount in cents")
    revenue_split = models.ForeignKey(
        RevenueSplit, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ON_TAB)

    # GenericFK for orderable (class, orientation, rental, buyable, etc.)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    orderable = GenericForeignKey("content_type", "object_id")

    issued_at = models.DateTimeField(default=timezone.now)
    billed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self) -> str:
        return f"Order #{self.pk} - {self.description} ({self.formatted_amount})"

    @property
    def formatted_amount(self) -> str:
        return f"${self.amount / 100:.2f}"

    @property
    def is_on_tab(self) -> bool:
        return self.status == self.Status.ON_TAB

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.PAID

    @property
    def is_failed(self) -> bool:
        return self.status == self.Status.FAILED


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        VOID = "void", "Void"
        UNCOLLECTIBLE = "uncollectible", "Uncollectible"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invoices")
    stripe_invoice_id = models.CharField(max_length=255, blank=True)
    amount_due = models.IntegerField(help_text="Amount due in cents")
    amount_paid = models.IntegerField(default=0, help_text="Amount paid in cents")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    line_items = models.JSONField(default=list)
    pdf_url = models.URLField(blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self) -> str:
        return f"Invoice #{self.pk} - {self.formatted_amount_due} ({self.status})"

    @property
    def formatted_amount_due(self) -> str:
        return f"${self.amount_due / 100:.2f}"

    @property
    def formatted_amount_paid(self) -> str:
        return f"${self.amount_paid / 100:.2f}"

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.PAID


class Payout(models.Model):
    class PayeeType(models.TextChoices):
        USER = "user", "User"
        GUILD = "guild", "Guild"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DISTRIBUTED = "distributed", "Distributed"

    payee_type = models.CharField(max_length=20, choices=PayeeType.choices)
    payee_id = models.PositiveIntegerField()
    amount = models.IntegerField(help_text="Amount in cents")
    invoice_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    distributed_at = models.DateTimeField(null=True, blank=True)
    distributed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="distributed_payouts",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end"]
        verbose_name = "Payout"
        verbose_name_plural = "Payouts"

    def __str__(self) -> str:
        return f"Payout #{self.pk} - {self.formatted_amount} ({self.payee_type}:{self.payee_id})"

    @property
    def formatted_amount(self) -> str:
        return f"${self.amount / 100:.2f}"

    @property
    def is_distributed(self) -> bool:
        return self.status == self.Status.DISTRIBUTED


class SubscriptionPlan(models.Model):
    """Defines a subscription plan available to members."""

    class Interval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    interval = models.CharField(max_length=20, choices=Interval.choices)
    stripe_price_id = models.CharField(max_length=255, blank=True)
    plan_type = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"

    def __str__(self) -> str:
        return f"{self.name} (${self.price}/{self.interval})"

    @property
    def formatted_price(self) -> str:
        return f"${self.price:.2f}"


class MemberSubscription(models.Model):
    """Tracks a member's active or historical subscription to a plan."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"
        PAST_DUE = "past_due", "Past Due"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="member_subscriptions")
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    next_billing_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]
        verbose_name = "Member Subscription"
        verbose_name_plural = "Member Subscriptions"

    def __str__(self) -> str:
        return f"{self.user} - {self.subscription_plan.name} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def effective_price(self) -> Decimal:
        if self.discount_percentage:
            discount = self.subscription_plan.price * self.discount_percentage / 100
            return self.subscription_plan.price - discount
        return self.subscription_plan.price
