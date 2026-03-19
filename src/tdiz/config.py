"""Configuration and secrets management for This Day in Zoom.

Config lives in ~/.tdiz/config.toml (preferences only).
Secrets come from environment variables or a .env file.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Compat: tomli for Python <3.11, stdlib tomllib for 3.11+
# ---------------------------------------------------------------------------
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TDIZ_DIR = Path.home() / ".tdiz"
CONFIG_PATH = TDIZ_DIR / "config.toml"
IMAGES_DIR = TDIZ_DIR / "images"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ZoomCredentials:
    account_id: str
    client_id: str
    client_secret: str


@dataclass
class AppConfig:
    """Merged view of config.toml preferences + environment secrets."""

    # Zoom
    zoom: Optional[ZoomCredentials] = None

    # API keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    bfl_api_key: Optional[str] = None

    # Preferences (from config.toml)
    image_provider: str = "openai"
    llm_provider: str = "openai"
    save_local: bool = True
    max_managed_images: int = 5
    schedule_time: str = "07:00"

    # Internal
    config_dir: Path = field(default_factory=lambda: TDIZ_DIR)
    images_dir: Path = field(default_factory=lambda: IMAGES_DIR)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_toml(path: Path) -> dict:
    """Load a TOML file and return its contents as a dict."""
    if not path.exists():
        return {}
    if tomllib is None:
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _save_toml(path: Path, data: dict) -> None:
    """Write a dict to a TOML file."""
    if tomli_w is None:
        raise RuntimeError("tomli_w is required to write config. pip install tomli-w")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def load_config(
    env_file: Optional[Path] = None,
    config_path: Optional[Path] = None,
) -> AppConfig:
    """Load configuration from environment + config.toml.

    Priority: environment variables > .env file > config.toml defaults.
    """
    # Load .env if present
    if env_file and env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()  # auto-discovers .env in cwd or parents

    # Load TOML preferences
    toml_path = config_path or CONFIG_PATH
    prefs = _load_toml(toml_path)

    # Build Zoom credentials (all three required)
    zoom_acct = os.getenv("ZOOM_ACCOUNT_ID", "")
    zoom_cid = os.getenv("ZOOM_CLIENT_ID", "")
    zoom_csecret = os.getenv("ZOOM_CLIENT_SECRET", "")
    zoom_creds = None
    if zoom_acct and zoom_cid and zoom_csecret:
        zoom_creds = ZoomCredentials(
            account_id=zoom_acct,
            client_id=zoom_cid,
            client_secret=zoom_csecret,
        )

    return AppConfig(
        zoom=zoom_creds,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        bfl_api_key=os.getenv("BFL_API_KEY"),
        image_provider=prefs.get("image_provider", "openai"),
        llm_provider=prefs.get("llm_provider", "openai"),
        save_local=prefs.get("save_local", True),
        max_managed_images=prefs.get("max_managed_images", 5),
        schedule_time=prefs.get("schedule_time", "07:00"),
    )


def save_preferences(
    prefs: dict,
    config_path: Optional[Path] = None,
) -> None:
    """Persist user preferences to config.toml (never writes secrets)."""
    toml_path = config_path or CONFIG_PATH
    existing = _load_toml(toml_path)
    existing.update(prefs)
    _save_toml(toml_path, existing)


def ensure_dirs() -> None:
    """Create ~/.tdiz/ and ~/.tdiz/images/ if they don't exist."""
    TDIZ_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def validate_config(cfg: AppConfig, require_zoom: bool = True) -> list[str]:
    """Return a list of missing-config error messages (empty = valid)."""
    errors: list[str] = []

    if require_zoom and cfg.zoom is None:
        errors.append(
            "Zoom credentials missing. Set ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, "
            "and ZOOM_CLIENT_SECRET in your environment or .env file."
        )

    if cfg.image_provider == "openai" and not cfg.openai_api_key:
        errors.append("OPENAI_API_KEY is required when image_provider is 'openai'.")

    if cfg.llm_provider == "openai" and not cfg.openai_api_key:
        errors.append("OPENAI_API_KEY is required when llm_provider is 'openai'.")

    if cfg.llm_provider == "anthropic" and not cfg.anthropic_api_key:
        errors.append("ANTHROPIC_API_KEY is required when llm_provider is 'anthropic'.")

    if cfg.image_provider == "flux" and not cfg.bfl_api_key:
        errors.append("BFL_API_KEY is required when image_provider is 'flux'.")

    return errors
