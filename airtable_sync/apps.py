from django.apps import AppConfig


class AirtableSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "airtable_sync"
    verbose_name = "Airtable Sync"
