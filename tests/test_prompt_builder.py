"""Tests for tdiz.prompt_builder — response parsing and selector factory."""

from __future__ import annotations

import json

import pytest

from tdiz.history import HistoricalEvent
from tdiz.prompt_builder import (
    SelectedEvent,
    _parse_selection,
    get_selector,
)


SAMPLE_EVENTS = [
    HistoricalEvent(1969, "Apollo 11 Moon landing", "test"),
    HistoricalEvent(1889, "Eiffel Tower opened", "test"),
    HistoricalEvent(1776, "US Declaration of Independence signed", "test"),
]


class TestParseSelection:
    def test_valid_json(self):
        raw = json.dumps({
            "year": 1889,
            "event": "Eiffel Tower opened in Paris",
            "rationale": "Iconic architecture with dramatic visual appeal",
            "image_prompt": "A wide 16:9 artistic painting of the Eiffel Tower at sunset",
        })
        result = _parse_selection(raw, SAMPLE_EVENTS, "test")
        assert isinstance(result, SelectedEvent)
        assert result.event.year == 1889
        assert "architecture" in result.rationale.lower()
        assert "16:9" in result.image_prompt

    def test_strips_markdown_fences(self):
        inner = json.dumps({
            "year": 1969,
            "event": "Moon landing",
            "rationale": "Space is visually stunning",
            "image_prompt": "A wide view of the lunar surface with Earth rising",
        })
        raw = f"```json\n{inner}\n```"
        result = _parse_selection(raw, SAMPLE_EVENTS, "test")
        assert result.event.year == 1969

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_selection("not json at all", SAMPLE_EVENTS, "test")

    def test_missing_image_prompt_raises(self):
        raw = json.dumps({
            "year": 1969,
            "event": "Moon landing",
            "rationale": "Cool event",
        })
        with pytest.raises(ValueError, match="image_prompt"):
            _parse_selection(raw, SAMPLE_EVENTS, "test")

    def test_unmatched_year_creates_new_event(self):
        raw = json.dumps({
            "year": 2000,
            "event": "Some event not in our list",
            "rationale": "Interesting",
            "image_prompt": "A futuristic cityscape",
        })
        result = _parse_selection(raw, SAMPLE_EVENTS, "test")
        assert result.event.year == 2000
        assert result.event.source == "llm-test"


class TestGetSelector:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            get_selector("gemini")

    def test_openai_requires_key(self):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            get_selector("openai", openai_key=None)

    def test_anthropic_requires_key(self):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            get_selector("anthropic", anthropic_key=None)
