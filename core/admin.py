"""Admin configuration for core app — site settings and invite management."""

from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from .models import Invite, SiteConfiguration


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(ModelAdmin):
    """Admin for the singleton SiteConfiguration model."""

    list_display = ["__str__", "registration_mode"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Prevent adding if the singleton already exists."""
        return not SiteConfiguration.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        """Never allow deleting the singleton."""
        return False


@admin.register(Invite)
class InviteAdmin(ModelAdmin):
    """Admin for managing email invitations."""

    list_display = ["email", "invited_by", "created_at", "accepted_at", "is_pending_display"]
    list_filter = ["accepted_at"]
    search_fields = ["email"]
    readonly_fields = ["invited_by", "created_at", "accepted_at"]

    @admin.display(description="Pending", boolean=True)
    def is_pending_display(self, obj: Invite) -> bool:
        """Show a boolean icon for pending status."""
        return obj.is_pending

    def get_queryset(self, request: HttpRequest) -> QuerySet[Invite]:
        return super().get_queryset(request).select_related("invited_by")

    def save_model(self, request: HttpRequest, obj: Invite, form: object, change: bool) -> None:
        """Set invited_by on create and send the invite email."""
        if not change:
            obj.invited_by = request.user  # type: ignore[assignment]
        super().save_model(request, obj, form, change)
        if not change:
            obj.send_invite_email()
