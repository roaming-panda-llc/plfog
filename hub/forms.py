"""Forms for the member hub."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.conf import settings
from django.core.mail import send_mail

if TYPE_CHECKING:
    from django.contrib.auth.models import User

from membership.models import Guild, Member


class GuildEditForm(forms.ModelForm):
    """Edit form for a guild's public-facing fields, including calendar integration."""

    class Meta:
        model = Guild
        fields = ["name", "about", "banner_image", "calendar_url", "calendar_color"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Guild name"}),
            "about": forms.Textarea(
                attrs={"rows": 5, "placeholder": "Tell members what this guild is about..."},
            ),
            "calendar_url": forms.URLInput(attrs={"placeholder": "https://calendar.google.com/calendar/ical/..."}),
            "calendar_color": forms.TextInput(
                attrs={"type": "color", "class": "pl-color-input"},
            ),
        }
        labels = {
            "about": "About",
            "banner_image": "Banner image",
            "calendar_url": "Google Calendar iCal URL",
            "calendar_color": "Calendar Color",
        }
        help_texts = {
            "banner_image": "Shown at the top of the guild page. Max 5 MB.",
            "calendar_url": (
                "In Google Calendar → Settings → your calendar → 'Secret address in iCal format'. "
                "Leave blank if you don't use Google Calendar."
            ),
            "calendar_color": "Color used for your guild's events on the Community Calendar.",
        }


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
            "profile_photo",
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
            "profile_photo": "Profile photo",
        }
        help_texts = {
            "profile_photo": "Optional. Shown next to your name in the member directory. Max 5 MB.",
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
