from __future__ import annotations

import math
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class Tool(models.Model):
    class OwnerType(models.TextChoices):
        GUILD = "guild", "Guild"
        MEMBER = "member", "Member"
        ORG = "org", "Organization"

    guild = models.ForeignKey(
        "membership.Guild", null=True, blank=True, on_delete=models.SET_NULL, related_name="tools"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="tools/", blank=True)
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    owner_type = models.CharField(max_length=20, choices=OwnerType.choices, default=OwnerType.ORG)
    owner_id = models.PositiveIntegerField(null=True, blank=True)
    is_reservable = models.BooleanField(default=False)
    is_rentable = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Tool"
        verbose_name_plural = "Tools"

    def __str__(self) -> str:
        return self.name


class ToolReservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="reservations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tool_reservations")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]
        verbose_name = "Tool Reservation"
        verbose_name_plural = "Tool Reservations"

    def __str__(self) -> str:
        return f"{self.tool.name} - {self.user} ({self.starts_at.date()})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class Rentable(models.Model):
    class RentalPeriod(models.TextChoices):
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"
        WEEKS = "weeks", "Weeks"

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="rentables")
    rental_period = models.CharField(max_length=20, choices=RentalPeriod.choices)
    cost_per_period = models.DecimalField(max_digits=8, decimal_places=2)
    revenue_split = models.ForeignKey(
        "billing.RevenueSplit", null=True, blank=True, on_delete=models.SET_NULL, related_name="rentables"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tool", "rental_period"]
        verbose_name = "Rentable"
        verbose_name_plural = "Rentables"

    def __str__(self) -> str:
        return f"{self.tool.name} - ${self.cost_per_period}/{self.rental_period}"

    @property
    def formatted_cost(self) -> str:
        return f"${self.cost_per_period:.2f}/{self.rental_period}"

    def is_available(self) -> bool:
        """Check if the rentable is active and has no active rentals."""
        if not self.is_active:
            return False
        return not self.rentals.filter(status=Rental.Status.ACTIVE).exists()


class Rental(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RETURNED = "returned", "Returned"
        OVERDUE = "overdue", "Overdue"

    rentable = models.ForeignKey(Rentable, on_delete=models.CASCADE, related_name="rentals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rentals")
    checked_out_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    order = models.ForeignKey("billing.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="rentals")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_out_at"]
        verbose_name = "Rental"
        verbose_name_plural = "Rentals"

    def __str__(self) -> str:
        return f"{self.rentable.tool.name} - {self.user} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def is_overdue(self) -> bool:
        return self.status == self.Status.ACTIVE and self.due_at < timezone.now()

    @property
    def is_returned(self) -> bool:
        return self.status == self.Status.RETURNED

    def mark_as_returned(self) -> None:
        self.status = self.Status.RETURNED
        self.returned_at = timezone.now()
        self.save()

    def calculate_rental_cost(self) -> Decimal:
        """Calculate the rental cost based on the rental period."""
        if self.returned_at:
            duration = self.returned_at - self.checked_out_at
        else:
            duration = timezone.now() - self.checked_out_at

        hours = Decimal(str(duration.total_seconds())) / Decimal("3600")
        period = self.rentable.rental_period

        if period == Rentable.RentalPeriod.HOURS:
            periods = hours
        elif period == Rentable.RentalPeriod.DAYS:
            periods = hours / Decimal("24")
        else:  # weeks
            periods = hours / Decimal("168")

        periods_rounded = Decimal(str(math.ceil(float(periods))))
        return periods_rounded * self.rentable.cost_per_period


class Document(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    documentable = GenericForeignKey("content_type", "object_id")
    name = models.CharField(max_length=255)
    file_path = models.FileField(upload_to="documents/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="uploaded_documents"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return self.name
