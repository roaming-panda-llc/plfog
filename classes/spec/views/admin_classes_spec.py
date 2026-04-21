"""BDD specs for admin classes tab — routing + gating."""

from __future__ import annotations

from django.urls import reverse


def describe_admin_classes_routing():
    def it_redirects_admin_root_to_classes(admin_user, client):
        client.force_login(admin_user)
        response = client.get(reverse("classes:admin_root"))
        assert response.status_code == 302
        assert response.url.endswith(reverse("classes:admin_classes"))

    def it_gates_tab_views_behind_admin_role(member_user, client):
        client.force_login(member_user)
        response = client.get(reverse("classes:admin_classes"))
        assert response.status_code == 403

    def it_renders_classes_tab_for_admin(admin_user, client):
        client.force_login(admin_user)
        response = client.get(reverse("classes:admin_classes"))
        assert response.status_code == 200
        assert b"Classes" in response.content
