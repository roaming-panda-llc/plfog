from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Setting


@admin.register(Setting)
class SettingAdmin(ModelAdmin):
    list_display = ["key", "type", "updated_by", "updated_at"]
    search_fields = ["key"]
    list_filter = ["type"]
    readonly_fields = ["created_at", "updated_at"]
