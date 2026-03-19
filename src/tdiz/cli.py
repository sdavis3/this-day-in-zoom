"""Typer CLI entry point for This Day in Zoom.

Commands: generate, list, delete, cleanup, schedule, config
"""

from __future__ import annotations

import calendar
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from tdiz import __version__
from tdiz.config import (
    AppConfig,
    ensure_dirs,
    load_config,
    save_preferences,
    validate_config,
)

app = typer.Typer(
    name="tdiz",
    help="This Day in Zoom — AI-generated virtual backgrounds from history.",
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_date(date_str: Optional[str]) -> tuple[int, int]:
    """Parse MM-DD (or MM/DD) into (month, day). Defaults to today."""
    if not date_str:
        today = date.today()
        return today.month, today.day

    clean = date_str.replace("/", "-")
    parts = clean.split("-")

    try:
        # Support MM-DD or YYYY-MM-DD (year is ignored per PRD)
        if len(parts) == 2:
            month, day = int(parts[0]), int(parts[1])
        elif len(parts) == 3:
            month, day = int(parts[1]), int(parts[2])
        else:
            raise ValueError("wrong number of parts")
    except ValueError:
        raise typer.BadParameter(f"Invalid date format: {date_str}. Use MM-DD.")

    if month < 1 or month > 12 or day < 1 or day > 31:
        raise typer.BadParameter(f"Invalid date: {date_str}")

    return month, day


def _abort(msg: str) -> None:
    typer.secho(f"Error: {msg}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _info(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.GREEN)


def _warn(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.YELLOW)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------
@app.command()
def generate(
    date_str: Optional[str] = typer.Option(
        None, "--date", "-d", help="Target date in MM-DD format (default: today)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Research & build prompt but don't upload."
    ),
    generate_only: bool = typer.Option(
        False, "--generate-only", help="Generate image but skip Zoom upload."
    ),
    provider: Optional[str] = typer.Option(
        None, "--provider", "-p", help="Image generation provider (openai, flux, sd)."
    ),
    llm_provider: Optional[str] = typer.Option(
        None, "--llm-provider", help="LLM for event selection (openai, anthropic)."
    ),
    save_local: Optional[bool] = typer.Option(
        None, "--save-local/--no-save-local", help="Save image locally."
    ),
    max_managed: Optional[int] = typer.Option(
        None, "--max-managed", help="Max tool-managed images on Zoom."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Detailed logging."),
) -> None:
    """Generate a virtual background for today (or --date) and set it on Zoom."""
    _setup_logging(verbose)
    logger = logging.getLogger("tdiz.cli")
    ensure_dirs()

    cfg = load_config()

    # Override config with CLI flags
    if provider:
        cfg.image_provider = provider
    if llm_provider:
        cfg.llm_provider = llm_provider
    if save_local is not None:
        cfg.save_local = save_local
    if max_managed is not None:
        cfg.max_managed_images = max_managed

    # Validate
    errors = validate_config(cfg, require_zoom=not dry_run and not generate_only)
    if errors:
        for e in errors:
            _abort(e)

    month, day = _parse_date(date_str)
    month_name = calendar.month_name[month]
    _info(f"🗓  Target date: {month_name} {day}")

    # --- Step 1: Fetch historical events ---
    _info("📚 Researching historical events...")
    from tdiz.history import CompositeEventSource

    source = CompositeEventSource()
    events = source.fetch_events(month, day)

    if not events:
        _abort(f"No historical events found for {month_name} {day}. Try a different date.")

    _info(f"   Found {len(events)} events")

    # --- Step 2: LLM event selection ---
    _info(f"🤖 Selecting best event via {cfg.llm_provider.upper()}...")
    from tdiz.prompt_builder import get_selector

    selector = get_selector(
        provider=cfg.llm_provider,
        openai_key=cfg.openai_api_key,
        anthropic_key=cfg.anthropic_api_key,
    )
    selected = selector.select_event(month, day, events)

    year_str = f" ({selected.event.year})" if selected.event.year else ""
    _info(f"   Selected: {selected.event.description}{year_str}")
    _info(f"   Rationale: {selected.rationale}")

    if dry_run:
        _info("\n🖼  Image prompt (dry run — not generating):")
        typer.echo(f"\n{selected.image_prompt}\n")
        raise typer.Exit(0)

    # --- Step 3: Generate image ---
    _info(f"🎨 Generating image via {cfg.image_provider.upper()}...")
    from tdiz.image_gen import generate_filename, get_image_generator

    filename = generate_filename(month, day, selected.event.description)
    output_path = cfg.images_dir / filename

    generator = get_image_generator(
        provider=cfg.image_provider,
        openai_key=cfg.openai_api_key,
        bfl_key=cfg.bfl_api_key,
    )
    img_path = generator.generate(selected.image_prompt, output_path)
    file_size_kb = img_path.stat().st_size / 1024
    _info(f"   Image saved: {img_path} ({file_size_kb:.0f} KB)")

    if generate_only:
        _info(f"\n✅ Done! Image saved locally (skipping Zoom upload): {img_path}")
        raise typer.Exit(0)

    # --- Step 4: Enforce Zoom cap & upload ---
    _info("☁️  Uploading to Zoom...")
    from tdiz.zoom_client import ZoomClient

    with ZoomClient(cfg.zoom) as zoom:  # type: ignore[arg-type]
        # Enforce cap
        deleted = zoom.enforce_cap(cfg.max_managed_images)
        if deleted:
            _info(f"   Cleaned up {len(deleted)} old background(s) to stay within cap")

        # Upload
        bg = zoom.upload_background(img_path)
        _info(f"   Uploaded: {bg.name} (ID: {bg.id})")

        # Set as default
        if zoom.set_default(bg.id):
            _info("   ✅ Set as default virtual background")
        else:
            _warn(
                "   ⚠️  Could not set as default (known Zoom API limitation). "
                "The most recently uploaded image should appear in your Zoom client."
            )

    if not cfg.save_local:
        img_path.unlink(missing_ok=True)
        logger.debug("Removed local image (save_local=false)")

    _info(f"\n🎉 Done! Your Zoom background is now: {selected.event.description}{year_str}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
@app.command("list")
def list_backgrounds(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List all virtual backgrounds on your Zoom account."""
    _setup_logging(verbose)
    cfg = load_config()
    errors = validate_config(cfg, require_zoom=True)
    if errors:
        for e in errors:
            _abort(e)

    from tdiz.zoom_client import ZoomClient

    with ZoomClient(cfg.zoom) as zoom:  # type: ignore[arg-type]
        backgrounds = zoom.list_backgrounds()

    if not backgrounds:
        _info("No virtual backgrounds found.")
        return

    _info(f"Found {len(backgrounds)} virtual background(s):\n")
    for bg in backgrounds:
        managed = " [tdiz]" if bg.is_managed else ""
        default = " ★ DEFAULT" if bg.is_default else ""
        size_kb = bg.size / 1024 if bg.size else 0
        typer.echo(f"  {bg.id}  {bg.name}{managed}{default}  ({size_kb:.0f} KB)")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
@app.command()
def delete(
    file_id: str = typer.Argument(help="Zoom file ID of the background to delete."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Delete a specific virtual background by Zoom file ID."""
    _setup_logging(verbose)
    cfg = load_config()
    errors = validate_config(cfg, require_zoom=True)
    if errors:
        for e in errors:
            _abort(e)

    from tdiz.zoom_client import ZoomClient

    with ZoomClient(cfg.zoom) as zoom:  # type: ignore[arg-type]
        zoom.delete_background(file_id)
    _info(f"Deleted background {file_id}")


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------
@app.command()
def cleanup(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Delete all tool-managed backgrounds (preserves user-uploaded ones)."""
    _setup_logging(verbose)
    cfg = load_config()
    errors = validate_config(cfg, require_zoom=True)
    if errors:
        for e in errors:
            _abort(e)

    from tdiz.zoom_client import ZoomClient

    with ZoomClient(cfg.zoom) as zoom:  # type: ignore[arg-type]
        managed = zoom.get_managed_backgrounds()
        if not managed:
            _info("No tool-managed backgrounds to clean up.")
            return

        confirm = typer.confirm(
            f"Delete {len(managed)} tool-managed background(s)?", default=False
        )
        if not confirm:
            _warn("Aborted.")
            return

        for bg in managed:
            zoom.delete_background(bg.id)
            _info(f"  Deleted: {bg.name}")

    _info("Cleanup complete.")


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------
@app.command()
def schedule(
    time_str: Optional[str] = typer.Option(
        None, "--time", "-t", help="Daily run time in HH:MM format (default: from config)."
    ),
    cron: bool = typer.Option(False, "--cron", help="Output cron entry instead of launchd plist."),
    install: bool = typer.Option(False, "--install", help="Install the launchd plist directly."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate a macOS launchd plist (or cron entry) for daily runs."""
    _setup_logging(verbose)
    cfg = load_config()

    if time_str:
        parts = time_str.split(":")
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    else:
        parts = cfg.schedule_time.split(":")
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0

    from tdiz.scheduler import (
        generate_cron_entry,
        generate_launchd_plist,
        get_install_instructions,
        install_launchd_plist,
    )

    if cron:
        entry = generate_cron_entry(hour, minute)
        _info("Add this line to your crontab (crontab -e):\n")
        typer.echo(entry)
        return

    plist = generate_launchd_plist(hour, minute)

    if install:
        path = install_launchd_plist(plist)
        instructions = get_install_instructions(path, hour, minute)
        _info(instructions)
    else:
        _info("Generated launchd plist:\n")
        typer.echo(plist)
        _info(
            "\nTo install, re-run with --install, or manually save to "
            "~/Library/LaunchAgents/ and load with launchctl."
        )


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
@app.command("config")
def configure(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Interactive setup wizard for preferences."""
    _setup_logging(verbose)
    ensure_dirs()
    cfg = load_config()

    _info("This Day in Zoom — Configuration\n")

    # Image provider
    image_prov = typer.prompt(
        "Image generation provider",
        default=cfg.image_provider,
        type=typer.Choice(["openai", "flux", "sd"]),
    )

    # LLM provider
    llm_prov = typer.prompt(
        "LLM provider for event selection",
        default=cfg.llm_provider,
        type=typer.Choice(["openai", "anthropic"]),
    )

    # Max managed images
    max_img = typer.prompt(
        "Max tool-managed images on Zoom (1-9)",
        default=cfg.max_managed_images,
        type=int,
    )

    # Save local
    save = typer.confirm("Save generated images locally?", default=cfg.save_local)

    # Schedule time
    sched = typer.prompt(
        "Daily schedule time (HH:MM)",
        default=cfg.schedule_time,
    )

    prefs = {
        "image_provider": image_prov,
        "llm_provider": llm_prov,
        "max_managed_images": min(max(max_img, 1), 9),
        "save_local": save,
        "schedule_time": sched,
    }

    save_preferences(prefs)
    _info("\n✅ Preferences saved to ~/.tdiz/config.toml")
    _info(
        "\nReminder: API keys should be set in environment variables or a .env file. "
        "See .env.example for the full list."
    )


# ---------------------------------------------------------------------------
# version callback
# ---------------------------------------------------------------------------
def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tdiz v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """This Day in Zoom — AI-generated virtual backgrounds from history."""
    pass
