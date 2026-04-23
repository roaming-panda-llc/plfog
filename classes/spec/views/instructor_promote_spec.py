"""Specs for the Promote-existing-user-to-instructor flow."""

from __future__ import annotations

from django.urls import reverse

from classes.factories import InstructorFactory, UserFactory
from classes.models import Instructor


def describe_promote_existing_user():
    def it_creates_an_instructor_for_the_selected_user(admin_user, client, db):
        client.force_login(admin_user)
        target = UserFactory(username="promote-me@example.com")
        response = client.post(
            reverse("classes:admin_instructor_promote"),
            {"user": target.pk, "display_name": "New Teacher", "bio": ""},
        )
        assert response.status_code == 302
        assert Instructor.objects.filter(user=target, display_name="New Teacher").exists()

    def it_defaults_display_name_to_user_identity(admin_user, client, db):
        client.force_login(admin_user)
        target = UserFactory(username="wholename@example.com")
        response = client.post(
            reverse("classes:admin_instructor_promote"),
            {"user": target.pk, "display_name": "", "bio": ""},
        )
        assert response.status_code == 302
        inst = Instructor.objects.get(user=target)
        assert inst.display_name

    def it_excludes_existing_instructors_from_the_dropdown(admin_user, client, db):
        client.force_login(admin_user)
        existing = InstructorFactory(slug="already")
        response = client.get(reverse("classes:admin_instructor_promote"))
        assert response.status_code == 200
        form = response.context["form"]
        assert existing.user not in form.fields["user"].queryset

    def it_rejects_non_admin_non_instructor_users(member_user, client, db):
        client.force_login(member_user)
        response = client.get(reverse("classes:admin_instructor_promote"))
        assert response.status_code == 403
