"""End-to-end: a user can log in with a verified alias email.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""

from __future__ import annotations

import re

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client

User = get_user_model()


def describe_login_via_alias():
    def it_lets_user_log_in_with_verified_alias(db):
        user = User.objects.create_user(username="aliasuser", email="primary@example.com")
        EmailAddress.objects.create(user=user, email="alias@example.com", verified=True, primary=False)

        client = Client()
        mail.outbox = []

        response = client.post("/accounts/login/code/", {"email": "alias@example.com"}, follow=True)
        assert response.status_code == 200

        assert len(mail.outbox) >= 1
        sent = mail.outbox[-1]
        assert "alias@example.com" in sent.to
        # allauth >=65.15 formats codes as XXXX-XXXX; older versions used 6 alphanumerics.
        # Match the token on its own line after "is:" to stay version-agnostic.
        match = re.search(r"is:\s*\n\s*(\S+)", sent.body)
        assert match is not None, f"No login code in: {sent.body}"
        code = match.group(1)

        response = client.post("/accounts/login/code/confirm/", {"code": code}, follow=True)
        assert response.status_code == 200
        assert response.wsgi_request.user.is_authenticated
        assert response.wsgi_request.user.pk == user.pk
