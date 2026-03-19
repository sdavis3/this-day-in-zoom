# Product Requirements Document

## This Day in Zoom — Virtual Background Generator

**Version:** 1.0
**Date:** March 18, 2026
**Status:** Draft — Pending Review
**Classification:** Open Source (GitHub)

---

## 1. Executive Summary

This Day in Zoom is a macOS command-line tool that automatically generates an AI-created virtual background for Zoom based on a historically significant event that occurred on this day in history (matching the current month and day, or a user-specified month/day). Each day, the tool researches notable historical events, selects the one most likely to produce a visually compelling and artistic image, generates the image using an AI image generation API, and uploads it to the user's Zoom account via the Zoom REST API—setting it as the active default virtual background.

The tool is built in Python, designed for personal use initially, and intended for open-source distribution via GitHub.

## 2. Problem Statement

Virtual backgrounds on Zoom are ubiquitous in remote and hybrid work, but most users default to a static, generic image and never change it. Meanwhile, historical awareness and conversation starters are undervalued in daily meetings. There is currently no automated tool that combines historical research, AI art generation, and Zoom background management into a single workflow.

## 3. Goals & Non-Goals

### 3.1 Goals

- Deliver a single CLI command that generates and sets a historically-themed Zoom virtual background for any given date.
- Fully comply with Zoom's REST API rules: OAuth authentication, file size/format limits, and the 10-image-per-user cap.
- Provide management subcommands to list, delete, and rotate virtual backgrounds.
- Ship as an installable Python package with clear README for GitHub distribution.

### 3.2 Non-Goals (v1)

