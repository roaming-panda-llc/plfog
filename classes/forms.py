"""Forms for the Classes app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from classes.models import Category, ClassOffering, ClassSettings, DiscountCode

if TYPE_CHECKING:
    from classes.models import Instructor


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


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "sort_order", "hero_image"]


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
            "mailchimp_api_key",
            "mailchimp_list_id",
            "google_analytics_measurement_id",
            "confirmation_email_footer",
        ]
        widgets = {
            "liability_waiver_text": forms.Textarea(attrs={"rows": 10}),
            "model_release_waiver_text": forms.Textarea(attrs={"rows": 10}),
            "confirmation_email_footer": forms.Textarea(attrs={"rows": 3}),
        }
