"""Seed allauth.account.EmailAddress rows from existing Member emails.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.

For every Member that has a linked User, this migration:
1. Creates a primary verified EmailAddress for Member._pre_signup_email
   (if one doesn't already exist).
2. Promotes each MemberEmail staging row into a verified non-primary
   EmailAddress.
3. Deletes the staging rows.

Reverse is lossy: it copies EmailAddress rows back into MemberEmail but
cannot distinguish rows that were originally staged from rows the user
added later. Documented as acceptable for staging rollback only.
"""

from typing import Any

from django.db import migrations


def forwards(apps: Any, schema_editor: Any) -> None:
    Member = apps.get_model("membership", "Member")
    MemberEmail = apps.get_model("membership", "MemberEmail")
    EmailAddress = apps.get_model("account", "EmailAddress")

    for member in Member.objects.filter(user__isnull=False).select_related("user"):
        user = member.user
        primary_value = (member._pre_signup_email or user.email or "").strip().lower()

        if primary_value:
            existing = EmailAddress.objects.filter(user=user, email__iexact=primary_value).first()
            if existing is None:
                # Unset any other primary first
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                EmailAddress.objects.create(user=user, email=primary_value, verified=True, primary=True)
            elif not existing.primary:
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                existing.primary = True
                existing.verified = True
                existing.save()

        for staging in MemberEmail.objects.filter(member=member):
            if not EmailAddress.objects.filter(user=user, email__iexact=staging.email).exists():
                EmailAddress.objects.create(user=user, email=staging.email, verified=True, primary=False)

        MemberEmail.objects.filter(member=member).delete()


def backwards(apps: Any, schema_editor: Any) -> None:
    """Lossy reverse: copy non-primary EmailAddress rows back into MemberEmail."""
    Member = apps.get_model("membership", "Member")
    MemberEmail = apps.get_model("membership", "MemberEmail")
    EmailAddress = apps.get_model("account", "EmailAddress")

    for member in Member.objects.filter(user__isnull=False).select_related("user"):
        for ea in EmailAddress.objects.filter(user=member.user, primary=False):
            MemberEmail.objects.get_or_create(member=member, email=ea.email)


class Migration(migrations.Migration):
    dependencies = [
        ("membership", "0021_drop_memberemail_is_primary"),
        ("account", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
