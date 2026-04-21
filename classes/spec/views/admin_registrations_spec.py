"""BDD specs for the admin Registrations tab."""

from __future__ import annotations

from django.urls import reverse


def describe_admin_registrations():
    def it_lists_registrations(admin_user, client, db):
        from classes.factories import RegistrationFactory

        client.force_login(admin_user)
        RegistrationFactory(email="who@example.com")
        response = client.get(reverse("classes:admin_registrations"))
        assert response.status_code == 200
        assert b"who@example.com" in response.content

    def it_shows_registration_detail(admin_user, client, db):
        from classes.factories import RegistrationFactory

        client.force_login(admin_user)
        reg = RegistrationFactory(first_name="Alice")
        response = client.get(reverse("classes:admin_registration_detail", kwargs={"pk": reg.pk}))
        assert response.status_code == 200
        assert b"Alice" in response.content

    def it_cancels_registration(admin_user, client, db):
        from classes.factories import RegistrationFactory
        from classes.models import Registration

        client.force_login(admin_user)
        reg = RegistrationFactory(status=Registration.Status.CONFIRMED)
        response = client.post(
            reverse("classes:admin_registration_cancel", kwargs={"pk": reg.pk}),
            {"reason": "test"},
        )
        assert response.status_code == 302
        reg.refresh_from_db()
        assert reg.status == Registration.Status.CANCELLED

    def it_gates_behind_admin_role(member_user, client, db):
        client.force_login(member_user)
        response = client.get(reverse("classes:admin_registrations"))
        assert response.status_code == 403
