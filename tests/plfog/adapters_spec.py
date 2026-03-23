"""BDD-style tests for plfog.adapters module — auto-admin, admin redirect, and signup gating."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from anymail.exceptions import AnymailRequestsAPIError
from django.contrib.auth.models import User
from django.test import RequestFactory, override_settings
from django.urls import reverse

from core.models import Invite, SiteConfiguration

pytestmark = pytest.mark.django_db


def _make_request_with_user(rf: RequestFactory, *, is_staff: bool, is_superuser: bool) -> object:
    """Create a GET request with an attached user having the given flags."""
    request = rf.get("/accounts/login/")
    user = MagicMock()
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    request.user = user
    return request


def describe_AdminRedirectAccountAdapter():
    def describe_login():
        def it_calls_maybe_grant_admin_then_super_login(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            user = MagicMock()
            user.email = "admin@example.com"
            user.is_staff = False
            user.is_superuser = False

            with patch.object(
                AdminRedirectAccountAdapter.__bases__[0],
                "login",
            ) as mock_super_login:
                adapter._maybe_grant_admin = MagicMock()  # type: ignore[method-assign]
                adapter.login(request, user)

                adapter._maybe_grant_admin.assert_called_once_with(user)
                mock_super_login.assert_called_once_with(request, user)

        def it_grants_admin_before_login_for_matching_domain(rf, settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")

            user = User.objects.create_user(
                username="admin",
                email="admin@example.com",
                password="testpass",
            )
            assert user.is_staff is False

            with patch.object(
                AdminRedirectAccountAdapter.__bases__[0],
                "login",
            ):
                adapter.login(request, user)

            user.refresh_from_db()
            assert user.is_staff is True
            assert user.is_superuser is True

    def describe_get_login_redirect_url():
        def it_redirects_staff_to_admin(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()
            request = _make_request_with_user(rf, is_staff=True, is_superuser=False)

            url = adapter.get_login_redirect_url(request)

            assert url == reverse("admin:index")

        def it_redirects_non_staff_to_hub(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()
            request = _make_request_with_user(rf, is_staff=False, is_superuser=False)

            url = adapter.get_login_redirect_url(request)

            assert url == reverse("hub_guild_voting")

        def it_redirects_staff_superuser_to_admin(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()
            request = _make_request_with_user(rf, is_staff=True, is_superuser=True)

            url = adapter.get_login_redirect_url(request)

            assert url == reverse("admin:index")

        def it_redirects_superuser_without_staff_to_hub(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()
            request = _make_request_with_user(rf, is_staff=False, is_superuser=True)

            url = adapter.get_login_redirect_url(request)

            assert url == reverse("hub_guild_voting")

        @override_settings(LOGIN_REDIRECT_URL="/dashboard/")
        def it_ignores_custom_url_for_staff(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()
            request = _make_request_with_user(rf, is_staff=True, is_superuser=False)

            url = adapter.get_login_redirect_url(request)

            assert url == reverse("admin:index")

    def describe_maybe_grant_admin():
        def it_sets_is_staff_and_is_superuser(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "admin@example.com"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            assert user.is_staff is True
            assert user.is_superuser is True
            user.save.assert_called_once_with(update_fields=["is_staff", "is_superuser"])

        def it_does_not_grant_admin_with_empty_admin_domains(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = []
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "user@example.com"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

        def it_does_not_grant_admin_when_domain_does_not_match(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "user@other.com"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

        def it_grants_admin_for_any_matching_domain(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["pastlives.space", "roaming-panda.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "mark@roaming-panda.com"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            assert user.is_staff is True
            assert user.is_superuser is True

        def it_matches_uppercase_email_domain(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["pastlives.space"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "User@PASTLIVES.SPACE"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            assert user.is_staff is True
            assert user.is_superuser is True

        def it_does_not_match_subdomains(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "user@sub.example.com"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

        def it_skips_save_when_user_already_has_admin_privileges(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "admin@example.com"
            user.is_staff = True
            user.is_superuser = True
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

        def it_upgrades_when_only_is_staff_is_true(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "admin@example.com"
            user.is_staff = True
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            assert user.is_staff is True
            assert user.is_superuser is True
            user.save.assert_called_once_with(update_fields=["is_staff", "is_superuser"])

        def it_upgrades_when_only_is_superuser_is_true(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "admin@example.com"
            user.is_staff = False
            user.is_superuser = True
            adapter._maybe_grant_admin(user)

            assert user.is_staff is True
            assert user.is_superuser is True
            user.save.assert_called_once_with(update_fields=["is_staff", "is_superuser"])

        def it_skips_user_with_empty_email(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = ""
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

        def it_skips_user_with_email_without_at_sign(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "noemail"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

        def it_skips_user_with_none_email(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = None
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

        def it_skips_when_admin_domains_not_configured(settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            if hasattr(settings, "ADMIN_DOMAINS"):
                delattr(settings, "ADMIN_DOMAINS")
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "user@example.com"
            user.is_staff = False
            user.is_superuser = False
            adapter._maybe_grant_admin(user)

            user.save.assert_not_called()

    def describe_maybe_grant_admin_logging():
        def it_logs_when_admin_is_granted(settings, caplog):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "admin@example.com"
            user.is_staff = False
            user.is_superuser = False

            with caplog.at_level(logging.INFO, logger="plfog.adapters"):
                adapter._maybe_grant_admin(user)

            assert "Auto-admin granted to admin@example.com" in caplog.text
            assert "domain: example.com" in caplog.text

        def it_does_not_log_when_already_admin(settings, caplog):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.ADMIN_DOMAINS = ["example.com"]
            adapter = AdminRedirectAccountAdapter()

            user = MagicMock()
            user.email = "admin@example.com"
            user.is_staff = True
            user.is_superuser = True

            with caplog.at_level(logging.INFO, logger="plfog.adapters"):
                adapter._maybe_grant_admin(user)

            assert "Auto-admin granted" not in caplog.text

    def describe_is_open_for_signup():
        def it_returns_true_in_open_mode(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            config = SiteConfiguration.load()
            config.registration_mode = SiteConfiguration.RegistrationMode.OPEN
            config.save()

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/accounts/signup/")
            assert adapter.is_open_for_signup(request) is True

        def it_returns_false_in_invite_only_with_no_invite(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            config = SiteConfiguration.load()
            config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
            config.save()

            adapter = AdminRedirectAccountAdapter()
            request = rf.post("/accounts/signup/", data={"email": "nobody@example.com"})
            assert adapter.is_open_for_signup(request) is False

        def it_returns_true_in_invite_only_with_valid_invite(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            config = SiteConfiguration.load()
            config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
            config.save()

            admin_user = User.objects.create_user(username="inviter", email="inviter@example.com", password="pass")
            Invite.objects.create(email="invited@example.com", invited_by=admin_user)

            adapter = AdminRedirectAccountAdapter()
            request = rf.post("/accounts/signup/", data={"email": "invited@example.com"})
            assert adapter.is_open_for_signup(request) is True

        def it_returns_false_for_accepted_invite(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            config = SiteConfiguration.load()
            config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
            config.save()

            admin_user = User.objects.create_user(username="inviter2", email="inviter2@example.com", password="pass")
            invite = Invite.objects.create(email="accepted@example.com", invited_by=admin_user)
            invite.mark_accepted()

            adapter = AdminRedirectAccountAdapter()
            request = rf.post("/accounts/signup/", data={"email": "accepted@example.com"})
            assert adapter.is_open_for_signup(request) is False

        def it_is_case_insensitive(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            config = SiteConfiguration.load()
            config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
            config.save()

            admin_user = User.objects.create_user(username="inviter3", email="inviter3@example.com", password="pass")
            Invite.objects.create(email="CasE@Example.COM", invited_by=admin_user)

            adapter = AdminRedirectAccountAdapter()
            request = rf.post("/accounts/signup/", data={"email": "case@example.com"})
            assert adapter.is_open_for_signup(request) is True

        def it_returns_false_with_no_email_in_request(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            config = SiteConfiguration.load()
            config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
            config.save()

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/accounts/signup/")
            assert adapter.is_open_for_signup(request) is False

        def it_checks_get_param_for_email(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            config = SiteConfiguration.load()
            config.registration_mode = SiteConfiguration.RegistrationMode.INVITE_ONLY
            config.save()

            admin_user = User.objects.create_user(username="inviter4", email="inviter4@example.com", password="pass")
            Invite.objects.create(email="getparam@example.com", invited_by=admin_user)

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/accounts/signup/?email=getparam@example.com")
            assert adapter.is_open_for_signup(request) is True

    def describe_pre_login():
        def it_marks_invite_accepted_on_signup(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            admin_user = User.objects.create_user(username="inviter5", email="inviter5@example.com", password="pass")
            invite = Invite.objects.create(email="newuser@example.com", invited_by=admin_user)

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            user = MagicMock()
            user.email = "newuser@example.com"

            with patch.object(
                AdminRedirectAccountAdapter.__bases__[0],
                "pre_login",
                return_value=None,
            ):
                adapter.pre_login(request, user, signup=True)

            invite.refresh_from_db()
            assert invite.accepted_at is not None

        def it_does_not_mark_invite_on_regular_login(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            admin_user = User.objects.create_user(username="inviter6", email="inviter6@example.com", password="pass")
            invite = Invite.objects.create(email="existing@example.com", invited_by=admin_user)

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            user = MagicMock()
            user.email = "existing@example.com"

            with patch.object(
                AdminRedirectAccountAdapter.__bases__[0],
                "pre_login",
                return_value=None,
            ):
                adapter.pre_login(request, user, signup=False)

            invite.refresh_from_db()
            assert invite.accepted_at is None

        def it_is_case_insensitive_for_invite_acceptance(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            admin_user = User.objects.create_user(username="inviter7", email="inviter7@example.com", password="pass")
            invite = Invite.objects.create(email="MixedCase@Example.COM", invited_by=admin_user)

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            user = MagicMock()
            user.email = "mixedcase@example.com"

            with patch.object(
                AdminRedirectAccountAdapter.__bases__[0],
                "pre_login",
                return_value=None,
            ):
                adapter.pre_login(request, user, signup=True)

            invite.refresh_from_db()
            assert invite.accepted_at is not None

        def it_handles_user_with_no_email_on_signup(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            user = MagicMock()
            user.email = ""

            with patch.object(
                AdminRedirectAccountAdapter.__bases__[0],
                "pre_login",
                return_value=None,
            ):
                adapter.pre_login(request, user, signup=True)  # Should not raise

    def describe_send_mail():
        def it_delegates_to_super_on_success(rf):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()

            with patch.object(
                AdminRedirectAccountAdapter.__bases__[0],
                "send_mail",
            ) as mock_super:
                adapter.send_mail("account/email/login_code", "user@example.com", {"code": "123456"})

                mock_super.assert_called_once_with("account/email/login_code", "user@example.com", {"code": "123456"})

        def it_catches_anymail_error_and_logs(rf, caplog):
            from plfog.adapters import AdminRedirectAccountAdapter

            adapter = AdminRedirectAccountAdapter()

            with (
                patch.object(
                    AdminRedirectAccountAdapter.__bases__[0],
                    "send_mail",
                    side_effect=AnymailRequestsAPIError("Resend API response 403"),
                ),
                caplog.at_level(logging.ERROR, logger="plfog.adapters"),
            ):
                adapter.send_mail("account/email/login_code", "user@example.com", {})

            assert "Failed to send email" in caplog.text
            assert "account/email/login_code" in caplog.text
            assert "user@example.com" in caplog.text
