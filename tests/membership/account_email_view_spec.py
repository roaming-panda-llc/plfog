"""Themed account_email view: members manage their own emails.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""
from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client

from tests.membership.factories import MembershipPlanFactory

User = get_user_model()


def describe_account_email_view():
    def it_requires_login(db):
        client = Client()
        response = client.get("/accounts/email/")
        assert response.status_code in (302, 401)

    def it_lists_user_email_addresses(db):
        MembershipPlanFactory()
        user = User.objects.create_user(username="u", email="primary@example.com")
        EmailAddress.objects.create(user=user, email="alias@example.com", verified=True, primary=False)

        client = Client()
        client.force_login(user)
        response = client.get("/accounts/email/")

        assert response.status_code == 200
        assert b"primary@example.com" in response.content
        assert b"alias@example.com" in response.content

    def it_renders_themed_template(db):
        MembershipPlanFactory()
        user = User.objects.create_user(username="u", email="primary@example.com")

        client = Client()
        client.force_login(user)
        response = client.get("/accounts/email/")

        assert response.status_code == 200
        assert b"Email Addresses - Past Lives" in response.content
        assert b"auth-page" in response.content
