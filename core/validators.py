"""Reusable model-field validators."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile


def validate_image_size(image: UploadedFile) -> None:
    """Reject uploaded images larger than ``settings.MAX_UPLOAD_IMAGE_BYTES``."""
    limit = settings.MAX_UPLOAD_IMAGE_BYTES
    size = getattr(image, "size", None)
    if size is None or size <= limit:
        return
    limit_mb = limit / (1024 * 1024)
    size_mb = size / (1024 * 1024)
    raise ValidationError(f"Image must be {limit_mb:.1f} MB or smaller (got {size_mb:.1f} MB).")
