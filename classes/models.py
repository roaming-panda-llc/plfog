"""Models for the Classes app."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, F, Q
from django.utils import timezone

from classes.managers import ClassOfferingQuerySet

DEFAULT_LIABILITY_TEXT = """ASSUMPTION OF RISK AND WAIVER OF LIABILITY

I understand that participation in classes, workshops, and activities at Past Lives Makerspace ("PLM") involves inherent risks, including but not limited to: exposure to tools, machinery, and equipment; risk of cuts, burns, eye injury, hearing damage, and other physical harm; and exposure to dust, fumes, chemicals, and other materials.

I voluntarily assume all risks associated with my participation. I hereby release, waive, and discharge PLM, its owners, officers, employees, instructors, volunteers, and agents from any and all liability, claims, demands, or causes of action arising out of or related to my participation, including negligence.

I agree to follow all safety rules, instructions, and guidelines provided by PLM and its instructors. I understand that failure to do so may result in removal from the class without refund.

I confirm that I am at least 18 years of age (or have a parent/guardian signing on my behalf), that I am physically able to participate, and that I carry my own health insurance or accept financial responsibility for any medical treatment I may require.

Past Lives Makerspace LLC, 2808 SE 9th Ave, Portland, OR 97202"""


DEFAULT_MODEL_RELEASE_TEXT = """MODEL RELEASE AND CONSENT TO USE OF IMAGE

I grant Past Lives Makerspace ("PLM"), its employees, and agents the right to photograph, video record, and otherwise capture my likeness during classes and events, and to use such images for promotional, educational, and marketing purposes including but not limited to: website, social media, printed materials, and press.

I waive any right to inspect or approve the finished images or the use to which they may be applied. I release PLM from any claims arising from the use of my likeness.

