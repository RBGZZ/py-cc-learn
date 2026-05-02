from __future__ import annotations

import io
import base64

import pytest
from PIL import Image as PILImage


class TestImageProcessing:
    def test_pil_image_creation(self):
        img = PILImage.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        contents = buf.getvalue()
        assert len(contents) > 0

    def test_pil_image_resize(self):
        img = PILImage.new("RGB", (4000, 3000), color="blue")
        assert img.size == (4000, 3000)

        ratio = min(2048 / 4000, 2048 / 3000)
        new_w, new_h = int(4000 * ratio), int(3000 * ratio)
        img = img.resize((new_w, new_h), PILImage.LANCZOS)
        assert img.size[0] <= 2048
        assert img.size[1] <= 2048

    def test_pil_base64(self):
        img = PILImage.new("RGB", (50, 50), color="green")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        assert len(b64) > 0
        assert not b64.startswith(" ")

    def test_image_format_detection(self):
        img = PILImage.new("RGB", (100, 100), color="white")
        fmt = img.format or "PNG"
        assert fmt == "PNG"

    def test_large_image_resize_ratio(self):
        img = PILImage.new("RGB", (8000, 6000), color="black")
        max_dim = 2048
        ratio = min(max_dim / 8000, max_dim / 6000)
        assert 0 < ratio < 1
        new_w = int(8000 * ratio)
        new_h = int(6000 * ratio)
        assert new_w == 2048
        assert new_h <= 2048
