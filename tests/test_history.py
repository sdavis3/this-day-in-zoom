"""Tests for tdiz.history — event scraping, parsing, and fallback logic."""

from __future__ import annotations

import pytest

from tdiz.history import (
    CompositeEventSource,
    EventSource,
    HistoricalEvent,
    OnThisDaySource,
    WikipediaSource,
    _extract_year_and_desc,
)


class TestExtractYearAndDesc:
    def test_standard_dash(self):
        year, desc = _extract_year_and_desc("1969 – Apollo 11 launched")
        assert year == 1969
        assert desc == "Apollo 11 launched"

    def test_colon_separator(self):
        year, desc = _extract_year_and_desc("1776: US Declaration of Independence")
        assert year == 1776
        assert desc == "US Declaration of Independence"

    def test_no_year(self):
        year, desc = _extract_year_and_desc("Some event without a year")
        assert year is None
        assert desc == "Some event without a year"

    def test_em_dash(self):
        year, desc = _extract_year_and_desc("1945—End of World War II in Europe")
        assert year == 1945
        assert desc == "End of World War II in Europe"


class TestOnThisDaySourceParsing:
    """Test HTML parsing with fixture data (no network calls)."""

    SAMPLE_HTML = """
    <html><body>
    <ul class="event-list">
      <li>1969 – Apollo 11 became the first crewed mission to land on the Moon</li>
      <li>1889 – The Eiffel Tower officially opened in Paris</li>
      <li>1776 – The Continental Congress voted to approve independence</li>
    </ul>
    </body></html>
    """

    def test_parses_event_list(self):
        events = OnThisDaySource._parse_html(self.SAMPLE_HTML)
        assert len(events) == 3
        assert events[0].year == 1969
        assert "Apollo" in events[0].description
        assert events[0].source == "onthisday.com"

    def test_fallback_parsing(self):
        html = """
        <html><body>
        <div class="content-list">
          <li>1903 – Wright brothers' first powered flight at Kitty Hawk</li>
        </div>
        </body></html>
        """
        events = OnThisDaySource._parse_html(html)
        # The primary selector won't match, but the fallback should
        assert len(events) >= 1

    def test_empty_html(self):
        events = OnThisDaySource._parse_html("<html><body></body></html>")
        assert events == []


class TestWikipediaSourceParsing:
    SAMPLE_RESPONSE = {
        "selected": [
            {"year": 1969, "text": "Apollo 11 lands on the Moon"},
            {"year": 1889, "text": "Eiffel Tower opens to the public"},
        ],
        "events": [
            {"year": 1776, "text": "American colonies declare independence"},
        ],
        "births": [
            {"year": 1918, "text": "Nelson Mandela born"},
        ],
    }

    def test_parses_selected_and_events(self):
        events = WikipediaSource._parse_response(self.SAMPLE_RESPONSE)
        assert len(events) == 3  # 2 selected + 1 events (births excluded)
        assert events[0].source == "wikipedia"
        assert events[0].year == 1969

    def test_empty_response(self):
        events = WikipediaSource._parse_response({})
        assert events == []


class TestCompositeEventSource:
    def test_falls_back_to_second_source(self):
        class FailSource(EventSource):
            def fetch_events(self, m, d):
                return []

        class GoodSource(EventSource):
            def fetch_events(self, m, d):
                return [HistoricalEvent(1969, "Moon landing", "test")]

        composite = CompositeEventSource([FailSource(), GoodSource()])
        events = composite.fetch_events(7, 20)
        assert len(events) == 1
        assert events[0].year == 1969

    def test_uses_first_source_when_successful(self):
        class Source1(EventSource):
            def fetch_events(self, m, d):
                return [HistoricalEvent(2000, "Event A", "source1")]

        class Source2(EventSource):
            def fetch_events(self, m, d):
                return [HistoricalEvent(2001, "Event B", "source2")]

        composite = CompositeEventSource([Source1(), Source2()])
        events = composite.fetch_events(1, 1)
        assert events[0].source == "source1"

    def test_handles_exception_in_source(self):
        class BrokenSource(EventSource):
            def fetch_events(self, m, d):
                raise ConnectionError("Network down")

        class BackupSource(EventSource):
            def fetch_events(self, m, d):
                return [HistoricalEvent(1999, "Backup event", "backup")]

        composite = CompositeEventSource([BrokenSource(), BackupSource()])
        events = composite.fetch_events(3, 18)
        assert len(events) == 1
        assert events[0].source == "backup"

    def test_all_sources_fail(self):
        class FailSource(EventSource):
            def fetch_events(self, m, d):
                return []

        composite = CompositeEventSource([FailSource(), FailSource()])
        events = composite.fetch_events(1, 1)
        assert events == []
