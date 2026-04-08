"""Core app forms."""

from __future__ import annotations

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import send_mail

from django import forms
from django.db import models

from membership.models import Member


class FindAccountForm(forms.Form):
    """Look up a member by name and send a login link to the email on file."""

    name = forms.CharField(
        max_length=255,
        help_text="Enter your full legal name or preferred name.",
    )

    def send_login_email(self) -> None:
        """If a matching member exists, send a login link to their email on file."""
        name = self.cleaned_data["name"].strip()
        member = (
            Member.objects.filter(status=Member.Status.ACTIVE)
            .filter(
                models.Q(full_legal_name__iexact=name) | models.Q(preferred_name__iexact=name),
            )
            .first()
        )
        if member is None or not member._pre_signup_email:
            return

        current_site = Site.objects.get_current()
        protocol = "https" if not settings.DEBUG else "http"
        login_url = f"{protocol}://{current_site.domain}/accounts/login/"

        send_mail(
            subject="Your Past Lives Account",
            message=(
                f"Hi {member.preferred_name or member.full_legal_name},\n\n"
                f"Your account email is: {member._pre_signup_email}\n\n"
                f"You can log in here:\n{login_url}\n\n"
                f"If you didn't request this, you can safely ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member._pre_signup_email],
        )
