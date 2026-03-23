"""Core app models for PWA push notification infrastructure and site configuration."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


class PushSubscription(models.Model):
    """Stores Web Push subscription data for a user."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=100)
    auth = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.email} - {self.endpoint[:50]}..."


class SiteConfiguration(models.Model):
    """Singleton model for site-wide settings like registration mode."""

    class RegistrationMode(models.TextChoices):
        OPEN = "open", "Open"
        INVITE_ONLY = "invite_only", "Invite Only"

    registration_mode = models.CharField(
        max_length=20,
        choices=RegistrationMode.choices,
        default=RegistrationMode.INVITE_ONLY,
        help_text="Whether new users can register freely or only via invite.",
    )

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self) -> str:
        return "Site Configuration"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Force singleton by always using pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> SiteConfiguration:
        """Load the singleton instance, creating it with defaults if needed."""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class Invite(models.Model):
    """Tracks email invitations sent by admins for invite-only registration."""

    email = models.EmailField(unique=True, help_text="Email address of the person being invited.")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The admin user who sent this invite.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the invite was created.")
    accepted_at = models.DateTimeField(null=True, blank=True, help_text="When the invite was accepted by signing up.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status = "pending" if self.is_pending else "accepted"
        return f"Invite for {self.email} ({status})"

    @property
    def is_pending(self) -> bool:
        """Return True if the invite has not been accepted yet."""
        return self.accepted_at is None

    def mark_accepted(self) -> None:
        """Mark this invite as accepted with the current timestamp."""
        self.accepted_at = timezone.now()
        self.save(update_fields=["accepted_at"])

    def send_invite_email(self) -> None:
        """Send a plaintext invite email with a signup link."""
        from django.contrib.sites.models import Site

        current_site = Site.objects.get_current()
        protocol = "https" if not settings.DEBUG else "http"
        signup_url = f"{protocol}://{current_site.domain}/accounts/signup/?email={self.email}"

        send_mail(
            subject="You're invited to Past Lives Makerspace",
            message=(
                f"You've been invited to join Past Lives Makerspace!\n\n"
                f"Click the link below to create your account:\n\n"
                f"{signup_url}\n\n"
                f"If you didn't expect this invite, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email],
        )
