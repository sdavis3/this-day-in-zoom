"""Generate macOS launchd plists and cron entries for daily background generation."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path


PLIST_LABEL = "com.tdiz.generate"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = PLIST_DIR / f"{PLIST_LABEL}.plist"


def generate_launchd_plist(
    hour: int = 7,
    minute: int = 0,
    tdiz_path: str | None = None,
) -> str:
    """Return a launchd plist XML string for daily tdiz generate runs."""
    if tdiz_path is None:
        found = shutil.which("tdiz")
        tdiz_path = found if found else "/usr/local/bin/tdiz"

    plist = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{PLIST_LABEL}</string>

            <key>ProgramArguments</key>
            <array>
                <string>{tdiz_path}</string>
                <string>generate</string>
            </array>

            <key>StartCalendarInterval</key>
            <dict>
                <key>Hour</key>
                <integer>{hour}</integer>
                <key>Minute</key>
                <integer>{minute}</integer>
            </dict>

            <key>StandardOutPath</key>
            <string>{Path.home()}/.tdiz/launchd-stdout.log</string>

            <key>StandardErrorPath</key>
            <string>{Path.home()}/.tdiz/launchd-stderr.log</string>

            <key>RunAtLoad</key>
            <false/>
        </dict>
        </plist>
    """)
    return plist


def install_launchd_plist(plist_content: str) -> Path:
    """Write the plist to ~/Library/LaunchAgents/ and return the path."""
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_content, encoding="utf-8")
    return PLIST_PATH


def generate_cron_entry(
    hour: int = 7,
    minute: int = 0,
    tdiz_path: str | None = None,
) -> str:
    """Return a crontab line for daily tdiz generate."""
    if tdiz_path is None:
        found = shutil.which("tdiz")
        tdiz_path = found if found else "tdiz"

    return f"{minute} {hour} * * * {tdiz_path} generate >> ~/.tdiz/cron.log 2>&1"


def get_install_instructions(plist_path: Path, hour: int, minute: int) -> str:
    """Return human-readable installation instructions."""
    return textwrap.dedent(f"""\
        launchd plist written to: {plist_path}

        To activate daily scheduling (runs at {hour:02d}:{minute:02d}):

            launchctl load {plist_path}

        To deactivate:

            launchctl unload {plist_path}

        To test immediately:

            launchctl start {PLIST_LABEL}

        Logs are written to ~/.tdiz/launchd-stdout.log and ~/.tdiz/launchd-stderr.log
    """)
