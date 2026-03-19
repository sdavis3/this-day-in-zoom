"""Smoke tests for tdiz.cli — command invocation and argument parsing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tdiz.cli import app, _parse_date

runner = CliRunner()


class TestParseDate:
    def test_mm_dd(self):
        month, day = _parse_date("03-18")
        assert month == 3
        assert day == 18

    def test_mm_slash_dd(self):
        month, day = _parse_date("12/25")
        assert month == 12
        assert day == 25

    def test_yyyy_mm_dd_ignores_year(self):
        month, day = _parse_date("2024-07-04")
        assert month == 7
        assert day == 4

    def test_none_returns_today(self):
        from datetime import date
        month, day = _parse_date(None)
        today = date.today()
        assert month == today.month
        assert day == today.day

    def test_invalid_format_raises(self):
        import typer
        with pytest.raises(typer.BadParameter):
            _parse_date("not-a-date")

    def test_invalid_month_raises(self):
        import typer
        with pytest.raises(typer.BadParameter):
            _parse_date("13-01")


class TestVersionFlag:
    def test_version_output(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "tdiz v" in result.output


class TestListCommand:
    def test_missing_zoom_creds_errors(self, monkeypatch):
        """List command should fail gracefully when Zoom creds are missing."""
        for var in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"):
            monkeypatch.delenv(var, raising=False)

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "Zoom" in result.output


class TestGenerateCommand:
    def test_dry_run_missing_llm_key_errors(self, monkeypatch):
        """Dry run still needs an LLM key."""
        for var in (
            "ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)

        result = runner.invoke(app, ["generate", "--dry-run"])
        assert result.exit_code == 1

    def test_dry_run_with_openai_key(self, monkeypatch):
        """Dry run with valid key should reach the history step."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        for var in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"):
            monkeypatch.delenv(var, raising=False)

        # Mock the event source to avoid network calls
        mock_events = [
            MagicMock(year=1969, description="Moon landing", source="test")
        ]
        mock_selected = MagicMock(
            event=mock_events[0],
            rationale="Visually stunning",
            image_prompt="A wide view of the moon",
        )

        with patch("tdiz.history.CompositeEventSource") as MockSource, \
             patch("tdiz.prompt_builder.get_selector") as MockSelector:
            MockSource.return_value.fetch_events.return_value = mock_events
            MockSelector.return_value.select_event.return_value = mock_selected

            result = runner.invoke(app, ["generate", "--dry-run", "--date", "07-20"])

        assert result.exit_code == 0
        assert "dry run" in result.output.lower() or "moon" in result.output.lower()


class TestCleanupCommand:
    def test_missing_creds_errors(self, monkeypatch):
        for var in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"):
            monkeypatch.delenv(var, raising=False)
        result = runner.invoke(app, ["cleanup"])
        assert result.exit_code == 1


class TestScheduleCommand:
    def test_cron_output(self):
        result = runner.invoke(app, ["schedule", "--cron", "--time", "08:30"])
        assert result.exit_code == 0
        assert "30 8 * * *" in result.output

    def test_plist_output(self):
        result = runner.invoke(app, ["schedule", "--time", "09:00"])
        assert result.exit_code == 0
        assert "com.tdiz.generate" in result.output
