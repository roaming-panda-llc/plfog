"""BDD-style tests for TabEntry model."""

from decimal import Decimal

import pytest
from django.db import IntegrityError

from billing.models import TabEntry
from tests.billing.factories import TabChargeFactory, TabEntryFactory, TabFactory, UserFactory

pytestmark = pytest.mark.django_db


def describe_TabEntry():
    def it_has_str_representation():
        entry = TabEntryFactory(description="Laser cutter", amount=Decimal("15.00"))
        assert str(entry) == "Laser cutter ($15.00)"

    def it_defaults_to_manual_type():
        entry = TabEntryFactory()
        assert entry.entry_type == TabEntry.EntryType.MANUAL

    def it_enforces_positive_amount():
        with pytest.raises(IntegrityError):
            TabEntryFactory(amount=Decimal("0.00"))

    def it_enforces_strictly_positive_amount():
        with pytest.raises(IntegrityError):
            TabEntryFactory(amount=Decimal("-5.00"))

    def describe_is_pending():
        def it_is_true_for_uncharged_unvoided_entries():
            entry = TabEntryFactory()
            assert entry.is_pending is True

        def it_is_false_for_charged_entries():
            tab = TabFactory()
            charge = TabChargeFactory(tab=tab)
            entry = TabEntryFactory(tab=tab, tab_charge=charge)
            assert entry.is_pending is False

        def it_is_false_for_voided_entries():
            entry = TabEntryFactory()
            user = UserFactory()
            entry.void(user=user, reason="test")
            assert entry.is_pending is False

    def describe_is_voided():
        def it_is_false_by_default():
            entry = TabEntryFactory()
            assert entry.is_voided is False

        def it_is_true_after_voiding():
            entry = TabEntryFactory()
            user = UserFactory()
            entry.void(user=user, reason="test")
            assert entry.is_voided is True

    def describe_void():
        def it_sets_voided_fields():
            entry = TabEntryFactory()
            user = UserFactory()
            entry.void(user=user, reason="Duplicate charge")
            entry.refresh_from_db()
            assert entry.voided_at is not None
            assert entry.voided_by == user
            assert entry.voided_reason == "Duplicate charge"

        def it_raises_ValueError_when_already_voided():
            entry = TabEntryFactory()
            user = UserFactory()
            entry.void(user=user, reason="first")
            with pytest.raises(ValueError, match="already voided"):
                entry.void(user=user, reason="second")

        def it_raises_ValueError_when_already_charged():
            tab = TabFactory()
            charge = TabChargeFactory(tab=tab)
            entry = TabEntryFactory(tab=tab, tab_charge=charge)
            user = UserFactory()
            with pytest.raises(ValueError, match="already been charged"):
                entry.void(user=user, reason="too late")

    def describe_queryset():
        def it_filters_pending_entries():
            tab = TabFactory()
            pending = TabEntryFactory(tab=tab)
            charge = TabChargeFactory(tab=tab)
            TabEntryFactory(tab=tab, tab_charge=charge)  # charged
            voided = TabEntryFactory(tab=tab)
            user = UserFactory()
            voided.void(user=user, reason="test")

            result = TabEntry.objects.pending()
            assert list(result) == [pending]

        def it_filters_charged_entries():
            tab = TabFactory()
            TabEntryFactory(tab=tab)  # pending
            charge = TabChargeFactory(tab=tab)
            charged = TabEntryFactory(tab=tab, tab_charge=charge)

            result = TabEntry.objects.charged()
            assert list(result) == [charged]

        def it_filters_voided_entries():
            tab = TabFactory()
            TabEntryFactory(tab=tab)  # pending
            voided = TabEntryFactory(tab=tab)
            user = UserFactory()
            voided.void(user=user, reason="test")

            result = TabEntry.objects.voided()
            assert list(result) == [voided]
