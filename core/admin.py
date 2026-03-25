"""Admin configuration for core app — site settings."""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from unfold.admin import ModelAdmin

from .models import SiteConfiguration


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(ModelAdmin):
    """Admin for the singleton SiteConfiguration model."""

    list_display = ["__str__", "registration_mode"]
    fieldsets = [
        (
            None,
            {
                "fields": ["registration_mode"],
                "description": "Global settings that control how the site behaves. Changes take effect immediately.",
            },
        ),
    ]

    def has_module_permission(self, request: HttpRequest) -> bool:
        """Only FOG admins (superusers) can see site settings."""
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return request.user.is_superuser

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Prevent adding if the singleton already exists."""
        return request.user.is_superuser and not SiteConfiguration.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        """Never allow deleting the singleton."""
        return False

    def changelist_view(self, request: HttpRequest, extra_context: dict | None = None) -> HttpResponse:
        """Redirect the changelist straight to the singleton edit form."""
        from django.shortcuts import redirect

        config = SiteConfiguration.load()
        return redirect(f"/admin/core/siteconfiguration/{config.pk}/change/")
