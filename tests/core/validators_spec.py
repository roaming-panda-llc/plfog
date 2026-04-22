"""BDD-style tests for core.validators."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from core.validators import validate_image_size


def describe_validate_image_size():
    def it_accepts_images_under_the_limit(settings):
        settings.MAX_UPLOAD_IMAGE_BYTES = 1024
        upload = SimpleUploadedFile("small.jpg", b"x" * 512, content_type="image/jpeg")

        assert validate_image_size(upload) is None

    def it_accepts_images_exactly_at_the_limit(settings):
        settings.MAX_UPLOAD_IMAGE_BYTES = 1024
        upload = SimpleUploadedFile("exact.jpg", b"x" * 1024, content_type="image/jpeg")

        assert validate_image_size(upload) is None

    def it_rejects_images_over_the_limit(settings):
        settings.MAX_UPLOAD_IMAGE_BYTES = 1024
        upload = SimpleUploadedFile("big.jpg", b"x" * 2048, content_type="image/jpeg")

        with pytest.raises(ValidationError) as exc_info:
            validate_image_size(upload)

        assert "MB or smaller" in str(exc_info.value)

    def it_accepts_objects_without_a_size_attribute():
        class Sizeless:
            name = "no_size.jpg"

        assert validate_image_size(Sizeless()) is None  # type: ignore[arg-type]
