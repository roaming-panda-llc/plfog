"""Forms for the member hub."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.conf import settings
from django.core.mail import send_mail

if TYPE_CHECKING:
    from django.contrib.auth.models import User

from decimal import Decimal

from billing.models import Product
from membership.models import Guild, Member


class ProfileSettingsForm(forms.ModelForm):
    """Form for editing member profile fields."""

    class Meta:
        model = Member
        fields = [
            "preferred_name",
            "pronouns",
            "phone",
            "discord_handle",
            "other_contact_info",
            "about_me",
            "show_in_directory",
        ]
        widgets = {
            "preferred_name": forms.TextInput(attrs={"placeholder": "How should we call you?"}),
            "phone": forms.TextInput(attrs={"placeholder": "(optional)"}),
            "discord_handle": forms.TextInput(attrs={"placeholder": "@username"}),
            "other_contact_info": forms.TextInput(attrs={"placeholder": "Instagram, Signal, etc."}),
            "about_me": forms.Textarea(attrs={"rows": 3, "placeholder": "Tell other members a bit about yourself..."}),
        }
        labels = {
            "show_in_directory": "Show me in the member directory",
            "discord_handle": "Discord",
            "other_contact_info": "Other contact info",
            "about_me": "About me",
        }


class EmailPreferencesForm(forms.Form):
    """Form for email notification preferences."""

    voting_results = forms.BooleanField(required=False, label="Voting Result Emails")


class BetaFeedbackForm(forms.Form):
    """Form for submitting beta feedback (bug reports, feature requests, general feedback)."""

    CATEGORY_CHOICES = [
        ("bug", "Bug Report"),
        ("feature", "Feature Request"),
        ("feedback", "General Feedback"),
    ]

    category = forms.ChoiceField(choices=CATEGORY_CHOICES, label="Category")
    subject = forms.CharField(max_length=200, label="Subject")
    message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 6, "placeholder": "Describe your issue or idea..."}), label="Message"
    )

    def send(self, *, user: User) -> None:
        """Send the feedback email to the configured recipients."""
        category_label = dict(self.CATEGORY_CHOICES)[self.cleaned_data["category"]]
        subject = f"[Beta {category_label}] {self.cleaned_data['subject']}"
        body = (
            f"From: {user.get_full_name() or user.email} ({user.email})\n"
            f"Category: {category_label}\n\n"
            f"{self.cleaned_data['message']}"
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=settings.BETA_FEEDBACK_EMAILS,
        )


class VotePreferenceForm(forms.Form):
    """Form for submitting or updating a member's persistent guild vote preferences."""

    guild_1st = forms.ModelChoiceField(
        queryset=Guild.objects.filter(is_active=True),
        label="1st Choice (5 pts)",
        empty_label="-- Select a guild --",
    )
    guild_2nd = forms.ModelChoiceField(
        queryset=Guild.objects.filter(is_active=True),
        label="2nd Choice (3 pts)",
        empty_label="-- Select a guild --",
    )
    guild_3rd = forms.ModelChoiceField(
        queryset=Guild.objects.filter(is_active=True),
        label="3rd Choice (2 pts)",
        empty_label="-- Select a guild --",
    )

    def clean(self) -> dict:
        """Validate that all three guild choices are distinct."""
        cleaned: dict = super().clean() or {}
        g1 = cleaned.get("guild_1st")
        g2 = cleaned.get("guild_2nd")
        g3 = cleaned.get("guild_3rd")

        if g1 and g2 and g3:
            choices = [g1, g2, g3]
            if len(set(g.pk for g in choices)) != 3:
                raise forms.ValidationError("Please select three different guilds.")

        return cleaned


class GuildPageForm(forms.ModelForm):
    """Form for guild leads to edit their guild's member-facing about/announcement text."""

    class Meta:
        model = Guild
        fields = ["about"]
        widgets = {
            "about": forms.Textarea(attrs={"rows": 6, "placeholder": "Tell members what your guild is about..."}),
        }
        labels = {"about": "About / Announcements"}


class GuildProductForm(forms.ModelForm):
    """Form for guild leads to add or edit a product offered by their guild."""

    class Meta:
        model = Product
        fields = ["name", "price"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Laser Cutter — 30 min"}),
            "price": forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01", "min": "0.01"}),
        }
        labels = {"name": "Product name", "price": "Price ($)"}

    def clean_price(self) -> Decimal:
        price: Decimal = self.cleaned_data["price"]
        if price <= Decimal("0"):
            raise forms.ValidationError("Price must be greater than zero.")
        return price


class AddTabEntryForm(forms.Form):
    """Self-service form for members to add items to their own tab."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).select_related("guild"),
        required=False,
        empty_label="— Manual entry (no product) —",
        label="Product",
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "What is this charge for?"}),
        label="Description",
    )
    amount = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01"}),
        label="Amount ($)",
    )

    def clean(self) -> dict:
        cleaned = super().clean() or {}
        product = cleaned.get("product")
        if product:
            cleaned["description"] = product.name
            cleaned["amount"] = product.price
        elif not cleaned.get("description") or not cleaned.get("amount"):
            raise forms.ValidationError("Either select a product or enter a description and amount.")
        return cleaned
