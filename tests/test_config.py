"""Tests for tdiz.config — config loading, validation, and persistence."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tdiz.config import AppConfig, ZoomCredentials, load_config, save_preferences, validate_config


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Set up a temporary config directory and clear env vars."""
    config_path = tmp_path / "config.toml"
    env_file = tmp_path / ".env"

    # Clear all relevant env vars
    for var in (
        "ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "BFL_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    return config_path, env_file


class TestLoadConfig:
    def test_defaults_when_no_config_or_env(self, tmp_config, monkeypatch):
        config_path, env_file = tmp_config
        cfg = load_config(env_file=env_file, config_path=config_path)
        assert cfg.zoom is None
        assert cfg.openai_api_key is None
        assert cfg.image_provider == "openai"
        assert cfg.llm_provider == "openai"
        assert cfg.max_managed_images == 5

    def test_loads_zoom_creds_from_env(self, tmp_config, monkeypatch):
        config_path, env_file = tmp_config
        monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acct-123")
        monkeypatch.setenv("ZOOM_CLIENT_ID", "client-456")
        monkeypatch.setenv("ZOOM_CLIENT_SECRET", "secret-789")

        cfg = load_config(config_path=config_path)
        assert cfg.zoom is not None
        assert cfg.zoom.account_id == "acct-123"
        assert cfg.zoom.client_id == "client-456"
        assert cfg.zoom.client_secret == "secret-789"

    def test_partial_zoom_creds_yields_none(self, tmp_config, monkeypatch):
        config_path, env_file = tmp_config
        monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acct-123")
        # Missing client_id and client_secret
        cfg = load_config(config_path=config_path)
        assert cfg.zoom is None

    def test_loads_preferences_from_toml(self, tmp_config):
        config_path, env_file = tmp_config
        save_preferences(
            {"image_provider": "flux", "max_managed_images": 3},
            config_path=config_path,
        )
        cfg = load_config(config_path=config_path)
        assert cfg.image_provider == "flux"
        assert cfg.max_managed_images == 3


class TestValidateConfig:
    def test_valid_openai_config(self):
        cfg = AppConfig(
            zoom=ZoomCredentials("a", "b", "c"),
            openai_api_key="sk-123",
            image_provider="openai",
            llm_provider="openai",
        )
        assert validate_config(cfg) == []

    def test_missing_zoom_creds(self):
        cfg = AppConfig(openai_api_key="sk-123")
        errors = validate_config(cfg, require_zoom=True)
        assert any("Zoom" in e for e in errors)

    def test_zoom_not_required_for_dry_run(self):
        cfg = AppConfig(openai_api_key="sk-123")
        errors = validate_config(cfg, require_zoom=False)
        assert errors == []

    def test_missing_openai_key_for_openai_provider(self):
        cfg = AppConfig(
            zoom=ZoomCredentials("a", "b", "c"),
            image_provider="openai",
            llm_provider="openai",
        )
        errors = validate_config(cfg)
        assert any("OPENAI_API_KEY" in e for e in errors)

    def test_missing_anthropic_key(self):
        cfg = AppConfig(
            zoom=ZoomCredentials("a", "b", "c"),
            openai_api_key="sk-123",
            image_provider="openai",
            llm_provider="anthropic",
        )
        errors = validate_config(cfg)
        assert any("ANTHROPIC_API_KEY" in e for e in errors)


class TestSavePreferences:
    def test_round_trip(self, tmp_path):
        config_path = tmp_path / "config.toml"
        save_preferences({"image_provider": "sd", "save_local": False}, config_path)
        cfg = load_config(config_path=config_path)
        assert cfg.image_provider == "sd"
        assert cfg.save_local is False

    def test_merge_preserves_existing(self, tmp_path):
        config_path = tmp_path / "config.toml"
        save_preferences({"image_provider": "openai"}, config_path)
        save_preferences({"max_managed_images": 7}, config_path)
        cfg = load_config(config_path=config_path)
        assert cfg.image_provider == "openai"
        assert cfg.max_managed_images == 7
