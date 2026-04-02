"""Forms for billing admin operations."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from billing.models import Product
from membership.models import Member


class AdminAddTabEntryForm(forms.Form):
    """Admin form for adding a charge to any member's tab."""

    member = forms.ModelChoiceField(
        queryset=Member.objects.filter(status=Member.Status.ACTIVE),
        label="Member",
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).select_related("guild"),
        required=False,
        empty_label="— Manual entry —",
        label="Product",
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "What is this charge for?"}),
        label="Description",
    )
    amount = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01"}),
        label="Amount ($)",
    )

    def clean(self) -> dict:
        cleaned = super().clean() or {}
        product = cleaned.get("product")
        if product:
            cleaned["description"] = product.name
            cleaned["amount"] = product.price
        elif not cleaned.get("description") or not cleaned.get("amount"):
            raise forms.ValidationError("Either select a product or enter a description and amount.")
        return cleaned


class VoidTabEntryForm(forms.Form):
    """Form for voiding a tab entry. Reason is required."""

    reason = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "Reason for voiding"}),
        label="Void Reason",
    )
