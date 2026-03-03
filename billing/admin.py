from __future__ import annotations

from django.contrib import admin

from unfold.admin import ModelAdmin

from .models import Invoice, MemberSubscription, Order, Payout, RevenueSplit, SubscriptionPlan


@admin.register(RevenueSplit)
class RevenueSplitAdmin(ModelAdmin):
    list_display = ["name", "notes", "created_at"]
    search_fields = ["name"]


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ["__str__", "user", "formatted_amount", "status", "issued_at"]
    list_filter = ["status"]
    search_fields = ["description", "user__username"]

    @admin.display(description="Amount")
    def formatted_amount(self, obj: Order) -> str:
        return obj.formatted_amount


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = ["__str__", "user", "formatted_amount_due", "formatted_amount_paid", "status", "issued_at"]
    list_filter = ["status"]
    search_fields = ["stripe_invoice_id", "user__username"]

    @admin.display(description="Amount Due")
    def formatted_amount_due(self, obj: Invoice) -> str:
        return obj.formatted_amount_due

    @admin.display(description="Amount Paid")
    def formatted_amount_paid(self, obj: Invoice) -> str:
        return obj.formatted_amount_paid


@admin.register(Payout)
class PayoutAdmin(ModelAdmin):
    list_display = ["__str__", "payee_type", "formatted_amount", "status", "period_start", "period_end"]
    list_filter = ["status", "payee_type"]

    @admin.display(description="Amount")
    def formatted_amount(self, obj: Payout) -> str:
        return obj.formatted_amount


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(ModelAdmin):
    list_display = ["name", "formatted_price", "interval", "plan_type", "is_active"]
    list_filter = ["interval", "is_active"]
    search_fields = ["name"]

    @admin.display(description="Price")
    def formatted_price(self, obj: SubscriptionPlan) -> str:
        return obj.formatted_price


@admin.register(MemberSubscription)
class MemberSubscriptionAdmin(ModelAdmin):
    list_display = ["user", "subscription_plan", "status", "starts_at", "next_billing_at"]
    list_filter = ["status"]
    search_fields = ["user__username", "subscription_plan__name"]
