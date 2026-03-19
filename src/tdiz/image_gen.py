"""Pluggable AI image generation backends.

v1 ships with OpenAI GPT Image 1.
The abstract base class supports future providers (FLUX, SD, etc.).
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger("tdiz.image_gen")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB Zoom hard limit
TARGET_FILE_SIZE = 5 * 1024 * 1024  # 5 MB practical target
RETRY_COUNT = 2
BACKOFF_BASE = 3.0


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------
class ImageGenerator(ABC):
    @abstractmethod
    def generate(self, prompt: str, output_path: Path) -> Path:
        """Generate an image from the prompt and save to output_path.

        Returns the path to the saved file.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI GPT Image 1
# ---------------------------------------------------------------------------
class OpenAIImageGenerator(ImageGenerator):
    """Generate images using OpenAI's GPT Image 1 (gpt-image-1)."""

    MODEL = "gpt-image-1"

    def __init__(self, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)

    def generate(self, prompt: str, output_path: Path) -> Path:
        logger.info("Generating image with OpenAI %s", self.MODEL)
        logger.debug("Prompt: %s", prompt[:200])

        last_error: Optional[Exception] = None

        for attempt in range(1, RETRY_COUNT + 2):  # up to 3 total attempts
            try:
                response = self._client.images.generate(
                    model=self.MODEL,
                    prompt=prompt,
                    n=1,
                    size="1536x1024",
                    quality="high",
                )

                # GPT Image 1 returns base64 data
                image_data = response.data[0]

                if hasattr(image_data, "b64_json") and image_data.b64_json:
                    img_bytes = base64.b64decode(image_data.b64_json)
                    _save_and_optimize(img_bytes, output_path)
                elif hasattr(image_data, "url") and image_data.url:
                    import httpx
                    dl_resp = httpx.get(image_data.url, timeout=60.0)
                    dl_resp.raise_for_status()
                    _save_and_optimize(dl_resp.content, output_path)
                else:
                    raise RuntimeError("OpenAI returned neither b64_json nor url")

                logger.info("Image saved to %s", output_path)
                return output_path

            except Exception as exc:
                last_error = exc
                if attempt <= RETRY_COUNT:
                    wait = BACKOFF_BASE**attempt
                    logger.warning(
                        "Image generation attempt %d failed: %s. Retrying in %.0fs",
                        attempt,
                        exc,
                        wait,
                    )
                    time.sleep(wait)

        raise RuntimeError(
            f"Image generation failed after {RETRY_COUNT + 1} attempts"
        ) from last_error


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_image_generator(
    provider: str,
    openai_key: Optional[str] = None,
    bfl_key: Optional[str] = None,
) -> ImageGenerator:
    """Return the appropriate ImageGenerator for the configured provider."""
    if provider == "openai":
        if not openai_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI image generation")
        return OpenAIImageGenerator(openai_key)
    elif provider == "flux":
        raise NotImplementedError(
            "FLUX image generation is planned for a future release. "
            "Set --provider openai for now."
        )
    elif provider == "sd":
        raise NotImplementedError(
            "Stable Diffusion image generation is planned for a future release. "
            "Set --provider openai for now."
        )
    else:
        raise ValueError(f"Unknown image provider: {provider}")


# ---------------------------------------------------------------------------
# Image optimization helpers
# ---------------------------------------------------------------------------
def _save_and_optimize(raw_bytes: bytes, output_path: Path) -> None:
    """Save image bytes as JPEG, re-encoding at lower quality if too large."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(io.BytesIO(raw_bytes))

    # Ensure correct size
    if img.size != (TARGET_WIDTH, TARGET_HEIGHT):
        img = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)

    # Convert to RGB if necessary (strip alpha)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    # Save at quality 95 first
    for quality in (95, 85, 70):
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        size = buffer.tell()

        if size <= TARGET_FILE_SIZE:
            output_path.write_bytes(buffer.getvalue())
            logger.debug("Saved at quality=%d, size=%d bytes", quality, size)
            return

        if size <= MAX_FILE_SIZE and quality == 70:
            # Under Zoom hard limit but over our target — accept it
            output_path.write_bytes(buffer.getvalue())
            logger.warning(
                "Image is %d bytes (over 5MB target but under 15MB limit), quality=%d",
                size,
                quality,
            )
            return

    # Last resort: save at quality 50
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=50, optimize=True)
    output_path.write_bytes(buffer.getvalue())
    logger.warning("Image saved at quality=50, size=%d bytes", buffer.tell())


def generate_filename(month: int, day: int, event_desc: str) -> str:
    """Create a filename like tdiz_03-18_apollo-11-launched.jpg."""
    # Slugify the event description
    slug = event_desc.lower()[:60]
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"tdiz_{month:02d}-{day:02d}_{slug}.jpg"
