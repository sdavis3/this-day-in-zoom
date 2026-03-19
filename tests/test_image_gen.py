"""Tests for tdiz.image_gen — image optimization, filename generation, factory."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from tdiz.image_gen import (
    _save_and_optimize,
    generate_filename,
    get_image_generator,
)


class TestGenerateFilename:
    def test_basic_event(self):
        name = generate_filename(3, 18, "Apollo 11 Moon landing")
        assert name.startswith("tdiz_03-18_")
        assert name.endswith(".jpg")
        assert "apollo" in name
        assert " " not in name

    def test_special_characters_stripped(self):
        name = generate_filename(12, 25, "Wright Bros' First Flight! (Kitty Hawk)")
        assert "'" not in name
        assert "!" not in name
        assert "(" not in name

    def test_long_description_truncated(self):
        long_desc = "A" * 200
        name = generate_filename(1, 1, long_desc)
        # Slug portion should be capped
        assert len(name) < 100

    def test_date_padding(self):
        name = generate_filename(1, 5, "Event")
        assert "tdiz_01-05_" in name


class TestSaveAndOptimize:
    def _make_test_image(self, width=1920, height=1080) -> bytes:
        """Create a simple test image in memory."""
        img = Image.new("RGB", (width, height), color=(100, 150, 200))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_saves_jpeg(self, tmp_path):
        raw = self._make_test_image()
        out = tmp_path / "test.jpg"
        _save_and_optimize(raw, out)
        assert out.exists()
        # Verify it's a valid JPEG
        img = Image.open(out)
        assert img.format == "JPEG"
        assert img.size == (1920, 1080)

    def test_resizes_if_wrong_dimensions(self, tmp_path):
        raw = self._make_test_image(800, 600)
        out = tmp_path / "resized.jpg"
        _save_and_optimize(raw, out)
        img = Image.open(out)
        assert img.size == (1920, 1080)

    def test_converts_rgba_to_rgb(self, tmp_path):
        img = Image.new("RGBA", (1920, 1080), color=(100, 150, 200, 128))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        raw = buffer.getvalue()

        out = tmp_path / "rgba.jpg"
        _save_and_optimize(raw, out)
        result = Image.open(out)
        assert result.mode == "RGB"

    def test_creates_parent_dirs(self, tmp_path):
        raw = self._make_test_image()
        out = tmp_path / "deep" / "nested" / "dir" / "image.jpg"
        _save_and_optimize(raw, out)
        assert out.exists()


class TestGetImageGenerator:
    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown"):
            get_image_generator("dall-e")

    def test_openai_requires_key(self):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            get_image_generator("openai", openai_key=None)

    def test_flux_not_implemented(self):
        with pytest.raises(NotImplementedError):
            get_image_generator("flux", bfl_key="test")

    def test_sd_not_implemented(self):
        with pytest.raises(NotImplementedError):
            get_image_generator("sd")
