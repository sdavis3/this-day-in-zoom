"""Historical event research: scraping and fallback sources.

Primary: onthisday.com
Fallback: Wikipedia "On this day" via the Wikimedia API.
"""

from __future__ import annotations

import calendar
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("tdiz.history")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class HistoricalEvent:
    year: Optional[int]
    description: str
    source: str  # e.g., "onthisday.com" or "wikipedia"

    def __str__(self) -> str:
        prefix = f"{self.year}: " if self.year else ""
        return f"{prefix}{self.description}"


# ---------------------------------------------------------------------------
# Abstract source
# ---------------------------------------------------------------------------
class EventSource(ABC):
    @abstractmethod
    def fetch_events(self, month: int, day: int) -> list[HistoricalEvent]:
        """Return historical events for the given month/day."""
        ...


# ---------------------------------------------------------------------------
# onthisday.com
# ---------------------------------------------------------------------------
class OnThisDaySource(EventSource):
    """Scrape https://www.onthisday.com/day/{month}/{day}."""

    BASE_URL = "https://www.onthisday.com/day/{month}/{day}"
    TIMEOUT = 15.0
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def fetch_events(self, month: int, day: int) -> list[HistoricalEvent]:
        month_name = calendar.month_name[month].lower()
        url = self.BASE_URL.format(month=month_name, day=day)
        logger.debug("Fetching events from %s", url)

        try:
            resp = httpx.get(url, timeout=self.TIMEOUT, follow_redirects=True, headers=self.HEADERS)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("onthisday.com request failed: %s", exc)
            return []

        return self._parse_html(resp.text)

    @staticmethod
    def _parse_html(html: str) -> list[HistoricalEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events: list[HistoricalEvent] = []

        # onthisday.com uses <li> elements inside section containers.
        # Each event typically has a year in bold/link and descriptive text.
        for li in soup.select("ul.event-list li, section.event-list li, li.event"):
            text = li.get_text(separator=" ", strip=True)
            if not text:
                continue
            year, desc = _extract_year_and_desc(text)
            events.append(
                HistoricalEvent(year=year, description=desc, source="onthisday.com")
            )

        # Broader fallback: grab list items from content sections
        if not events:
            for li in soup.select(".content-list li, #events-list li, article li"):
                text = li.get_text(separator=" ", strip=True)
                if not text or len(text) < 10:
                    continue
                year, desc = _extract_year_and_desc(text)
                events.append(
                    HistoricalEvent(year=year, description=desc, source="onthisday.com")
                )

        # Final fallback: any <li> inside the main content
        if not events:
            for li in soup.find_all("li"):
                text = li.get_text(separator=" ", strip=True)
                if not text or len(text) < 20:
                    continue
                year, desc = _extract_year_and_desc(text)
                if year and 100 <= year <= 2100:
                    events.append(
                        HistoricalEvent(year=year, description=desc, source="onthisday.com")
                    )

        logger.info("Parsed %d events from onthisday.com", len(events))
        return events


# ---------------------------------------------------------------------------
# Wikipedia (Wikimedia REST API)
# ---------------------------------------------------------------------------
class WikipediaSource(EventSource):
    """Fetch events from the Wikipedia REST API 'On this day' endpoint."""

    # The en.wikipedia.org REST v1 endpoint is more permissive for anonymous access
    # than api.wikimedia.org, which aggressively rate-limits unregistered clients.
    BASE_URL = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/all/{month}/{day}"
    TIMEOUT = 15.0

    def fetch_events(self, month: int, day: int) -> list[HistoricalEvent]:
        url = self.BASE_URL.format(month=f"{month:02d}", day=f"{day:02d}")
        logger.debug("Fetching events from Wikipedia API: %s", url)

        try:
            resp = httpx.get(
                url,
                timeout=self.TIMEOUT,
                headers={"User-Agent": "ThisDayInZoom/1.0 (https://github.com/this-day-in-zoom)"},
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Wikipedia API request failed: %s", exc)
            return []

        return self._parse_response(resp.json())

    @staticmethod
    def _parse_response(data: dict) -> list[HistoricalEvent]:
        events: list[HistoricalEvent] = []

        # The API returns categories: "selected", "events", "births", "deaths", "holidays"
        # We prefer "selected" (curated) and "events" (general).
        for category in ("selected", "events"):
            for item in data.get(category, []):
                year = item.get("year")
                text = item.get("text", "")
                if text:
                    events.append(
                        HistoricalEvent(year=year, description=text, source="wikipedia")
                    )

        logger.info("Parsed %d events from Wikipedia", len(events))
        return events


# ---------------------------------------------------------------------------
# Composite source with fallback
# ---------------------------------------------------------------------------
class CompositeEventSource(EventSource):
    """Try sources in order, fall back if one returns no results."""

    def __init__(self, sources: Optional[list[EventSource]] = None) -> None:
        self.sources = sources or [OnThisDaySource(), WikipediaSource()]

    def fetch_events(self, month: int, day: int) -> list[HistoricalEvent]:
        for source in self.sources:
            try:
                events = source.fetch_events(month, day)
                if events:
                    return events
                logger.info("Source %s returned no events, trying next", type(source).__name__)
            except Exception as exc:
                logger.warning("Source %s failed: %s", type(source).__name__, exc)
                continue

        logger.error("All event sources failed for %02d-%02d", month, day)
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_YEAR_RE = re.compile(r"^(\d{1,4})\s*[-–—:]\s*")


def _extract_year_and_desc(text: str) -> tuple[Optional[int], str]:
    """Split a string like '1969 – Apollo 11 launched' into (1969, 'Apollo 11 launched')."""
    m = _YEAR_RE.match(text)
    if m:
        year = int(m.group(1))
        desc = text[m.end():].strip()
        return year, desc
    return None, text.strip()
