"""BDD specs for the admin Settings tab."""

from __future__ import annotations

from django.urls import reverse


def describe_admin_settings():
    def it_shows_settings_form(admin_user, client, db):
        client.force_login(admin_user)
        response = client.get(reverse("classes:admin_settings"))
        assert response.status_code == 200
        assert b"Class Settings" in response.content

    def it_saves_settings(admin_user, client, db):
        client.force_login(admin_user)
        response = client.post(
            reverse("classes:admin_settings"),
            {
                "liability_waiver_text": "NEW LIABILITY TEXT",
                "model_release_waiver_text": "NEW MODEL RELEASE",
                "default_member_discount_pct": 15,
                "reminder_hours_before": 48,
                "confirmation_email_footer": "",
            },
        )
        assert response.status_code == 302
        from classes.models import ClassSettings

        settings_obj = ClassSettings.load()
        assert settings_obj.default_member_discount_pct == 15

    def it_gates_behind_admin_role(member_user, client, db):
        client.force_login(member_user)
        response = client.get(reverse("classes:admin_settings"))
        assert response.status_code == 403
