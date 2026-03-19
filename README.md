# 🗓 This Day in Zoom

AI-generated Zoom virtual backgrounds based on historically significant events that happened **on this day**.

Every day, `tdiz` researches notable historical events for today's date, uses an LLM to pick the most visually compelling one, generates an artistic image with AI, and uploads it as your Zoom virtual background — automatically.

## How It Works

```
tdiz generate
```

1. **Research** → Scrapes [onthisday.com](https://www.onthisday.com) (with Wikipedia fallback) for events on today's date
2. **Select** → An LLM (OpenAI GPT or Anthropic Claude) picks the most visually striking event
3. **Generate** → AI image generation (OpenAI GPT Image 1) creates a 1920×1080 artistic scene
4. **Upload** → The image is uploaded to your Zoom account via the REST API and set as your default background

Your colleagues will ask "what's your background today?" — and you'll have a great answer.

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Zoom account** with Virtual Background enabled
- **OpenAI API key** (for image generation + event selection)
- A **Zoom Server-to-Server OAuth app** (free to create)

### 1. Install

```bash
pip install this-day-in-zoom
```

Or install from source:

```bash
git clone https://github.com/sdavis3/this-day-in-zoom.git
cd this-day-in-zoom
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Create a Zoom Server-to-Server OAuth App

1. Go to the [Zoom App Marketplace](https://marketplace.zoom.us/) → **Develop** → **Build App**
2. Choose **Server-to-Server OAuth**
3. Note your **Account ID**, **Client ID**, and **Client Secret**
4. Under **Scopes**, add:
   - `user:write:admin` (upload/delete virtual backgrounds)
   - `user:read:admin` (read current backgrounds)

### 3. Configure

Create a `.env` file in your project root (or set environment variables):

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required variables:

| Variable             | Description                               |
| -------------------- | ----------------------------------------- |
| `ZOOM_ACCOUNT_ID`    | From your Zoom Server-to-Server OAuth app |
| `ZOOM_CLIENT_ID`     | From your Zoom Server-to-Server OAuth app |
| `ZOOM_CLIENT_SECRET` | From your Zoom Server-to-Server OAuth app |
| `OPENAI_API_KEY`     | Your OpenAI API key                       |

Optional:

| Variable            | Description                                              |
| ------------------- | -------------------------------------------------------- |
| `ANTHROPIC_API_KEY` | For Claude-based event selection (alternative to OpenAI) |
| `BFL_API_KEY`       | For FLUX image generation (future release)               |

Then run the interactive config wizard:

```bash
tdiz config
```

### 4. Generate!

```bash
# Generate for today
tdiz generate

# Generate for a specific date
tdiz generate --date 07-20

# Dry run — see the selected event and prompt without uploading
tdiz generate --dry-run

# Use Claude for event selection instead of GPT
tdiz generate --llm-provider anthropic

# Verbose logging
tdiz generate -v
```

---

## Commands

| Command            | Description                                                    |
| ------------------ | -------------------------------------------------------------- |
| `tdiz generate`    | Generate and upload a background for today (or `--date MM-DD`) |
| `tdiz list`        | List all virtual backgrounds on your Zoom account              |
| `tdiz delete <id>` | Delete a specific background by Zoom file ID                   |
| `tdiz cleanup`     | Delete all tool-managed backgrounds (preserves your own)       |
| `tdiz schedule`    | Generate a macOS launchd plist for daily automation            |
| `tdiz config`      | Interactive setup wizard                                       |

### Key Flags

| Flag                               | Default | Description                                       |
| ---------------------------------- | ------- | ------------------------------------------------- |
| `--date` / `-d`                    | Today   | Target date in MM-DD format                       |
| `--dry-run`                        | false   | Show event/prompt without generating or uploading |
| `--generate-only`                  | false   | Generate image locally but skip Zoom upload       |
| `--provider` / `-p`                | openai  | Image generation provider                         |
| `--llm-provider`                   | openai  | LLM for event selection (openai or anthropic)     |
| `--max-managed`                    | 5       | Max tool-managed images to keep on Zoom           |
| `--save-local` / `--no-save-local` | true    | Save images to `~/.tdiz/images/`                  |
| `--verbose` / `-v`                 | false   | Detailed logging                                  |

---

## Daily Automation

### macOS (launchd — recommended)

```bash
# Generate and install a daily schedule (default: 7:00 AM)
tdiz schedule --install

# Custom time
tdiz schedule --install --time 06:30
```

This creates a LaunchAgent plist at `~/Library/LaunchAgents/com.tdiz.generate.plist`.

To manage:

```bash
# Activate
launchctl load ~/Library/LaunchAgents/com.tdiz.generate.plist

# Deactivate
launchctl unload ~/Library/LaunchAgents/com.tdiz.generate.plist

# Test immediately
launchctl start com.tdiz.generate
```

### cron (alternative)

```bash
tdiz schedule --cron
# Output: 0 7 * * * /path/to/tdiz generate >> ~/.tdiz/cron.log 2>&1
```

Add the output to your crontab with `crontab -e`.

---

## Image Lifecycle Management

Zoom enforces a **10 virtual background file limit** per user. This tool manages its own images to avoid conflicts:

- Tool-managed images are identified by the `tdiz_` filename prefix
- Before uploading, the tool checks your current count and deletes the oldest tool-managed image if needed
- Images you uploaded manually are **never** touched
- The `--max-managed` flag (default: 5) reserves slots for your personal backgrounds

---

## Cost

Daily image generation uses paid APIs. Expected costs with default settings:

| Provider           | Cost per image | Monthly (daily use) |
| ------------------ | -------------- | ------------------- |
| OpenAI GPT Image 1 | ~$0.04–$0.08   | ~$1.20–$2.40        |

LLM event selection adds a negligible cost (a few cents per month).

---

## Configuration Files

| Path                  | Purpose                                   |
| --------------------- | ----------------------------------------- |
| `~/.tdiz/config.toml` | User preferences (never contains secrets) |
| `~/.tdiz/images/`     | Locally saved generated images            |
| `.env`                | API keys and credentials (git-ignored)    |

---

## Known Limitations

1. **`is_default` PATCH**: Zoom's API for setting a default virtual background at the user level has been reported as unreliable (it works reliably at the account/admin level). The tool attempts the PATCH call but falls back gracefully — your most recently uploaded image should appear in the Zoom client.

2. **Web scraping**: The onthisday.com scraper may break if the site's HTML structure changes. Wikipedia is a built-in fallback and typically provides sufficient event data.

3. **macOS only**: The `tdiz schedule` command generates macOS-specific launchd plists. Linux/Windows users can use the `--cron` flag or set up their own scheduler.

4. **REST API only**: Zoom's REST API cannot switch backgrounds during a live meeting. The background is set before your next call.

---

## Development

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with verbose output
pytest -v
```

---

## Project Structure

```
this-day-in-zoom/
├── pyproject.toml          # Package config & dependencies
├── README.md
├── LICENSE                  # MIT
├── .env.example             # Template for credentials
├── src/
│   └── tdiz/
│       ├── __init__.py
│       ├── cli.py           # Typer CLI entry point
│       ├── config.py        # Config & env loading
│       ├── zoom_client.py   # Zoom OAuth + VB API
│       ├── history.py       # Event scraping & selection
│       ├── image_gen.py     # Pluggable image generation
│       ├── prompt_builder.py# LLM prompt crafting
│       └── scheduler.py     # launchd/cron generation
└── tests/
    ├── test_cli.py
    ├── test_config.py
    ├── test_history.py
    ├── test_image_gen.py
    ├── test_prompt_builder.py
    ├── test_scheduler.py
    └── test_zoom_client.py
```

---

## License

MIT — see [LICENSE](LICENSE).
