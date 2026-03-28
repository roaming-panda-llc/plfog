import pytest
from django.contrib.auth.models import User

from core.models import Invite, SiteConfiguration
from plfog.version import VERSION

pytestmark = pytest.mark.django_db


def describe_allauth_urls():
    def it_login_page_returns_200(client):
        response = client.get("/accounts/login/")
        assert response.status_code == 200

    def it_signup_page_returns_200(client):
        # Default is invite_only, so signup_closed is rendered
        response = client.get("/accounts/signup/")
        assert response.status_code == 200

    def it_login_page_uses_custom_template(client):
        response = client.get("/accounts/login/")
        template_names = [t.name for t in response.templates]
        assert "account/login.html" in template_names

    def it_signup_page_uses_custom_template_when_open(client):
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.OPEN
        config.save()

        response = client.get("/accounts/signup/")
        template_names = [t.name for t in response.templates]
        assert "account/signup.html" in template_names

    def it_login_page_does_not_contain_google_button(client):
        response = client.get("/accounts/login/")
        content = response.content.decode()
        assert "google" not in content.lower()
        assert "Continue with Google" not in content

    def it_login_page_shows_version_badge(client):
        response = client.get("/accounts/login/")
        content = response.content.decode()
        assert f"BETA v{VERSION}" in content

    def it_login_page_includes_changelog_modal(client):
        response = client.get("/accounts/login/")
        content = response.content.decode()
        assert "changelog-modal" in content
        assert "Launch Day" in content


def describe_signup_gating():
    def it_shows_signup_closed_page_in_invite_only_mode(client):
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
        config.save()

        response = client.get("/accounts/signup/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "invitation only" in content.lower()

    def it_shows_signup_form_in_open_mode(client):
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.OPEN
        config.save()

        response = client.get("/accounts/signup/")
        assert response.status_code == 200
        template_names = [t.name for t in response.templates]
        assert "account/signup.html" in template_names

    def it_hides_signup_link_on_login_page_when_invite_only(client):
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
        config.save()

        response = client.get("/accounts/login/")
        content = response.content.decode()
        assert "Sign up" not in content

    def it_shows_signup_link_on_login_page_when_open(client):
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.OPEN
        config.save()

        response = client.get("/accounts/login/")
        content = response.content.decode()
        assert "Sign up" in content

    def it_allows_signup_with_valid_invite_in_invite_only_mode(client):
        config = SiteConfiguration.load()
        config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
        config.save()

        admin_user = User.objects.create_user(username="inviter", email="inviter@example.com", password="pass")
        Invite.objects.create(email="invited@example.com", invited_by=admin_user)

        response = client.get("/accounts/signup/?email=invited@example.com")
        assert response.status_code == 200
        template_names = [t.name for t in response.templates]
        assert "account/signup.html" in template_names
