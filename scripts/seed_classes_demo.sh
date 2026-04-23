#!/usr/bin/env bash
# Enable the public classes portal and seed one demo class with an upcoming
# session, so /classes/ has something to render for visual review.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
exec .venv/bin/python manage.py shell <<'PY'
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from classes.models import (
    Category, ClassOffering, ClassSession, ClassSettings, Instructor,
)

settings_obj = ClassSettings.load()
settings_obj.enabled_publicly = True
settings_obj.save()
print(f"enabled_publicly: {settings_obj.enabled_publicly}")

User = get_user_model()
user, _ = User.objects.get_or_create(
    username="demo-instructor@example.com",
    defaults={"email": "demo-instructor@example.com"},
)
instructor, _ = Instructor.objects.get_or_create(
    user=user,
    defaults={
        "display_name": "Deenie",
        "slug": "deenie",
        "bio": "Working lampworker and longtime PLM instructor.",
        "social_handle": "@deenie",
    },
)

category, _ = Category.objects.get_or_create(
    slug="ceramics",
    defaults={"name": "Ceramics", "sort_order": 10},
)
category2, _ = Category.objects.get_or_create(
    slug="blacksmithing",
    defaults={"name": "Blacksmithing", "sort_order": 20},
)

demo, _ = ClassOffering.objects.get_or_create(
    slug="intro-to-wheel-throwing",
    defaults={
        "title": "Intro to Wheel Throwing",
        "category": category,
        "instructor": instructor,
        "description": "A two-session intro to throwing on the wheel — clay, tools, glaze, everything provided.",
        "prerequisites": "None — beginners welcome.",
        "materials_included": "Clay, tools, aprons, firing.",
        "price_cents": 12500,
        "member_discount_pct": 10,
        "capacity": 6,
        "status": ClassOffering.Status.PUBLISHED,
        "published_at": timezone.now(),
    },
)
if not demo.sessions.exists():
    for offset in (7, 14):
        start = timezone.now() + timedelta(days=offset, hours=2)
        ClassSession.objects.create(
            class_offering=demo,
            starts_at=start,
            ends_at=start + timedelta(hours=2, minutes=30),
        )
print(f"seeded class: {demo.title} — sessions: {demo.sessions.count()}")

flex, _ = ClassOffering.objects.get_or_create(
    slug="one-on-one-forging",
    defaults={
        "title": "One-on-One Forging Session",
        "category": category2,
        "instructor": instructor,
        "description": "Book a private forging session at a time that works for you.",
        "price_cents": 9500,
        "member_discount_pct": 10,
        "capacity": 1,
        "scheduling_model": ClassOffering.SchedulingModel.FLEXIBLE,
        "flexible_note": "Reach out after registering and we'll coordinate a time.",
        "status": ClassOffering.Status.PUBLISHED,
        "published_at": timezone.now(),
    },
)
print(f"seeded flex class: {flex.title}")
print("Done. Visit http://localhost:8000/classes/")
PY