- GUI or web interface.
- Support for video virtual backgrounds.
- Multi-user or enterprise/admin-level Zoom account management.
- Real-time in-meeting background switching (Zoom's REST API does not support this).

## 4. Target User

The primary user is a technically comfortable individual who uses Zoom regularly and wants a daily conversation-starter background that is unique, educational, and visually compelling. The tool will be open-sourced on GitHub, so secondary users include developers and power users comfortable with Python, API keys, and CLI tools.

## 5. Core Workflow

The end-to-end flow for the primary command executes the following steps in sequence:

1. **Determine the target date** — Default: today's month/day, or accept a `--date` parameter. Only the month and day are relevant—the year is ignored since the tool searches for all events across history that occurred on that calendar date.
2. **Research historical events** — Scrape or query a data source such as onthisday.com or a historical events API.
3. **Evaluate and rank events** — Use an LLM (e.g., Claude or GPT) to determine which event would produce the most visually impactful and artistic image as a Zoom background.
4. **Generate the image** — Call an AI image generation API (recommended: OpenAI GPT Image 1 or FLUX.1.1 Pro) at 1920×1080, saved as JPEG.
5. **Enforce the Zoom 10-file cap** — Check the user's current virtual backgrounds and delete the oldest tool-managed image if at or near the limit.
6. **Upload the image** — Upload the generated image to Zoom via `POST /v2/users/me/settings/virtual_backgrounds`.
7. **Set as default** — Set the newly uploaded image as the default virtual background via `PATCH` to user settings (`is_default: true`).
8. **Archive locally** — Optionally save the image to a configurable directory for archival.

## 6. Zoom API Integration

### 6.1 Authentication

Zoom deprecated JWT apps in September 2023. The tool must use **Server-to-Server OAuth**, which is the recommended authentication method for internal/personal apps that do not require user interaction.

- The user creates a Server-to-Server OAuth app in the Zoom App Marketplace.
- The app provides an **Account ID**, **Client ID**, and **Client Secret**.
- The tool exchanges these credentials for a Bearer access token via `POST https://zoom.us/oauth/token` with `grant_type=account_credentials`.
- Access tokens expire after 1 hour; the tool must handle refresh automatically before each API call.

### 6.2 Required OAuth Scopes

| Scope              | Purpose                                           |
| ------------------ | ------------------------------------------------- |
| `user:write:admin` | Upload and delete virtual background files        |
| `user:read:admin`  | Read current virtual background list and settings |

### 6.3 Virtual Background API Endpoints

| Method | Endpoint                                          | Description                         |
| ------ | ------------------------------------------------- | ----------------------------------- |
| POST   | `/v2/users/{userId}/settings/virtual_backgrounds` | Upload a virtual background image   |
| DELETE | `/v2/users/{userId}/settings/virtual_backgrounds` | Delete virtual background file(s)   |
| GET    | `/v2/users/{userId}/settings`                     | Retrieve settings including VB list |
| PATCH  | `/v2/users/{userId}/settings`                     | Update settings (set `is_default`)  |

### 6.4 Zoom API Constraints & Compliance

The tool must respect the following Zoom-enforced constraints:

| Constraint              | Detail                                                              |
| ----------------------- | ------------------------------------------------------------------- |
| Max files per user      | 10 virtual background files. Exceeding this returns error code 120. |
| Max file size           | 15 MB per file (API limit). Practical target: under 5 MB.           |
| Allowed formats         | JPG/JPEG, PNG (24-bit, no alpha), GIF.                              |
| Rate limit              | Medium rate limit label on upload. Tool should implement backoff.   |
| Feature prerequisite    | Virtual Background must be enabled on the Zoom account.             |
| userId for personal use | Use `"me"` as the userId parameter.                                 |

### 6.5 Image Lifecycle Management

To stay within the 10-file cap, the tool must implement a lifecycle strategy:

- Before uploading, call `GET /v2/users/me/settings` to retrieve the current list of virtual backgrounds.
- Identify images managed by this tool (via a naming convention prefix, e.g., `tdiz_03-18_`).
- If the total count is at or near 10, delete the oldest tool-managed image(s) via `DELETE`.
- Never delete images that were not created by this tool (user-uploaded or admin-provided backgrounds).
- Provide a configurable `--max-managed-images` flag (default: 5) to reserve slots for user-uploaded backgrounds.

## 7. AI Image Generation

### 7.1 Image Generation API — Recommendation

Based on the current landscape of AI image generation APIs (as of March 2026), the following are recommended in priority order:

| Provider          | Model        | Cost/Image   | Notes                                                                                                                          |
| ----------------- | ------------ | ------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| OpenAI            | GPT Image 1  | ~$0.04–$0.08 | Top-ranked quality (LM Arena Elo 1264). Best prompt adherence for historical scenes. Natively multimodal. Recommended default. |
| Black Forest Labs | FLUX.1.1 Pro | ~$0.055      | Tied for highest quality. 4.5s generation. Excellent photorealism. Strong alternative.                                         |
| Stability AI      | SD 3.5       | ~$0.02–$0.04 | Open-source option. Can self-host. Good fallback for cost-sensitive users.                                                     |

The tool should be designed with a pluggable image-generation backend so users can swap providers via configuration.

### 7.2 Note on Zoom's API

Zoom's REST API does not include any image generation capabilities. The API supports only uploading, listing, deleting, and setting virtual background images. All image creation must be handled externally via a third-party AI image generation service.

### 7.3 Image Specifications

- **Resolution:** 1920×1080 pixels (Full HD, 16:9 aspect ratio).
- **Format:** JPEG (best balance of quality and file size for Zoom).
- **Target file size:** Under 5 MB (well within Zoom's 15 MB API limit).
- **Style:** Artistic and visually striking. Optimized for readability at small scale behind a person's head/shoulders. Avoid excessive text in the image.

### 7.4 Prompt Engineering Strategy

The image generation prompt should be crafted by an LLM (Claude or GPT) given the selected historical event. The prompt should instruct the image model to:

- Create a wide-format (16:9) artistic scene inspired by the event.
- Avoid placing key visual elements in the center-bottom area (where the user's silhouette will appear).
- Use rich color and dramatic lighting appropriate to the subject.
- Avoid rendering text or lettering in the image (AI text rendering is unreliable).

## 8. Historical Event Research

### 8.1 Data Source

The primary data source is [onthisday.com](https://www.onthisday.com). The URL format is `https://www.onthisday.com/day/{month}/{day}`, where `{month}` is the full month name spelled out (e.g., "march") and `{day}` is the numeric day (e.g., "18"). The tool will scrape or parse this page to extract a list of notable historical events for the target month and day across all years. Fallback or supplementary sources may include Wikipedia's "On This Day" page or a dedicated historical events API if one becomes available.

### 8.2 Event Selection Logic

After retrieving a list of events, the tool passes them to an LLM with a prompt such as:

> _"Given the following historical events that occurred on [MONTH DAY] across all years in history, select the single event that would produce the most visually impactful, artistic, and culturally significant image to use as a Zoom virtual background. Prioritize events with strong visual elements—architecture, nature, exploration, invention, art, or landmark moments. Avoid events that are primarily political text (e.g., treaty signings with no visual component) or sensitive/controversial in a professional setting."_

The LLM returns the selected event along with a rationale and a suggested image generation prompt.

## 9. CLI Design

### 9.1 Technology Stack

| Component         | Technology                                             |
| ----------------- | ------------------------------------------------------ |
| Language          | Python 3.10+                                           |
| CLI Framework     | Typer (modern, type-hint-driven CLI library)           |
| HTTP Client       | httpx (async support for parallel API calls)           |
| HTML Parsing      | BeautifulSoup4 (for onthisday.com scraping)            |
| Config Management | `~/.tdiz/config.toml` (TOML format)                    |
| Secrets Storage   | Environment variables or `.env` file (python-dotenv)   |
| Packaging         | `pyproject.toml`, pip-installable, entry point: `tdiz` |

### 9.2 Command Structure

| Command            | Description                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------- |
| `tdiz generate`    | Generate a background for today (or `--date MM-DD`) and set it as default.                  |
| `tdiz list`        | List all current virtual backgrounds on the Zoom account.                                   |
| `tdiz delete <id>` | Delete a specific virtual background by its Zoom file ID.                                   |
| `tdiz cleanup`     | Delete all tool-managed backgrounds (preserves user-uploaded ones).                         |
| `tdiz schedule`    | Output a cron expression or launchd plist to run `tdiz generate` daily at a specified time. |
| `tdiz config`      | Interactive setup wizard for API keys and preferences.                                      |

### 9.3 Key Flags & Options

| Flag               | Default  | Description                                              |
| ------------------ | -------- | -------------------------------------------------------- |
| `--date`           | Today    | Target date in MM-DD format (year accepted but ignored). |
| `--save-local`     | `true`   | Save generated image to `~/.tdiz/images/`.               |
| `--dry-run`        | `false`  | Generate and display event/prompt without uploading.     |
| `--provider`       | `openai` | Image generation provider (`openai`, `flux`, `sd`).      |
| `--max-managed`    | `5`      | Max tool-managed images to keep on Zoom.                 |
| `--verbose` / `-v` | `false`  | Enable detailed logging.                                 |

## 10. Background Rotation & Scheduling

The `tdiz schedule` command will generate the appropriate macOS scheduling configuration to run `tdiz generate` automatically each morning. On macOS, the preferred approach is a **launchd plist** (LaunchAgent) that triggers daily at a configurable time (default: 7:00 AM local time). The command should output the plist file and instructions for installing it to `~/Library/LaunchAgents/`.

As a fallback, the tool should also support generating a standard crontab entry for users who prefer cron.

## 11. Configuration & Secrets Management

All configuration is stored in `~/.tdiz/config.toml`. Secrets (API keys, Zoom credentials) are read from environment variables or a `.env` file and are never written to `config.toml`.

### 11.1 Required Environment Variables

| Variable             | Description                                         |
| -------------------- | --------------------------------------------------- |
| `ZOOM_ACCOUNT_ID`    | Zoom Server-to-Server OAuth Account ID              |
| `ZOOM_CLIENT_ID`     | Zoom app Client ID                                  |
| `ZOOM_CLIENT_SECRET` | Zoom app Client Secret                              |
| `OPENAI_API_KEY`     | OpenAI API key (if using GPT Image 1)               |
| `BFL_API_KEY`        | Black Forest Labs key (if using FLUX)               |
| `ANTHROPIC_API_KEY`  | Anthropic key (if using Claude for event selection) |

## 12. Error Handling & Edge Cases

| Scenario                           | Handling                                                                                                                                                                                            |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Zoom 10-file cap reached           | Auto-delete oldest tool-managed image. If no tool-managed images exist, warn the user and abort.                                                                                                    |
| Image generation fails             | Retry up to 2 times with exponential backoff. On final failure, log the error and exit with code 1.                                                                                                 |
| Historical data source unreachable | Fall back to Wikipedia On This Day. If both fail, exit with descriptive error.                                                                                                                      |
| Zoom OAuth token expired           | Automatically request a new token before retrying the failed call.                                                                                                                                  |
| Rate limited by Zoom               | Respect `Retry-After` header; implement exponential backoff.                                                                                                                                        |
| Generated image > 15 MB            | Re-encode as JPEG at reduced quality (85, then 70) until under limit.                                                                                                                               |
| No events found for date           | Fall back to closest date or display a message suggesting a different date.                                                                                                                         |
| Setting `is_default` fails         | Note: community reports suggest `PATCH is_default` may not work reliably at the user level (account-level API). Document this limitation and upload with the most recent image as implicit default. |

## 13. Project Structure

```
this-day-in-zoom/
├── pyproject.toml
├── README.md
├── LICENSE (MIT)
├── .env.example
├── src/
│   └── tdiz/
│       ├── __init__.py
│       ├── cli.py              # Typer CLI entry point
│       ├── config.py           # Config & env loading
│       ├── zoom_client.py      # Zoom OAuth + VB API
│       ├── history.py          # Event scraping & selection
│       ├── image_gen.py        # Pluggable image generation
│       ├── prompt_builder.py   # LLM prompt crafting
│       └── scheduler.py        # launchd/cron generation
├── tests/
└── docs/
```

## 14. Open Questions & Risks

| #   | Question / Risk                                                                                                                                                                 | Proposed Mitigation                                                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | The `PATCH` endpoint to set `is_default` on virtual backgrounds has been reported as unreliable at the user level (works at account level only). Can we reliably set a default? | Investigate at implementation time. Fallback: upload the new image last so Zoom's client picks it up as most recent. Document the limitation.                   |
| 2   | Scraping onthisday.com may break if the site's HTML structure changes, or may violate their ToS.                                                                                | Build a modular data-source layer. Add Wikipedia as a first-class fallback. Consider a dedicated API (e.g., api.wikimedia.org) for long-term reliability.       |
| 3   | AI-generated images may occasionally depict sensitive content for certain historical events.                                                                                    | The event selection LLM prompt explicitly filters for professional-setting-appropriate events. Add a content safety check on the generated image before upload. |
| 4   | Cost accumulation: daily image generation uses paid APIs.                                                                                                                       | At ~$0.04–$0.08/image (OpenAI), monthly cost is ~$1.20–$2.40. Document expected costs clearly in README.                                                        |

## 15. Success Metrics

- The tool successfully generates and uploads a background in under 30 seconds end-to-end.
- Zero Zoom API compliance violations (no exceeding file cap, no invalid formats).
- Daily scheduled runs succeed at 95%+ reliability over a 30-day period.
- GitHub repo achieves 25+ stars within 3 months of publication (community interest signal).

## 16. Milestones & Phases

| Phase | Milestone           | Deliverables                                                                                  |
| ----- | ------------------- | --------------------------------------------------------------------------------------------- |
| 1     | Foundation          | Project scaffold, Zoom OAuth client, upload/delete/list VB, config system.                    |
| 2     | Core Pipeline       | Historical event scraping, LLM event selection, image generation, end-to-end `tdiz generate`. |
| 3     | Polish & Scheduling | `tdiz schedule` (launchd/cron), `tdiz cleanup`, error handling hardening, dry-run mode.       |
| 4     | Open Source Release | README, LICENSE, `.env.example`, GitHub repo, PyPI publication.                               |

## 17. Appendix: Zoom API Quick Reference

### 17.1 Upload Virtual Background (cURL Example)

```bash
curl -X POST "https://api.zoom.us/v2/users/me/settings/virtual_backgrounds" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/image.jpg"
```

### 17.2 Upload Response (201 Created)

```json
{
  "id": "_Tcj7354w6eHw",
  "is_default": false,
  "name": "tdiz_03-18_moon-landing.jpg",
  "size": 53434,
  "type": "image"
}
```

### 17.3 Delete Virtual Background (cURL Example)

```bash
curl -X DELETE "https://api.zoom.us/v2/users/me/settings/virtual_backgrounds?file_ids={file_id}" \
  -H "Authorization: Bearer {access_token}"
```
