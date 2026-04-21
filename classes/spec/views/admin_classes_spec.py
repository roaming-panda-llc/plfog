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


def describe_create_class():
    def it_creates_a_class(admin_user, client, db):
        from classes.factories import CategoryFactory, InstructorFactory

        client.force_login(admin_user)
        cat = CategoryFactory()
        inst = InstructorFactory()
        response = client.post(
            reverse("classes:admin_class_create"),
            {
                "title": "New Class",
                "slug": "new-class",
                "category": cat.pk,
                "instructor": inst.pk,
                "price_cents": 5000,
                "member_discount_pct": 10,
                "capacity": 6,
                "scheduling_model": "fixed",
                "description": "d",
                "prerequisites": "",
                "materials_included": "",
                "materials_to_bring": "",
                "safety_requirements": "",
                "age_guardian_note": "",
                "flexible_note": "",
                "private_for_name": "",
                "recurring_pattern": "",
            },
        )
        assert response.status_code == 302


def describe_approve_class():
    def it_transitions_pending_to_published(admin_user, client, db):
        from classes.factories import ClassOfferingFactory
        from classes.models import ClassOffering

        client.force_login(admin_user)
        offering = ClassOfferingFactory(status=ClassOffering.Status.PENDING)
        response = client.post(reverse("classes:admin_class_approve", kwargs={"pk": offering.pk}))
        assert response.status_code == 302
        offering.refresh_from_db()
        assert offering.status == ClassOffering.Status.PUBLISHED


def describe_archive_class():
    def it_archives_class(admin_user, client, db):
        from classes.factories import ClassOfferingFactory
        from classes.models import ClassOffering

        client.force_login(admin_user)
        offering = ClassOfferingFactory(status=ClassOffering.Status.PUBLISHED)
        response = client.post(reverse("classes:admin_class_archive", kwargs={"pk": offering.pk}))
        assert response.status_code == 302
        offering.refresh_from_db()
        assert offering.status == ClassOffering.Status.ARCHIVED


def describe_duplicate_class():
    def it_duplicates_as_draft(admin_user, client, db):
        from classes.factories import ClassOfferingFactory
        from classes.models import ClassOffering

        client.force_login(admin_user)
        src = ClassOfferingFactory(status=ClassOffering.Status.PUBLISHED)
        response = client.post(reverse("classes:admin_class_duplicate", kwargs={"pk": src.pk}))
        assert response.status_code == 302
        assert ClassOffering.objects.count() == 2
        copy = ClassOffering.objects.exclude(pk=src.pk).first()
        assert copy.status == ClassOffering.Status.DRAFT
        assert "copy" in copy.title.lower()
