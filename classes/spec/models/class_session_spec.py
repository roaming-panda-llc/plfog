"""BDD specs for ClassSession."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db.utils import IntegrityError
from django.utils import timezone

from classes.factories import ClassOfferingFactory, ClassSessionFactory
from classes.models import ClassSession


def describe_ClassSession():
    def it_orders_by_starts_at(db):
        offering = ClassOfferingFactory()
        later = timezone.now() + timedelta(days=2)
        earlier = timezone.now() + timedelta(days=1)
        ClassSessionFactory(class_offering=offering, starts_at=later, ends_at=later + timedelta(hours=1))
        ClassSessionFactory(class_offering=offering, starts_at=earlier, ends_at=earlier + timedelta(hours=1))
        all_sessions = list(ClassSession.objects.all())
        assert all_sessions[0].starts_at == earlier

    def it_rejects_ends_before_starts(db):
        offering = ClassOfferingFactory()
        now = timezone.now()
        with pytest.raises(IntegrityError):
            ClassSession.objects.create(class_offering=offering, starts_at=now, ends_at=now - timedelta(minutes=1))

    def it_stringifies_with_class_and_date(db):
        offering = ClassOfferingFactory(title="Pottery")
        session = ClassSessionFactory(
            class_offering=offering,
            starts_at=timezone.now().replace(year=2026, month=5, day=10),
        )
        assert "Pottery" in str(session)
        assert "2026-05-10" in str(session)
