"""Forms for the Classes app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils.text import slugify

from classes.models import Category, ClassOffering, ClassSession, ClassSettings, DiscountCode, Instructor

if TYPE_CHECKING:
    pass


class ClassOfferingForm(forms.ModelForm):
    class Meta:
        model = ClassOffering
        fields = [
            "title",
            "slug",
            "category",
            "instructor",
            "description",
            "prerequisites",
            "materials_included",
            "materials_to_bring",
            "safety_requirements",
            "age_minimum",
            "age_guardian_note",
            "price_cents",
            "member_discount_pct",
            "capacity",
            "scheduling_model",
            "flexible_note",
            "is_private",
            "private_for_name",
            "recurring_pattern",
            "image",
            "requires_model_release",
        ]


class InstructorClassOfferingForm(forms.ModelForm):
    """Class form for instructors — no `instructor`, no `is_private`, slug auto-generated."""

    class Meta:
        model = ClassOffering
        fields = [
            "title",
            "category",
            "description",
            "prerequisites",
            "materials_included",
            "materials_to_bring",
            "safety_requirements",
            "age_minimum",
            "age_guardian_note",
            "price_cents",
            "member_discount_pct",
            "capacity",
            "scheduling_model",
            "flexible_note",
            "recurring_pattern",
            "image",
            "requires_model_release",
        ]

    def __init__(self, *args, instructor: Instructor | None = None, **kwargs) -> None:
        self.instructor = instructor
        super().__init__(*args, **kwargs)

    def save(self, commit: bool = True) -> ClassOffering:
        offering = super().save(commit=False)
        if self.instructor is not None and not offering.instructor_id:
            offering.instructor = self.instructor
            if not offering.created_by_id:
                offering.created_by = self.instructor
        if not offering.slug:
            base = slugify(offering.title) or "class"
            slug = base
            n = 1
            while ClassOffering.objects.filter(slug=slug).exclude(pk=offering.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            offering.slug = slug
        if commit:
            offering.save()
        return offering


class InstructorProfileForm(forms.ModelForm):
    class Meta:
        model = Instructor
        fields = ["display_name", "bio", "photo", "website", "social_handle"]


class ClassSessionForm(forms.ModelForm):
    class Meta:
        model = ClassSession
        fields = ["starts_at", "ends_at"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean(self) -> dict:
        data = super().clean()
        starts_at = data.get("starts_at")
        ends_at = data.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            raise forms.ValidationError("Session end time must be after start time.")
        return data


ClassSessionFormSet = inlineformset_factory(
    ClassOffering,
    ClassSession,
    form=ClassSessionForm,
    extra=1,
    can_delete=True,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "sort_order", "hero_image"]


class PromoteUserToInstructorForm(forms.Form):
    """Promote an existing User (with any role except Guest) into an Instructor."""

    user = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        help_text="The user to promote. Members, admins, and staff can all be made instructors.",
    )
    display_name = forms.CharField(max_length=255, required=False, help_text="Defaults to the user's current name.")
    bio = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        from classes.models import Instructor

        User = get_user_model()
        already_instructors = Instructor.objects.values_list("user_id", flat=True)
        self.fields["user"].queryset = (
            User.objects.filter(is_active=True).exclude(pk__in=already_instructors).order_by("email")
        )

    def save(self) -> Instructor:
        from classes.models import Instructor

        user = self.cleaned_data["user"]
        display_name = (self.cleaned_data.get("display_name") or user.get_full_name() or user.email).strip()

        base_slug = slugify(display_name) or f"instructor-{user.pk}"
        slug = base_slug
        n = 1
        while Instructor.objects.filter(slug=slug).exists():
            n += 1
            slug = f"{base_slug}-{n}"

        return Instructor.objects.create(
            user=user,
            display_name=display_name,
            slug=slug,
            bio=self.cleaned_data.get("bio", ""),
        )


class InstructorInviteForm(forms.Form):
    display_name = forms.CharField(max_length=255)
    email = forms.EmailField()
    bio = forms.CharField(widget=forms.Textarea, required=False)

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower().strip()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists. Link them manually in Django admin.")
        return email

    def save(self) -> Instructor:
        from allauth.account.models import EmailAddress

        from classes.models import Instructor
        from membership.models import Member

        User = get_user_model()
        email = self.cleaned_data["email"]
        user = User.objects.create_user(username=email, email=email)
        user.set_unusable_password()
        user.save()
        EmailAddress.objects.update_or_create(
            user=user,
            email=email,
            defaults={"verified": True, "primary": True},
        )

        # The `ensure_user_has_member` signal auto-creates a Member on User save,
        # defaulting to Status.ACTIVE. For someone we're onboarding strictly as
        # an instructor, flip the placeholder Member to Status.INVITED so role
        # gates don't treat them as an active makerspace member.
        Member.objects.filter(user=user, status=Member.Status.ACTIVE).update(status=Member.Status.INVITED)

        base_slug = slugify(self.cleaned_data["display_name"]) or "instructor"
        slug = base_slug
        n = 1
        while Instructor.objects.filter(slug=slug).exists():
            n += 1
            slug = f"{base_slug}-{n}"

        return Instructor.objects.create(
            user=user,
            display_name=self.cleaned_data["display_name"],
            slug=slug,
            bio=self.cleaned_data.get("bio", ""),
        )


class DiscountCodeForm(forms.ModelForm):
    class Meta:
        model = DiscountCode
        fields = [
            "code",
            "description",
            "discount_pct",
            "discount_fixed_cents",
            "valid_from",
            "valid_until",
            "max_uses",
            "is_active",
        ]

    def clean(self) -> dict:
        data = super().clean()
        if not data.get("discount_pct") and not data.get("discount_fixed_cents"):
            raise forms.ValidationError("Set either a percent OR a fixed-cents discount.")
        return data


class ClassSettingsForm(forms.ModelForm):
    class Meta:
        model = ClassSettings
        fields = [
            "enabled_publicly",
            "liability_waiver_text",
            "model_release_waiver_text",
            "default_member_discount_pct",
            "reminder_hours_before",
            "instructor_approval_required",
            "confirmation_email_footer",
        ]
        widgets = {
            "liability_waiver_text": forms.Textarea(attrs={"rows": 10}),
            "model_release_waiver_text": forms.Textarea(attrs={"rows": 10}),
            "confirmation_email_footer": forms.Textarea(attrs={"rows": 3}),
        }