I understand that I may revoke this consent at any time by notifying PLM in writing at info@pastlives.space."""


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Display name (e.g. Woodworking).")
    slug = models.SlugField(max_length=100, unique=True, help_text="URL slug.")
    sort_order = models.PositiveIntegerField(default=0, help_text="Ascending sort; lower shows first.")
    hero_image = models.ImageField(upload_to="classes/categories/", blank=True, help_text="Optional header image.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return self.name


class Instructor(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="instructor",
        help_text="Auth identity — required.",
    )
    display_name = models.CharField(max_length=255, help_text="Public name shown on class pages.")
    slug = models.SlugField(max_length=255, unique=True, help_text="URL slug for public profile.")
    bio = models.TextField(blank=True, help_text="Markdown-safe bio shown on profile.")
    photo = models.ImageField(upload_to="classes/instructors/", blank=True, help_text="Profile photo.")
    website = models.URLField(blank=True, help_text="Personal site.")
    social_handle = models.CharField(max_length=255, blank=True, help_text="e.g. @handle on primary social.")
    is_active = models.BooleanField(default=True, help_text="Inactive instructors hidden from public browse.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class ClassOffering(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending Review"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class SchedulingModel(models.TextChoices):
        FIXED = "fixed", "Fixed sessions"
        FLEXIBLE = "flexible", "Flexible (arrange with instructor)"

    title = models.CharField(max_length=255, help_text="Public class title.")
    slug = models.SlugField(max_length=255, unique=True, help_text="URL slug.")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="classes", help_text="Category grouping.")
    instructor = models.ForeignKey(Instructor, on_delete=models.PROTECT, related_name="classes", help_text="Assigned instructor.")
    description = models.TextField(blank=True, help_text="Class description — markdown-safe.")
    prerequisites = models.TextField(blank=True, help_text="What a student should know/own.")
    materials_included = models.TextField(blank=True, help_text="Included materials.")
    materials_to_bring = models.TextField(blank=True, help_text="What students must bring.")
    safety_requirements = models.TextField(blank=True, help_text="PPE or other safety requirements.")
    age_minimum = models.PositiveIntegerField(null=True, blank=True, help_text="Minimum age.")
    age_guardian_note = models.TextField(blank=True, help_text="Notes about minors / guardians.")
    price_cents = models.PositiveIntegerField(help_text="Full price in cents.")
    member_discount_pct = models.PositiveIntegerField(default=10, help_text="Auto-applied for verified members.")
    capacity = models.PositiveIntegerField(default=6, help_text="Maximum confirmed registrants.")
    scheduling_model = models.CharField(
        max_length=10, choices=SchedulingModel.choices, default=SchedulingModel.FIXED,
        help_text="Fixed scheduled sessions or flexible per-student scheduling.",
    )
    flexible_note = models.TextField(blank=True, help_text="Notes when scheduling_model=flexible.")
    is_private = models.BooleanField(default=False, help_text="Hidden from public portal; private registration only.")
    private_for_name = models.CharField(max_length=255, blank=True, help_text="Name shown when private.")
    recurring_pattern = models.CharField(max_length=255, blank=True, help_text="Free-text recurrence description.")
    image = models.ImageField(upload_to="classes/images/", blank=True, help_text="Hero image.")
    requires_model_release = models.BooleanField(default=False, help_text="When on, registrants also sign model release.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, help_text="Lifecycle status.")
    created_by = models.ForeignKey(
        Instructor, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Instructor who authored the class.",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Admin user who approved publication.",
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="Stamp on first publish.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClassOfferingQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def submit_for_review(self) -> None:
        if self.status != self.Status.DRAFT:
            raise ValueError(f"Only draft classes can be submitted; got {self.status}.")
        self.status = self.Status.PENDING
        self.save(update_fields=["status", "updated_at"])

    def approve(self, admin_user) -> None:
        if self.status != self.Status.PENDING:
            raise ValueError(f"Only pending classes can be approved; got {self.status}.")
        self.status = self.Status.PUBLISHED
        self.approved_by = admin_user
        self.published_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "published_at", "updated_at"])

    def archive(self) -> None:
        self.status = self.Status.ARCHIVED
        self.save(update_fields=["status", "updated_at"])


class ClassSession(models.Model):
    class_offering = models.ForeignKey(
        ClassOffering, on_delete=models.CASCADE, related_name="sessions",
        help_text="Parent class offering.",
    )
    starts_at = models.DateTimeField(help_text="Start (timezone-aware).")
    ends_at = models.DateTimeField(help_text="End (timezone-aware).")
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order within a class.")

    class Meta:
        ordering = ["starts_at"]
        constraints = [CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="session_ends_after_starts")]

    def __str__(self) -> str:
        return f"{self.class_offering.title} — {self.starts_at:%Y-%m-%d}"


class ClassSettings(models.Model):
    enabled_publicly = models.BooleanField(
        default=False,
        help_text="When False, /classes/ public routes return 404. Admin + instructor dashboards stay available.",
    )
    liability_waiver_text = models.TextField(help_text="Full liability waiver text shown to all registrants.")
    model_release_waiver_text = models.TextField(
        help_text="Full model-release waiver text shown when a class requires it."
    )
    default_member_discount_pct = models.PositiveIntegerField(
        default=10, help_text="Percent discount auto-applied to registrations from verified Members (0 = no discount)."
    )
    reminder_hours_before = models.PositiveIntegerField(
        default=24, help_text="Hours before a class session to send the reminder email."
    )
    instructor_approval_required = models.BooleanField(
        default=True, help_text="When on, new classes go to admin for review before being published."
    )
    mailchimp_api_key = models.CharField(max_length=255, blank=True, help_text="MailChimp API key for auto-subscribe.")
    mailchimp_list_id = models.CharField(
        max_length=255, blank=True, help_text="MailChimp list ID for class registrants."
    )
    google_analytics_measurement_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="GA4 measurement ID (e.g. G-XXXXXXX). Leave blank to disable GA tag.",
    )
    confirmation_email_footer = models.TextField(
        blank=True, help_text="Custom footer appended to confirmation emails."
    )

    class Meta:
        verbose_name = "Class Settings"
        verbose_name_plural = "Class Settings"

    def __str__(self) -> str:
        return "Class Settings"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "ClassSettings":
        obj, _created = cls.objects.get_or_create(
            pk=1,
            defaults={
                "liability_waiver_text": DEFAULT_LIABILITY_TEXT,
                "model_release_waiver_text": DEFAULT_MODEL_RELEASE_TEXT,
            },
        )
        return obj
