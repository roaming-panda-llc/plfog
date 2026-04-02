"""BDD-style tests for billing-related forms."""

from __future__ import annotations

from decimal import Decimal

import pytest

from billing.forms import AdminAddTabEntryForm, VoidTabEntryForm
from hub.forms import AddTabEntryForm
from tests.billing.factories import ProductFactory
from tests.membership.factories import MemberFactory

pytestmark = pytest.mark.django_db


def describe_AddTabEntryForm():
    def it_is_valid_with_correct_data():
        form = AddTabEntryForm(data={"description": "Laser cutter", "amount": "15.00"})
        assert form.is_valid()

    def it_rejects_when_no_product_and_no_manual_fields():
        form = AddTabEntryForm(data={})
        assert not form.is_valid()
        assert form.non_field_errors()

    def it_rejects_zero_amount():
        form = AddTabEntryForm(data={"description": "Test", "amount": "0.00"})
        assert not form.is_valid()
        assert "amount" in form.errors

    def it_rejects_negative_amount():
        form = AddTabEntryForm(data={"description": "Test", "amount": "-5.00"})
        assert not form.is_valid()
        assert "amount" in form.errors

    def it_accepts_one_cent_minimum():
        form = AddTabEntryForm(data={"description": "Tiny", "amount": "0.01"})
        assert form.is_valid()
        assert form.cleaned_data["amount"] == Decimal("0.01")

    def it_is_valid_with_product_selection():
        product = ProductFactory(name="Wood glue", price=Decimal("3.00"))
        form = AddTabEntryForm(data={"product": product.pk})
        assert form.is_valid()

    def it_fills_description_and_amount_from_product():
        product = ProductFactory(name="Laser time", price=Decimal("12.50"))
        form = AddTabEntryForm(data={"product": product.pk})
        assert form.is_valid()
        assert form.cleaned_data["description"] == "Laser time"
        assert form.cleaned_data["amount"] == Decimal("12.50")


def describe_AdminAddTabEntryForm():
    def it_is_valid_with_correct_data():
        member = MemberFactory()
        form = AdminAddTabEntryForm(data={"member": member.pk, "description": "Admin charge", "amount": "50.00"})
        assert form.is_valid()

    def it_rejects_missing_member():
        form = AdminAddTabEntryForm(data={"description": "Test", "amount": "10.00"})
        assert not form.is_valid()
        assert "member" in form.errors

    def it_rejects_zero_amount():
        member = MemberFactory()
        form = AdminAddTabEntryForm(data={"member": member.pk, "description": "Test", "amount": "0.00"})
        assert not form.is_valid()

    def it_rejects_when_no_product_and_no_manual_fields():
        member = MemberFactory()
        form = AdminAddTabEntryForm(data={"member": member.pk})
        assert not form.is_valid()
        assert form.non_field_errors()

    def it_is_valid_with_product_selection():
        member = MemberFactory()
        product = ProductFactory(name="Resin print", price=Decimal("8.00"))
        form = AdminAddTabEntryForm(data={"member": member.pk, "product": product.pk})
        assert form.is_valid()

    def it_fills_description_and_amount_from_product():
        member = MemberFactory()
        product = ProductFactory(name="Plasma cutter", price=Decimal("25.00"))
        form = AdminAddTabEntryForm(data={"member": member.pk, "product": product.pk})
        assert form.is_valid()
        assert form.cleaned_data["description"] == "Plasma cutter"
        assert form.cleaned_data["amount"] == Decimal("25.00")


def describe_VoidTabEntryForm():
    def it_is_valid_with_reason():
        form = VoidTabEntryForm(data={"reason": "Duplicate charge"})
        assert form.is_valid()

    def it_rejects_empty_reason():
        form = VoidTabEntryForm(data={"reason": ""})
        assert not form.is_valid()
        assert "reason" in form.errors
