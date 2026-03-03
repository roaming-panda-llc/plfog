from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db import models


class Setting(models.Model):
    key = models.CharField(max_length=255, unique=True)
    value = models.JSONField(default=dict)
    type = models.CharField(max_length=20, default="text")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    @classmethod
    def get(cls, key: str, default: object = None) -> object:
        cache_key = f"setting.{key}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            setting = cls.objects.get(key=key)
            cache.set(cache_key, setting.value, 3600)
            return setting.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(
        cls,
        key: str,
        value: object,
        type: str = "text",
        updated_by_id: int | None = None,
    ) -> None:
        cls.objects.update_or_create(
            key=key,
            defaults={"value": value, "type": type, "updated_by_id": updated_by_id},
        )
        cache.delete(f"setting.{key}")
