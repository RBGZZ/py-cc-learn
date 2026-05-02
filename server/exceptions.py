from __future__ import annotations


class ImageSizeError(Exception):
    def __init__(self, size_bytes: int, max_size_bytes: int = 5 * 1024 * 1024):
        self.size_bytes = size_bytes
        self.max_size_bytes = max_size_bytes
        super().__init__(f"Image size {size_bytes} bytes exceeds maximum {max_size_bytes} bytes")


class ImageResizeError(Exception):
    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(f"Image resize failed: {message}")
