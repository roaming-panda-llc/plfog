"""Custom managers / querysets for classes models.

The concrete ``ClassOfferingQuerySet`` lives in ``classes.models`` alongside the
model so django-stubs can resolve the manager type. This module re-exports it
for backwards compatibility with any callers still importing from here.
"""

from __future__ import annotations

from classes.models import ClassOfferingQuerySet

__all__ = ["ClassOfferingQuerySet"]
