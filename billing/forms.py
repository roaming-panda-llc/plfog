"""Forms for billing admin operations and tab-item entry."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django import forms

from billing.models import BillingSettings, Product
from membership.models import Guild, Member

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser

    from billing.exceptions import TabLimitExceededError, TabLockedError  # noqa: F401
    from billing.models import Tab, TabEntry

    UserLike = AbstractBaseUser | AnonymousUser | None


# Context values used by TabItemForm to select field set + editability.
CONTEXT_MEMBER_GUILD_PAGE = "member_guild_page"
CONTEXT_MEMBER_TAB_PAGE = "member_tab_page"
CONTEXT_ADMIN_DASHBOARD = "admin_dashboard"

VALID_CONTEXTS = {
    CONTEXT_MEMBER_GUILD_PAGE,
    CONTEXT_MEMBER_TAB_PAGE,
    CONTEXT_ADMIN_DASHBOARD,
}


def _user_can_edit_split(user: UserLike) -> bool:
    """True if user is a guild officer, fog admin, or Django superuser."""
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    member = getattr(user, "member", None)
    if member is None:
        return False
    return bool(getattr(member, "is_fog_admin", False) or getattr(member, "is_guild_officer", False))


class TabItemForm(forms.Form):
    """Unified tab-item entry form used in three contexts:

    1. ``member_guild_page`` — member quick-adds a charge on /guilds/<pk>/;
       guild is fixed to the current guild, no pickers.
    2. ``member_tab_page`` — member quick-adds on /tab/; product picker plus an
       optional manual entry path.
    3. ``admin_dashboard`` — admin quick-adds to any member's tab from
       /billing/admin/add-entry/; adds a member picker.

    Revenue splits live entirely on ``Product.revenue_split`` now. A manual
    (product-less) entry falls back to the implicit 100%-Admin split in
    ``Tab.add_entry``. The form no longer lets members tweak admin_percent
    or pick between SINGLE_GUILD/SPLIT_EQUALLY — that configuration happens
    once, per product, on the admin Product change page.
    """

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

    def __init__(
        self,
        *args: Any,
        context: str,
        user: "UserLike" = None,
        guild: Guild | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if context not in VALID_CONTEXTS:
            raise ValueError(f"Unknown TabItemForm context: {context}")
        self.context = context
        self.user = user
        self.fixed_guild = guild

        # Context-dependent fields
        if context == CONTEXT_ADMIN_DASHBOARD:
            self.fields["member"] = forms.ModelChoiceField(
                queryset=Member.objects.filter(status=Member.Status.ACTIVE),
                label="Member",
            )
            self.fields["product"] = forms.ModelChoiceField(
                queryset=Product.objects.filter(is_active=True).select_related("guild"),
                required=False,
                empty_label="— Manual entry —",
                label="Product",
            )
        elif context == CONTEXT_MEMBER_TAB_PAGE:
            self.fields["product"] = forms.ModelChoiceField(
                queryset=Product.objects.filter(is_active=True).select_related("guild"),
                required=False,
                empty_label="— Manual entry (no product) —",
                label="Product",
            )
        elif context == CONTEXT_MEMBER_GUILD_PAGE:
            if guild is None:
                raise ValueError("member_guild_page context requires guild=<Guild>")
            self.fields["description"].required = True
            self.fields["amount"].required = True

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        product = cleaned.get("product")
        if product is not None:
            cleaned["description"] = product.name
            cleaned["amount"] = product.price
        elif self.context != CONTEXT_MEMBER_GUILD_PAGE:
            if not cleaned.get("description") or not cleaned.get("amount"):
                raise forms.ValidationError("Either select a product or enter a description and amount.")
        return cleaned

    def apply_to_tab(
        self,
        tab: Tab,
        *,
        added_by: "UserLike",
        is_self_service: bool,
    ) -> TabEntry:
        """Add the entry to the tab using ``Tab.add_entry``.

        Raises ``TabLockedError`` or ``TabLimitExceededError`` — caller should
        catch and render.
        """
        if not self.is_valid():
            raise RuntimeError("call form.is_valid() before apply_to_tab()")
        return tab.add_entry(
            description=self.cleaned_data["description"],
            amount=self.cleaned_data["amount"],
            added_by=added_by,  # type: ignore[arg-type]
            is_self_service=is_self_service,
            product=self.cleaned_data.get("product"),
        )


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
            "default_admin_percent",
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
    """Admin form for editing the platform Stripe credentials on BillingSettings.

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
