"""BDD specs for Waiver."""

from __future__ import annotations

import pytest
from django.db.utils import IntegrityError

from classes.factories import ClassOfferingFactory, RegistrationFactory
from classes.models import Waiver


def describe_Waiver():
    def it_stringifies_with_kind_and_registration(db):
        offering = ClassOfferingFactory()
        reg = RegistrationFactory(class_offering=offering)
        waiver = Waiver.objects.create(
            registration=reg,
            kind=Waiver.Kind.LIABILITY,
            waiver_text="text",
            signature_text="A B",
        )
        assert "liability" in str(waiver).lower()

    def it_enforces_unique_kind_per_registration(db):
        offering = ClassOfferingFactory()
        reg = RegistrationFactory(class_offering=offering)
        Waiver.objects.create(registration=reg, kind=Waiver.Kind.LIABILITY, waiver_text="t", signature_text="s")
        with pytest.raises(IntegrityError):
            Waiver.objects.create(registration=reg, kind=Waiver.Kind.LIABILITY, waiver_text="t", signature_text="s")
