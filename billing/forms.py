"""Forms for billing admin operations."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms

from billing.models import BillingSettings, Product
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

    def clean(self) -> dict[str, Any]:
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


class BillingSettingsForm(forms.ModelForm):
    """Admin form for editing the BillingSettings singleton."""

    class Meta:
        model = BillingSettings
        fields = [
            "charge_frequency",
            "charge_time",
            "charge_day_of_week",
            "charge_day_of_month",
            "default_tab_limit",
            "max_retry_attempts",
            "retry_interval_hours",
        ]
        widgets = {
            "charge_frequency": forms.Select(),
            "charge_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean_default_tab_limit(self) -> Decimal:
        value: Decimal = self.cleaned_data["default_tab_limit"]
        if value < Decimal("0.00"):
            raise forms.ValidationError("Tab limit must be zero or positive.")
        return value


class ConnectPlatformSettingsForm(forms.ModelForm):
    """Admin form for editing the Stripe Connect platform credentials on BillingSettings.

    Lives separately from BillingSettingsForm so it can be POSTed independently
    from a dedicated card on the Settings tab.
    """

    class Meta:
        model = BillingSettings
        fields = [
            "connect_enabled",
            "connect_client_id",
            "connect_platform_publishable_key",
            "connect_platform_secret_key",
            "connect_platform_webhook_secret",
        ]
        widgets = {
            "connect_client_id": forms.TextInput(attrs={"placeholder": "ca_…", "autocomplete": "off"}),
            "connect_platform_publishable_key": forms.TextInput(attrs={"placeholder": "pk_…", "autocomplete": "off"}),
            "connect_platform_secret_key": forms.PasswordInput(
                render_value=True, attrs={"placeholder": "sk_…", "autocomplete": "off"}
            ),
            "connect_platform_webhook_secret": forms.PasswordInput(
                render_value=True, attrs={"placeholder": "whsec_…", "autocomplete": "off"}
            ),
        }

    def clean(self) -> dict:
        cleaned = super().clean() or {}
        if cleaned.get("connect_enabled"):
            missing = [
                field
                for field in (
                    "connect_client_id",
                    "connect_platform_publishable_key",
                    "connect_platform_secret_key",
                    "connect_platform_webhook_secret",
                )
                if not cleaned.get(field)
            ]
            for field in missing:
                self.add_error(field, "Required when Stripe Connect is enabled.")
        return cleaned
