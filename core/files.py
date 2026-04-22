"""Storage helpers for ImageField / FileField models."""

from __future__ import annotations

from django.db import models


def delete_orphan_on_replace(instance: models.Model, field_name: str) -> None:
    """Delete the storage file backing ``field_name`` when its value changes.

    Call from ``Model.save()`` BEFORE ``super().save()``. On update, fetches the
    pre-save value from the database and, if the user replaced or cleared the
    file, removes the old object from storage so it does not orphan in R2.

    Safe to call on creates (returns early) and when the field is unchanged.
    """
    if not instance.pk:
        return
    model = type(instance)
    try:
        old_instance = model._default_manager.only(field_name).get(pk=instance.pk)
    except model.DoesNotExist:  # type: ignore[attr-defined]
        return
    old_file = getattr(old_instance, field_name)
    new_file = getattr(instance, field_name)
    new_name = getattr(new_file, "name", "") or ""
    if old_file and old_file.name and old_file.name != new_name:
        old_file.delete(save=False)
