"""Forms for the Classes app."""

from __future__ import annotations

from django import forms

from classes.models import Category, ClassOffering


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
