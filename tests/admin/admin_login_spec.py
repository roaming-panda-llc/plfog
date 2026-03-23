import pytest

pytestmark = pytest.mark.django_db


def describe_admin_login_page():
    def it_returns_200(client):
        response = client.get("/admin/login/")
        assert response.status_code == 200

    def it_does_not_contain_google_sign_in_link(client):
        response = client.get("/admin/login/")
        content = response.content.decode()
        assert "/accounts/google/login/" not in content
        assert "Sign in with Google" not in content

    def it_contains_password_form(client):
        response = client.get("/admin/login/")
        content = response.content.decode()
        assert 'id="login-form"' in content
        assert 'type="password"' in content

    def it_contains_email_code_link(client):
        response = client.get("/admin/login/")
        content = response.content.decode()
        assert "/accounts/login/code/?next=/admin/" in content
