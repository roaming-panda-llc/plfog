from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class ClassDiscountCode(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed Amount"

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Discount Code"
        verbose_name_plural = "Discount Codes"

    def __str__(self) -> str:
        return self.code

    def calculate_discount(self, price: Decimal) -> Decimal:
        if self.discount_type == self.DiscountType.PERCENTAGE:
            return price * self.discount_value / Decimal("100")
        return min(self.discount_value, price)


class MakerClass(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    guild = models.ForeignKey(
        "membership.Guild", null=True, blank=True, on_delete=models.SET_NULL, related_name="classes"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="classes/", blank=True)
    location = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    max_students = models.PositiveIntegerField(null=True, blank=True)
    revenue_split = models.ForeignKey(
        "billing.RevenueSplit", null=True, blank=True, on_delete=models.SET_NULL, related_name="classes"
    )
    registration_email_copy = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_classes"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    instructors = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="taught_classes")
    discount_codes = models.ManyToManyField(ClassDiscountCode, blank=True, related_name="classes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Class"
        verbose_name_plural = "Classes"

    def __str__(self) -> str:
        return self.name

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED

    def has_available_spots(self) -> bool:
        if self.max_students is None:
            return True
        return self.students.count() < self.max_students


class ClassSession(models.Model):
    maker_class = models.ForeignKey(MakerClass, on_delete=models.CASCADE, related_name="sessions")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["starts_at"]
        verbose_name = "Class Session"
        verbose_name_plural = "Class Sessions"

    def __str__(self) -> str:
        return f"{self.maker_class.name} - {self.starts_at.date()}"


class ClassImage(models.Model):
    maker_class = models.ForeignKey(MakerClass, on_delete=models.CASCADE, related_name="images")
    image_path = models.ImageField(upload_to="class_images/")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "Class Image"
        verbose_name_plural = "Class Images"

    def __str__(self) -> str:
        return f"Image for {self.maker_class.name} (#{self.sort_order})"


class Student(models.Model):
    maker_class = models.ForeignKey(MakerClass, on_delete=models.CASCADE, related_name="students")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="class_enrollments"
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    discount_code = models.ForeignKey(
        ClassDiscountCode, null=True, blank=True, on_delete=models.SET_NULL, related_name="students"
    )
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    invoice_id = models.CharField(max_length=255, blank=True)
    registered_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registered_at"]
        verbose_name = "Student"
        verbose_name_plural = "Students"

    def __str__(self) -> str:
        return f"{self.name} - {self.maker_class.name}"

    @property
    def is_member(self) -> bool:
        return self.user_id is not None


class Orientation(models.Model):
    guild = models.ForeignKey("membership.Guild", on_delete=models.CASCADE, related_name="orientations")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    revenue_split = models.ForeignKey(
        "billing.RevenueSplit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orientations",
    )
    is_active = models.BooleanField(default=True)
    tools = models.ManyToManyField("tools.Tool", blank=True, related_name="orientations")
    orienters = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="authorized_orientations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Orientation"
        verbose_name_plural = "Orientations"

    def __str__(self) -> str:
        return self.name

    @property
    def formatted_price(self) -> str:
        return f"${self.price:.2f}"


class ScheduledOrientation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    orientation = models.ForeignKey(Orientation, on_delete=models.CASCADE, related_name="scheduled")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scheduled_orientations")
    scheduled_at = models.DateTimeField()
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_orientations",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    order = models.ForeignKey(
        "billing.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_orientations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_at"]
        verbose_name = "Scheduled Orientation"
        verbose_name_plural = "Scheduled Orientations"

    def __str__(self) -> str:
        return f"{self.orientation.name} - {self.user} ({self.status})"

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING

    @property
    def is_claimed(self) -> bool:
        return self.status == self.Status.CLAIMED

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.COMPLETED
