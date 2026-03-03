from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Document, Rentable, Rental, Tool, ToolReservation


class ToolReservationInline(TabularInline):
    model = ToolReservation
    fields = ["user", "starts_at", "ends_at", "status"]
    extra = 0


class RentableInline(TabularInline):
    model = Rentable
    fields = ["rental_period", "cost_per_period", "is_active"]
    extra = 0


@admin.register(Tool)
class ToolAdmin(ModelAdmin):
    list_display = ["name", "guild", "owner_type", "is_reservable", "is_rentable"]
    list_filter = ["owner_type", "is_reservable", "is_rentable", "guild"]
    search_fields = ["name"]
    inlines = [ToolReservationInline, RentableInline]


@admin.register(ToolReservation)
class ToolReservationAdmin(ModelAdmin):
    list_display = ["tool", "user", "starts_at", "ends_at", "status"]
    list_filter = ["status"]
    search_fields = ["tool__name", "user__username"]


@admin.register(Rentable)
class RentableAdmin(ModelAdmin):
    list_display = ["tool", "rental_period", "formatted_cost", "is_active"]
    list_filter = ["rental_period", "is_active"]

    @admin.display(description="Cost")
    def formatted_cost(self, obj: Rentable) -> str:
        return obj.formatted_cost


@admin.register(Rental)
class RentalAdmin(ModelAdmin):
    list_display = ["rentable", "user", "status", "checked_out_at", "due_at", "returned_at"]
    list_filter = ["status"]
    search_fields = ["rentable__tool__name", "user__username"]


@admin.register(Document)
class DocumentAdmin(ModelAdmin):
    list_display = ["name", "uploaded_by", "created_at"]
    search_fields = ["name"]
