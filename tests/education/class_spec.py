"""Tests for education models and admin."""

from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client

from education.admin import (
    ClassDiscountCodeAdmin,
    ClassImageAdmin,
    ClassSessionAdmin,
    MakerClassAdmin,
    StudentAdmin,
)
from education.models import ClassDiscountCode, ClassImage, ClassSession, MakerClass, Student
from tests.core.factories import UserFactory
from tests.education.factories import (
    ClassDiscountCodeFactory,
    ClassImageFactory,
    ClassSessionFactory,
    MakerClassFactory,
    StudentFactory,
)
from tests.membership.factories import GuildFactory

User = get_user_model()


# ---------------------------------------------------------------------------
# ClassDiscountCode
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_class_discount_code():
    def it_has_str_representation():
        code = ClassDiscountCodeFactory(code="SAVE20")
        assert str(code) == "SAVE20"

    def it_defaults_is_active_to_true():
        code = ClassDiscountCodeFactory()
        assert code.is_active is True

    def describe_calculate_discount():
        def it_calculates_percentage_discount():
            code = ClassDiscountCodeFactory(
                discount_type=ClassDiscountCode.DiscountType.PERCENTAGE,
                discount_value=Decimal("10.00"),
            )
            result = code.calculate_discount(Decimal("100.00"))
            assert result == Decimal("10.00")

        def it_calculates_fixed_discount():
            code = ClassDiscountCodeFactory(
                discount_type=ClassDiscountCode.DiscountType.FIXED,
                discount_value=Decimal("15.00"),
            )
            result = code.calculate_discount(Decimal("100.00"))
            assert result == Decimal("15.00")

        def it_caps_fixed_discount_at_price():
            code = ClassDiscountCodeFactory(
                discount_type=ClassDiscountCode.DiscountType.FIXED,
                discount_value=Decimal("200.00"),
            )
            result = code.calculate_discount(Decimal("50.00"))
            assert result == Decimal("50.00")

        def it_calculates_partial_percentage_discount():
            code = ClassDiscountCodeFactory(
                discount_type=ClassDiscountCode.DiscountType.PERCENTAGE,
                discount_value=Decimal("25.00"),
            )
            result = code.calculate_discount(Decimal("80.00"))
            assert result == Decimal("20.00")


# ---------------------------------------------------------------------------
# MakerClass
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_maker_class():
    def it_has_str_representation():
        maker_class = MakerClassFactory(name="Intro to Welding")
        assert str(maker_class) == "Intro to Welding"

    def it_defaults_status_to_draft():
        maker_class = MakerClassFactory()
        assert maker_class.status == MakerClass.Status.DRAFT

    def describe_is_published():
        def it_returns_false_when_draft():
            maker_class = MakerClassFactory(status=MakerClass.Status.DRAFT)
            assert maker_class.is_published is False

        def it_returns_true_when_published():
            maker_class = MakerClassFactory(status=MakerClass.Status.PUBLISHED)
            assert maker_class.is_published is True

        def it_returns_false_when_archived():
            maker_class = MakerClassFactory(status=MakerClass.Status.ARCHIVED)
            assert maker_class.is_published is False

    def describe_has_available_spots():
        def it_returns_true_when_max_students_is_null():
            maker_class = MakerClassFactory(max_students=None)
            assert maker_class.has_available_spots() is True

        def it_returns_true_when_spots_are_available():
            maker_class = MakerClassFactory(max_students=5)
            StudentFactory(maker_class=maker_class)
            StudentFactory(maker_class=maker_class)
            assert maker_class.has_available_spots() is True

        def it_returns_false_when_class_is_full():
            maker_class = MakerClassFactory(max_students=2)
            StudentFactory(maker_class=maker_class)
            StudentFactory(maker_class=maker_class)
            assert maker_class.has_available_spots() is False

    def it_has_guild_relationship():
        guild = GuildFactory(name="Woodworking Guild")
        maker_class = MakerClassFactory(guild=guild)
        maker_class.refresh_from_db()
        assert maker_class.guild == guild

    def it_allows_null_guild():
        maker_class = MakerClassFactory(guild=None)
        assert maker_class.guild is None

    def it_supports_m2m_instructors():
        maker_class = MakerClassFactory()
        instructor = UserFactory()
        maker_class.instructors.add(instructor)
        assert maker_class.instructors.filter(pk=instructor.pk).exists()

    def it_supports_m2m_discount_codes():
        maker_class = MakerClassFactory()
        code = ClassDiscountCodeFactory()
        maker_class.discount_codes.add(code)
        assert maker_class.discount_codes.filter(pk=code.pk).exists()


