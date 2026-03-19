"""Tests for tdiz.scheduler — launchd plist and cron entry generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tdiz.scheduler import (
    generate_cron_entry,
    generate_launchd_plist,
    get_install_instructions,
    install_launchd_plist,
)


class TestGenerateLaunchdPlist:
    def test_contains_label(self):
        plist = generate_launchd_plist(hour=7, minute=0)
        assert "com.tdiz.generate" in plist

    def test_contains_time(self):
        plist = generate_launchd_plist(hour=8, minute=30)
        assert "<integer>8</integer>" in plist
        assert "<integer>30</integer>" in plist

    def test_contains_generate_command(self):
        plist = generate_launchd_plist(tdiz_path="/usr/local/bin/tdiz")
        assert "/usr/local/bin/tdiz" in plist
        assert "<string>generate</string>" in plist

    def test_valid_xml(self):
        plist = generate_launchd_plist()
        assert plist.startswith("<?xml version=")
        assert "</plist>" in plist

    def test_custom_tdiz_path(self):
        plist = generate_launchd_plist(tdiz_path="/opt/bin/tdiz")
        assert "/opt/bin/tdiz" in plist


class TestGenerateCronEntry:
    def test_format(self):
        entry = generate_cron_entry(hour=7, minute=0, tdiz_path="/usr/local/bin/tdiz")
        assert entry == "0 7 * * * /usr/local/bin/tdiz generate >> ~/.tdiz/cron.log 2>&1"

    def test_custom_time(self):
        entry = generate_cron_entry(hour=22, minute=15, tdiz_path="tdiz")
        assert entry.startswith("15 22 * * *")


class TestInstallLaunchdPlist:
    def test_writes_file(self, tmp_path, monkeypatch):
        # Patch the target path to a temp directory
        plist_path = tmp_path / "com.tdiz.generate.plist"
        import tdiz.scheduler as sched_mod

        monkeypatch.setattr(sched_mod, "PLIST_DIR", tmp_path)
        monkeypatch.setattr(sched_mod, "PLIST_PATH", plist_path)

        content = generate_launchd_plist()
        result_path = install_launchd_plist(content)

        assert result_path == plist_path
        assert plist_path.exists()
        assert "com.tdiz.generate" in plist_path.read_text()


class TestGetInstallInstructions:
    def test_contains_load_command(self):
        instructions = get_install_instructions(
            Path("~/Library/LaunchAgents/com.tdiz.generate.plist"),
            hour=7,
            minute=0,
        )
        assert "launchctl load" in instructions
        assert "launchctl unload" in instructions
        assert "07:00" in instructions
