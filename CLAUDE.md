# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**This Day in Zoom** is a Python CLI tool (`tdiz`) that generates AI-created Zoom virtual backgrounds based on historically significant events for a given date. The full pipeline: research historical events → LLM selects best event → AI generates image → upload to Zoom API.

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Commands

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_zoom_client.py

# Run a single test
pytest tests/test_zoom_client.py::test_function_name -v

# Run the CLI
tdiz generate
tdiz --help
```

No Makefile, no lint configuration (yet). Entry point is `tdiz` (defined in `pyproject.toml`).

## Architecture

The `src/tdiz/` package has 7 focused modules with clear separation of concerns:

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Typer CLI with 6 commands: `generate`, `list`, `delete`, `cleanup`, `schedule`, `config` |
| `config.py` | Loads preferences from `~/.tdiz/config.toml` and secrets from env/`.env` |
| `zoom_client.py` | Zoom REST API: Server-to-Server OAuth, upload/delete/list backgrounds, rate-limit retry |
| `history.py` | Fetches historical events — onthisday.com first, Wikipedia fallback |
| `image_gen.py` | Image generation backends (OpenAI GPT Image 1 implemented; FLUX/SD stubbed) |
| `prompt_builder.py` | LLM event selection — picks most visually compelling event, returns image prompt |
| `scheduler.py` | Generates macOS launchd plists or cron entries for daily automation |

**`generate` pipeline flow:**
```
Config load → Fetch events (history.py) → LLM select (prompt_builder.py)
→ Generate image (image_gen.py) → Enforce 10-file cap (zoom_client.py)
→ Upload to Zoom → Optionally save to ~/.tdiz/images/
```

## Key Design Decisions

- **Pluggable backends**: Image generators and LLM providers use factory/strategy patterns. New providers should implement the existing abstract interfaces.
- **Tool-managed images**: Identified by `tdiz_` filename prefix. The client never deletes user-uploaded backgrounds — only its own.
- **Secrets vs. preferences**: API keys always come from env vars / `.env`; user preferences (provider choice, schedule time, etc.) go in `~/.tdiz/config.toml`.
- **Zoom OAuth**: Server-to-Server OAuth with automatic token refresh and 401 retry.
- **Image constraints**: Zoom requires < 15 MB; tool targets 1920×1080 JPEG, auto-downsizes if needed.

## Configuration

Runtime config lives outside the repo:
- `~/.tdiz/config.toml` — preferences (`image_provider`, `llm_provider`, `max_managed_images`, `save_local`, `schedule_time`)
- `.env` (or environment variables) — secrets (`ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

See `.env.example` for required variable names.

## Testing

Tests use `pytest`, `pytest-asyncio`, `pytest-mock`, and `respx` (for mocking httpx HTTP calls). Each module has a corresponding test file in `tests/`. HTTP interactions with external APIs should always be mocked with `respx`.