# ---------------------------------------------------------------------------
# ClassSession
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_class_session():
    def it_has_str_representation():
        maker_class = MakerClassFactory(name="Laser Cutting Basics")
        session = ClassSessionFactory(maker_class=maker_class)
        expected = f"Laser Cutting Basics - {session.starts_at.date()}"
        assert str(session) == expected

    def it_belongs_to_a_class():
        maker_class = MakerClassFactory()
        session = ClassSessionFactory(maker_class=maker_class)
        session.refresh_from_db()
        assert session.maker_class == maker_class


# ---------------------------------------------------------------------------
# ClassImage
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_class_image():
    def it_has_str_representation():
        maker_class = MakerClassFactory(name="3D Printing Workshop")
        image = ClassImageFactory(maker_class=maker_class, sort_order=2)
        assert str(image) == "Image for 3D Printing Workshop (#2)"

    def it_orders_by_sort_order():
        maker_class = MakerClassFactory()
        img_b = ClassImageFactory(maker_class=maker_class, sort_order=5)
        img_a = ClassImageFactory(maker_class=maker_class, sort_order=1)
        images = list(maker_class.images.all())
        assert images[0].pk == img_a.pk
        assert images[1].pk == img_b.pk


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_student():
    def it_has_str_representation():
        maker_class = MakerClassFactory(name="CNC Routing 101")
        student = StudentFactory(maker_class=maker_class, name="Jane Doe")
        assert str(student) == "Jane Doe - CNC Routing 101"

    def describe_is_member():
        def it_returns_true_when_user_is_set():
            user = UserFactory()
            student = StudentFactory(user=user)
            assert student.is_member is True

        def it_returns_false_when_user_is_null():
            student = StudentFactory(user=None)
            assert student.is_member is False

    def it_belongs_to_a_class():
        maker_class = MakerClassFactory()
        student = StudentFactory(maker_class=maker_class)
        student.refresh_from_db()
        assert student.maker_class == maker_class

    def it_stores_amount_paid():
        student = StudentFactory(amount_paid=Decimal("75.00"))
        student.refresh_from_db()
        assert student.amount_paid == Decimal("75.00")


# ---------------------------------------------------------------------------
# Admin registration
# ---------------------------------------------------------------------------


def describe_admin_registration():
    def it_registers_maker_class():
        assert MakerClass in admin.site._registry
        assert isinstance(admin.site._registry[MakerClass], MakerClassAdmin)

    def it_registers_class_session():
        assert ClassSession in admin.site._registry
        assert isinstance(admin.site._registry[ClassSession], ClassSessionAdmin)

    def it_registers_class_image():
        assert ClassImage in admin.site._registry
        assert isinstance(admin.site._registry[ClassImage], ClassImageAdmin)

    def it_registers_class_discount_code():
        assert ClassDiscountCode in admin.site._registry
        assert isinstance(admin.site._registry[ClassDiscountCode], ClassDiscountCodeAdmin)

    def it_registers_student():
        assert Student in admin.site._registry
        assert isinstance(admin.site._registry[Student], StudentAdmin)


# ---------------------------------------------------------------------------
# Admin changelist views (HTTP-level)
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="edu-admin-test",
        password="edu-admin-pw",
        email="edu-admin@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def describe_admin_maker_class_changelist():
    def it_loads_changelist(admin_client):
        MakerClassFactory(name="Changelist Class")
        resp = admin_client.get("/admin/education/makerclass/")
        assert resp.status_code == 200

    def it_loads_add_form(admin_client):
        resp = admin_client.get("/admin/education/makerclass/add/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_class_session_changelist():
    def it_loads_changelist(admin_client):
        ClassSessionFactory()
        resp = admin_client.get("/admin/education/classsession/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_class_image_changelist():
    def it_loads_changelist(admin_client):
        ClassImageFactory()
        resp = admin_client.get("/admin/education/classimage/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_class_discount_code_changelist():
    def it_loads_changelist(admin_client):
        ClassDiscountCodeFactory(code="TESTCODE")
        resp = admin_client.get("/admin/education/classdiscountcode/")
        assert resp.status_code == 200


@pytest.mark.django_db
def describe_admin_student_changelist():
    def it_loads_changelist(admin_client):
        StudentFactory()
        resp = admin_client.get("/admin/education/student/")
        assert resp.status_code == 200
