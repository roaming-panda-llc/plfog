"""Auto-register every classes model with Django admin for full fallback coverage."""

from __future__ import annotations

from django.apps import apps
from django.contrib import admin


for model in apps.get_app_config("classes").get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
