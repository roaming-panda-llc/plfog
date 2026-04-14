"""Admin configuration for billing app."""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from unfold.admin import ModelAdmin, TabularInline

from membership.models import Guild

from .models import BillingSettings, Product, RevenueSplit, SplitRecipient, Tab, TabCharge, TabEntry


# ---------------------------------------------------------------------------
# BillingSettings (singleton)
# ---------------------------------------------------------------------------


@admin.register(BillingSettings)
class BillingSettingsAdmin(ModelAdmin):
    """Admin for the singleton BillingSettings model."""

    list_display = ["__str__", "charge_frequency", "default_tab_limit"]
    fieldsets = [
        (
            "Schedule",
            {
                "fields": ["charge_frequency", "charge_time", "charge_day_of_week", "charge_day_of_month"],
                "description": "Controls when the billing cycle runs. Changes take effect on the next cycle.",
            },
        ),
        (
            "Limits & Retries",
            {
                "fields": ["default_tab_limit", "max_retry_attempts", "retry_interval_hours"],
            },
        ),
    ]

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return request.user.is_superuser

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and not BillingSettings.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def changelist_view(self, request: HttpRequest, extra_context: dict | None = None) -> HttpResponse:
        """Redirect the changelist straight to the singleton edit form."""
        from django.shortcuts import redirect

        config = BillingSettings.load()
        return redirect(f"/admin/billing/billingsettings/{config.pk}/change/")


# ---------------------------------------------------------------------------
# Tab
# ---------------------------------------------------------------------------


class TabEntryInline(TabularInline):
    model = TabEntry
    extra = 0
    fields = ["description", "amount", "entry_type", "created_at", "voided_at"]
    readonly_fields = ["description", "amount", "entry_type", "created_at", "voided_at"]
    show_change_link = True
    max_num = 0  # No adding via inline — use the dedicated form

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).order_by("-created_at")[:20]

    def has_add_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(Tab)
