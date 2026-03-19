"""LLM-driven event selection and image prompt generation.

Supports OpenAI and Anthropic as pluggable backends.
Default: OpenAI when both keys are present.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from tdiz.history import HistoricalEvent

logger = logging.getLogger("tdiz.prompt_builder")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class SelectedEvent:
    event: HistoricalEvent
    rationale: str
    image_prompt: str


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
EVENT_SELECTION_SYSTEM = """You are an expert curator selecting historical events for AI-generated Zoom virtual backgrounds.

You will receive a list of historical events that occurred on a specific month and day. Select the single event that would produce the most visually impactful, artistic, and culturally significant image for a Zoom virtual background.

SELECTION CRITERIA (in priority order):
1. Strong visual elements — architecture, nature, exploration, invention, art, space, landmark moments.
2. Culturally significant and broadly recognizable.
3. Appropriate for a professional setting — avoid events that are primarily political text (treaty signings with no visual component), controversial, violent, or sensitive.
4. Interesting conversation starter — something that would make colleagues ask "what's your background today?"

RESPONSE FORMAT — reply with ONLY a JSON object, no markdown fencing:
{
  "year": <integer>,
  "event": "<short description of the selected event>",
  "rationale": "<1-2 sentences explaining why this event is visually compelling>",
  "image_prompt": "<detailed image generation prompt — see rules below>"
}

IMAGE PROMPT RULES:
- Describe a wide-format (16:9 aspect ratio) artistic scene inspired by the event.
- Use rich, vivid color and dramatic lighting appropriate to the subject.
- Avoid placing important visual elements in the center-bottom area (a person's silhouette will appear there).
- DO NOT include any text, lettering, numbers, or written words in the image.
- The style should be artistic and painterly, not photorealistic, unless photorealism strongly suits the subject.
- The scene should work at small scale (background behind a person's head/shoulders in a video call).
"""


def _build_user_prompt(month: int, day: int, events: list[HistoricalEvent]) -> str:
    """Build the user prompt listing events for the LLM to choose from."""
    lines = [f"Historical events that occurred on {month:02d}/{day:02d}:\n"]
    for i, ev in enumerate(events, 1):
        year_str = f"{ev.year}" if ev.year else "Unknown year"
        lines.append(f"{i}. [{year_str}] {ev.description}")
    lines.append(
        "\nSelect the best event for a Zoom virtual background and respond with the JSON object."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Abstract selector
# ---------------------------------------------------------------------------
class EventSelector(ABC):
    @abstractmethod
    def select_event(
        self, month: int, day: int, events: list[HistoricalEvent]
    ) -> SelectedEvent:
        ...


# ---------------------------------------------------------------------------
# OpenAI selector
# ---------------------------------------------------------------------------
class OpenAIEventSelector(EventSelector):
    """Use OpenAI GPT for event selection and prompt generation."""

    MODEL = "gpt-4o"

    def __init__(self, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)

    def select_event(
        self, month: int, day: int, events: list[HistoricalEvent]
    ) -> SelectedEvent:
        user_prompt = _build_user_prompt(month, day, events)
        logger.debug("Sending %d events to OpenAI for selection", len(events))

        response = self._client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": EVENT_SELECTION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        raw = response.choices[0].message.content or ""
        return _parse_selection(raw, events, "openai")


# ---------------------------------------------------------------------------
# Anthropic selector
# ---------------------------------------------------------------------------
class AnthropicEventSelector(EventSelector):
    """Use Anthropic Claude for event selection and prompt generation."""

    MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)

    def select_event(
        self, month: int, day: int, events: list[HistoricalEvent]
    ) -> SelectedEvent:
        user_prompt = _build_user_prompt(month, day, events)
        logger.debug("Sending %d events to Anthropic for selection", len(events))

        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=1000,
            system=EVENT_SELECTION_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = response.content[0].text if response.content else ""
        return _parse_selection(raw, events, "anthropic")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_selector(
    provider: str,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
) -> EventSelector:
    """Return the appropriate EventSelector for the configured provider."""
    if provider == "openai":
        if not openai_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI event selection")
        return OpenAIEventSelector(openai_key)
    elif provider == "anthropic":
        if not anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY required for Anthropic event selection")
        return AnthropicEventSelector(anthropic_key)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------
def _parse_selection(
    raw: str, events: list[HistoricalEvent], source: str
) -> SelectedEvent:
    """Parse the LLM JSON response into a SelectedEvent."""
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s\nRaw: %s", exc, raw[:500])
        raise ValueError(f"LLM ({source}) returned invalid JSON") from exc

    year = data.get("year")
    event_desc = data.get("event", "")
    rationale = data.get("rationale", "")
    image_prompt = data.get("image_prompt", "")

    if not image_prompt:
        raise ValueError(f"LLM ({source}) did not return an image_prompt")

    # Match to an original event if possible
    matched_event = None
    for ev in events:
        if ev.year == year:
            matched_event = ev
            break

    if matched_event is None:
        matched_event = HistoricalEvent(
            year=year, description=event_desc, source=f"llm-{source}"
        )

    return SelectedEvent(
        event=matched_event,
        rationale=rationale,
        image_prompt=image_prompt,
    )
