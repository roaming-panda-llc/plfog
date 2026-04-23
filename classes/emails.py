"""Outbound class-related emails."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

if TYPE_CHECKING:
    from classes.models import ClassSession, Registration


def send_reminder_email(registration: "Registration", session: "ClassSession") -> None:
    """Email a registrant a reminder for an upcoming session.

    Plain-text body for v1; HTML email templates land in Plan 2 email polish.
    """
    offering = session.class_offering
    context = {
        "registration": registration,
        "session": session,
        "offering": offering,
        "self_serve_url": f"/classes/my/{registration.self_serve_token}/",
    }
    body = render_to_string("classes/emails/reminder.txt", context)
    subject = f"Reminder: {offering.title} — {session.starts_at:%a %b %-d at %-I:%M %p}"
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[registration.email],
        fail_silently=False,
    )
