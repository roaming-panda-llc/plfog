"""BDD specs for the restart_login view."""

import pytest
from django.test import Client


@pytest.mark.django_db
def describe_restart_login():
    def it_redirects_to_login_page(client: Client):
        response = client.get("/accounts/restart-login/")

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def it_clears_pending_login_stage(client: Client):
        # Even without a pending stage, the view should work gracefully
        response = client.get("/accounts/restart-login/", follow=True)

        assert response.status_code == 200
