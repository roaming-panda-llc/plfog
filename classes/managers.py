"""Custom managers / querysets for classes models."""

from __future__ import annotations

from django.db import models


class ClassOfferingQuerySet(models.QuerySet):
    def public(self) -> "ClassOfferingQuerySet":
        return self.filter(status="published")

    def pending_review(self) -> "ClassOfferingQuerySet":
        return self.filter(status="pending")

    def for_instructor(self, instructor) -> "ClassOfferingQuerySet":
        return self.filter(instructor=instructor)
