"""BDD specs for the admin Instructors tab."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse


def describe_admin_instructors():
    def it_lists_instructors(admin_user, client, db):
        from classes.factories import InstructorFactory

        client.force_login(admin_user)
        InstructorFactory(display_name="Alice Teacher")
        response = client.get(reverse("classes:admin_instructors"))
        assert response.status_code == 200
        assert b"Alice Teacher" in response.content


def describe_instructor_invite():
    def it_creates_user_emailaddress_and_instructor(admin_user, client, db):
        client.force_login(admin_user)
        response = client.post(
            reverse("classes:admin_instructor_invite"),
            {
                "display_name": "Alice Teacher",
                "email": "alice@example.com",
                "bio": "Hello.",
            },
        )
        assert response.status_code == 302

        User = get_user_model()
        user = User.objects.get(email="alice@example.com")
        assert user.instructor.display_name == "Alice Teacher"

        from allauth.account.models import EmailAddress

        addr = EmailAddress.objects.get(user=user, email="alice@example.com")
        assert addr.verified is True
        assert addr.primary is True

    def it_refuses_duplicate_email(admin_user, client, db):
        client.force_login(admin_user)
        User = get_user_model()
        User.objects.create_user(username="existing@example.com", email="existing@example.com")
        response = client.post(
            reverse("classes:admin_instructor_invite"),
            {
                "display_name": "X",
                "email": "existing@example.com",
            },
        )
        assert response.status_code == 200
        assert b"already exists" in response.content

    def it_gates_behind_admin_role(member_user, client, db):
        client.force_login(member_user)
        response = client.get(reverse("classes:admin_instructor_invite"))
        assert response.status_code == 403

    def it_generates_unique_slug_when_display_name_collides(admin_user, client, db):
        from classes.factories import InstructorFactory
        from classes.models import Instructor

        client.force_login(admin_user)
        InstructorFactory(display_name="Alice Teacher", slug="alice-teacher")
        response = client.post(
            reverse("classes:admin_instructor_invite"),
            {
                "display_name": "Alice Teacher",
                "email": "alice2@example.com",
                "bio": "",
            },
        )
        assert response.status_code == 302
        slugs = set(Instructor.objects.values_list("slug", flat=True))
        assert "alice-teacher" in slugs
        assert "alice-teacher-2" in slugs
