"""BDD specs for the fix_unverified_emails management command."""

from __future__ import annotations

from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.management import call_command


@pytest.mark.django_db
def describe_fix_unverified_emails():
    def it_marks_unverified_records_as_verified():
        user = User.objects.create_user(username="u1", email="u1@example.com")
        EmailAddress.objects.create(user=user, email="u1@example.com", verified=False, primary=True)

        call_command("fix_unverified_emails")

        ea = EmailAddress.objects.get(email="u1@example.com")
        assert ea.verified is True

    def it_reports_zero_when_none_exist():
        out = StringIO()
        call_command("fix_unverified_emails", stdout=out)

        assert "No unverified" in out.getvalue()

    def it_does_not_modify_in_dry_run():
        user = User.objects.create_user(username="u2", email="u2@example.com")
        EmailAddress.objects.create(user=user, email="u2@example.com", verified=False, primary=True)

        out = StringIO()
        call_command("fix_unverified_emails", dry_run=True, stdout=out)

        ea = EmailAddress.objects.get(email="u2@example.com")
        assert ea.verified is False
        assert "DRY RUN" in out.getvalue()