class TabAdmin(ModelAdmin):
    list_display = ["member", "current_balance_display", "is_locked", "has_payment_method_display", "created_at"]
    list_filter = ["is_locked"]
    search_fields = ["member__full_legal_name", "member__preferred_name", "member___pre_signup_email"]
    readonly_fields = ["stripe_customer_id", "stripe_payment_method_id", "payment_method_last4", "payment_method_brand"]
    inlines = [TabEntryInline]

    fieldsets = [
        (
            None,
            {
                "fields": ["member", "tab_limit", "is_locked", "locked_reason"],
            },
        ),
        (
            "Stripe",
            {
                "fields": [
                    "stripe_customer_id",
                    "stripe_payment_method_id",
                    "payment_method_last4",
                    "payment_method_brand",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    @admin.display(description="Balance")
    def current_balance_display(self, obj: Tab) -> str:
        return f"${obj.current_balance}"

    @admin.display(description="Payment Method", boolean=True)
    def has_payment_method_display(self, obj: Tab) -> bool:
        return obj.has_payment_method


# ---------------------------------------------------------------------------
# TabEntry
# ---------------------------------------------------------------------------


@admin.register(TabEntry)
class TabEntryAdmin(ModelAdmin):
    list_display = ["description", "amount", "tab", "entry_type", "created_at", "voided_at"]
    list_filter = ["entry_type"]
    search_fields = ["description", "tab__member__full_legal_name", "tab__member__preferred_name"]
    readonly_fields = ["created_at"]

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


# ---------------------------------------------------------------------------
# TabCharge
# ---------------------------------------------------------------------------


@admin.register(TabCharge)
class TabChargeAdmin(ModelAdmin):
    list_display = ["tab", "amount", "status", "retry_count", "created_at", "charged_at"]
    list_filter = ["status"]
    search_fields = ["tab__member__full_legal_name", "tab__member__preferred_name"]
    readonly_fields = [
        "stripe_payment_intent_id",
        "stripe_charge_id",
        "stripe_receipt_url",
        "created_at",
        "charged_at",
        "receipt_sent_at",
    ]

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class SplitRecipientInline(TabularInline):
    model = SplitRecipient
    extra = 2
    fields = ["guild", "percent"]

    def get_formset(self, request: HttpRequest, obj: object = None, **kwargs: object):  # type: ignore[override]
        formset = super().get_formset(request, obj, **kwargs)
        from membership.models import Guild as _Guild

        formset.form.base_fields["guild"].queryset = _Guild.objects.filter(is_active=True).order_by("name")
        formset.form.base_fields["guild"].empty_label = "— Admin (Past Lives) —"
        return formset


@admin.register(RevenueSplit)
class RevenueSplitAdmin(ModelAdmin):
    list_display = ["__str__", "recipient_summary", "created_at"]
    inlines = [SplitRecipientInline]

    @admin.display(description="Recipients")
    def recipient_summary(self, obj: RevenueSplit) -> str:
        return ", ".join(str(r) for r in obj.recipients.all()) or "—"


_ADMIN_VALUE = "admin"
_NUM_SPLIT_SLOTS = 5


def _build_product_form_fields() -> dict[str, forms.Field]:
    """Build the (entity, percent) slot fields as class-level attributes.

    Django admin introspects fieldsets against the form class's declared
    fields, so dynamic fields added inside ``__init__`` are invisible to it.
    Declaring them at class level sidesteps that.
    """
    attrs: dict[str, forms.Field] = {}
    for i in range(_NUM_SPLIT_SLOTS):
        attrs[f"split_entity_{i}"] = forms.ChoiceField(
            choices=[("", "— none —"), (_ADMIN_VALUE, "Past Lives admin")],
            required=False,
            label=f"Recipient {i + 1}" if i else "Recipient",
        )
        attrs[f"split_percent_{i}"] = forms.DecimalField(
            max_digits=5,
            decimal_places=2,
            required=False,
            min_value=Decimal("0.00"),
            max_value=Decimal("100.00"),
            label="Percent",
            widget=forms.NumberInput(attrs={"step": "0.01"}),
        )
    return attrs


class ProductAdminForm(forms.ModelForm):
    """Product form with inline split recipient slots.

    Renders ``_NUM_SPLIT_SLOTS`` (entity, percent) pairs where entity is a
    dropdown of "Past Lives admin" + every active guild. Saves the
    ``RevenueSplit`` + ``SplitRecipient`` rows atomically with the product,
    so there's no "save the product first" step.
    """

    locals().update(_build_product_form_fields())

    class Meta:
        model = Product
        fields = ["name", "description", "is_active", "guild", "price"]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # Populate entity dropdowns with live guild list (queryset at import
        # time would be stale + break during migrations).
        entity_choices: list[tuple[str, str]] = [
            ("", "— none —"),
            (_ADMIN_VALUE, "Past Lives admin"),
        ]
        for g in Guild.objects.filter(is_active=True).order_by("name"):
            entity_choices.append((str(g.pk), g.name))
        for i in range(_NUM_SPLIT_SLOTS):
            self.fields[f"split_entity_{i}"].choices = entity_choices

        self._seed_initial()

    def _seed_initial(self) -> None:
        instance = self.instance
        if instance.pk and instance.revenue_split_id is not None:
            for i, r in enumerate(instance.revenue_split.recipients.order_by("pk")[:_NUM_SPLIT_SLOTS]):
                self.fields[f"split_entity_{i}"].initial = (
                    _ADMIN_VALUE if r.guild_id is None else str(r.guild_id)
                )
                self.fields[f"split_percent_{i}"].initial = r.percent
            return

        # New product defaults: Admin at site default %, remainder to the
        # pre-selected guild (via ?guild= query param or explicit initial).
        admin_percent = BillingSettings.load().default_admin_percent
        self.fields["split_entity_0"].initial = _ADMIN_VALUE
        self.fields["split_percent_0"].initial = admin_percent

        guild_pk = self.initial.get("guild") or instance.guild_id
        if guild_pk and admin_percent < Decimal("100"):
            self.fields["split_entity_1"].initial = str(guild_pk)
            self.fields["split_percent_1"].initial = Decimal("100.00") - admin_percent

    def clean(self) -> dict:
        cleaned = super().clean() or {}
        total = Decimal("0")
        seen: set[str] = set()
        any_row = False

        for i in range(_NUM_SPLIT_SLOTS):
            entity = cleaned.get(f"split_entity_{i}")
            percent = cleaned.get(f"split_percent_{i}")

            # Neither filled → ignore row entirely
            if not entity and percent in (None, ""):
                continue

            if not entity:
                self.add_error(f"split_entity_{i}", "Pick a recipient or clear the percent.")
                continue
            if percent is None or percent <= 0:
                self.add_error(f"split_percent_{i}", "Percent must be greater than 0.")
                continue
            if entity in seen:
                self.add_error(f"split_entity_{i}", "Duplicate recipient.")
                continue

            seen.add(entity)
            total += percent
            any_row = True

        if not any_row:
            raise ValidationError("Revenue split must have at least one recipient.")
        if total != Decimal("100"):
            raise ValidationError(f"Revenue split must sum to 100% (currently {total}%).")

        cleaned["_split_rows"] = [
            (
                cleaned[f"split_entity_{i}"],
                cleaned[f"split_percent_{i}"],
            )
            for i in range(_NUM_SPLIT_SLOTS)
            if cleaned.get(f"split_entity_{i}") and cleaned.get(f"split_percent_{i}")
        ]
        return cleaned

    def save(self, commit: bool = True) -> Product:
        product: Product = super().save(commit=False)

        # Ensure the product has a RevenueSplit before save() — otherwise the
        # model's auto-provision path would fire and create a default split
        # we'd have to immediately wipe.
        if product.revenue_split_id is None:
            product.revenue_split = RevenueSplit.objects.create()

        if commit:
            product.save()
            product.revenue_split.recipients.all().delete()
            for entity, percent in self.cleaned_data.get("_split_rows", []):
                guild_pk = None if entity == _ADMIN_VALUE else int(entity)
                SplitRecipient.objects.create(
                    split=product.revenue_split,
                    guild_id=guild_pk,
                    percent=percent,
                )
        return product


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    form = ProductAdminForm
    list_display = ["name", "guild_name", "price", "split_summary", "is_active"]
    list_filter = ["is_active", "guild"]
    search_fields = ["name", "guild__name"]

    fieldsets = [
        (
            "Product",
            {
                "fields": ["name", "description", "is_active"],
            },
        ),
        (
            "Guild",
            {
                "fields": ["guild"],
                "description": "The guild whose page this product appears on.",
            },
        ),
        (
            "Financial",
            {
                "fields": [
                    "price",
                    ("split_entity_0", "split_percent_0"),
                    ("split_entity_1", "split_percent_1"),
                    ("split_entity_2", "split_percent_2"),
                    ("split_entity_3", "split_percent_3"),
                    ("split_entity_4", "split_percent_4"),
                ],
                "description": "Price and how the money is split. Recipients must sum to 100%.",
            },
        ),
    ]

    def get_changeform_initial_data(self, request: HttpRequest) -> dict:
        """Prefill `guild` from the ``?guild=<pk>`` query param (used by the guild page)."""
        initial = super().get_changeform_initial_data(request)
        guild_pk = request.GET.get("guild")
        if guild_pk:
            initial["guild"] = guild_pk
        return initial

    @admin.display(description="Guild", ordering="guild__name")
    def guild_name(self, obj: Product) -> str:
        return obj.guild.name if obj.guild_id is not None else "—"

    @admin.display(description="Split")
    def split_summary(self, obj: Product) -> str:
        if obj.revenue_split_id is None:
            return "—"
        return ", ".join(str(r) for r in obj.revenue_split.recipients.all()) or "(empty)"
