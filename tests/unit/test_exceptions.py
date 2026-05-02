from __future__ import annotations

import pytest
from server.exceptions import ImageSizeError, ImageResizeError


class TestImageExceptions:
    def test_image_size_error(self):
        exc = ImageSizeError(size_bytes=6_000_000, max_size_bytes=5_000_000)
        assert exc.size_bytes == 6_000_000
        assert exc.max_size_bytes == 5_000_000
        assert "6000000" in str(exc)

    def test_image_resize_error(self):
        original = ValueError("bad image")
        exc = ImageResizeError("Failed to scale", original_error=original)
        assert exc.original_error is original
        assert "Failed to scale" in str(exc)

    def test_image_size_error_default(self):
        exc = ImageSizeError(size_bytes=10_000_000)
        assert exc.max_size_bytes == 5 * 1024 * 1024
