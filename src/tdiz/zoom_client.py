"""Zoom Server-to-Server OAuth client and Virtual Background API wrapper.

Handles token lifecycle, VB upload/delete/list, image lifecycle management,
and rate-limit backoff.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from tdiz.config import ZoomCredentials

logger = logging.getLogger("tdiz.zoom")

ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"

# Prefix used to identify images managed by this tool
MANAGED_PREFIX = "tdiz_"

# Retry / backoff
MAX_RETRIES = 3
BACKOFF_BASE = 2.0  # seconds


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class VirtualBackground:
    """Represents a single Zoom virtual background file."""

    id: str
    name: str
    size: int
    is_default: bool
    type: str = "image"

    @property
    def is_managed(self) -> bool:
        """True if this background was created by tdiz."""
        return self.name.startswith(MANAGED_PREFIX)


@dataclass
class _TokenCache:
    access_token: str = ""
    expires_at: float = 0.0  # epoch seconds


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class ZoomClient:
    """Zoom REST API client with Server-to-Server OAuth."""

    def __init__(self, credentials: ZoomCredentials) -> None:
        self._creds = credentials
        self._token = _TokenCache()
        self._http = httpx.Client(timeout=30.0)

    # ----- Auth ----------------------------------------------------------

    def _ensure_token(self) -> str:
        """Return a valid Bearer token, refreshing if expired."""
        now = time.time()
        if self._token.access_token and now < self._token.expires_at - 60:
            return self._token.access_token

        logger.debug("Requesting new Zoom OAuth token")
        resp = self._http.post(
            ZOOM_OAUTH_URL,
            params={"grant_type": "account_credentials", "account_id": self._creds.account_id},
            auth=(self._creds.client_id, self._creds.client_secret),
        )
        resp.raise_for_status()
        data = resp.json()
        self._token.access_token = data["access_token"]
        self._token.expires_at = now + data.get("expires_in", 3600)
        logger.debug("Token acquired, expires in %ds", data.get("expires_in", 3600))
        return self._token.access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._ensure_token()}"}

    # ----- Low-level request with retry ----------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        url = f"{ZOOM_API_BASE}{path}"

        for attempt in range(1, MAX_RETRIES + 1):
            headers = self._headers()
            try:
                resp = self._http.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    data=data,
                    files=files,
                    params=params,
                )

                # Rate limited — back off
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", BACKOFF_BASE**attempt))
                    logger.warning("Rate limited by Zoom. Retrying in %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                # Token expired mid-session — refresh and retry
                if resp.status_code == 401:
                    logger.debug("Token expired mid-session, refreshing")
                    self._token.access_token = ""
                    continue

                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError:
                if attempt == MAX_RETRIES:
                    raise
                wait = BACKOFF_BASE**attempt
                logger.warning("Zoom API error, retry %d/%d in %.1fs", attempt, MAX_RETRIES, wait)
                time.sleep(wait)

        raise RuntimeError("Zoom API request failed after all retries")

    # ----- Virtual Background endpoints ----------------------------------

    def list_backgrounds(self) -> list[VirtualBackground]:
        """GET /v2/users/me/settings → extract virtual_backgrounds list."""
        resp = self._request("GET", "/users/me/settings")
        data = resp.json()

        vb_settings = data.get("in_meeting", {}).get("virtual_background_settings", {})
        files = vb_settings.get("files", [])

        backgrounds = []
        for f in files:
            backgrounds.append(
                VirtualBackground(
                    id=f.get("id", ""),
                    name=f.get("name", ""),
                    size=f.get("size", 0),
                    is_default=f.get("is_default", False),
                    type=f.get("type", "image"),
                )
            )
        return backgrounds

    def upload_background(self, file_path: Path) -> VirtualBackground:
        """POST multipart upload of an image file as a virtual background."""
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "image/jpeg")}
            resp = self._request(
                "POST",
                "/users/me/settings/virtual_backgrounds",
                files=files,
            )

        data = resp.json()
        return VirtualBackground(
            id=data.get("id", ""),
            name=data.get("name", file_path.name),
            size=data.get("size", 0),
            is_default=data.get("is_default", False),
        )

    def delete_background(self, file_id: str) -> None:
        """DELETE a virtual background by its file ID."""
        self._request(
            "DELETE",
            "/users/me/settings/virtual_backgrounds",
            params={"file_ids": file_id},
        )
        logger.info("Deleted virtual background %s", file_id)

    def set_default(self, file_id: str) -> bool:
        """Attempt to set a background as default via PATCH.

        Returns True on success, False if the endpoint doesn't behave as expected
        (known Zoom API limitation for user-level accounts).
        """
        try:
            self._request(
                "PATCH",
                "/users/me/settings",
                json={
                    "in_meeting": {
                        "virtual_background_settings": {
                            "files": [{"id": file_id, "is_default": True}]
                        }
                    }
                },
            )
            logger.info("Set background %s as default", file_id)
            return True
        except Exception as exc:
            logger.warning(
                "Could not set default background (known Zoom limitation): %s", exc
            )
            return False

    # ----- Lifecycle management ------------------------------------------

    def get_managed_backgrounds(self) -> list[VirtualBackground]:
        """Return only tool-managed backgrounds, oldest first by name (date-sorted)."""
        all_bgs = self.list_backgrounds()
        managed = [bg for bg in all_bgs if bg.is_managed]
        managed.sort(key=lambda bg: bg.name)
        return managed

    def enforce_cap(self, max_managed: int = 5) -> list[str]:
        """Delete oldest tool-managed images to stay within the cap.

        Returns list of deleted file IDs.
        """
        all_bgs = self.list_backgrounds()
        managed = sorted(
            [bg for bg in all_bgs if bg.is_managed],
            key=lambda bg: bg.name,
        )
        total = len(all_bgs)
        managed_count = len(managed)

        deleted_ids: list[str] = []

        # Delete if we'd exceed Zoom's hard 10-file cap or our managed cap
        while managed and (total >= 10 or managed_count >= max_managed):
            oldest = managed.pop(0)
            self.delete_background(oldest.id)
            deleted_ids.append(oldest.id)
            total -= 1
            managed_count -= 1
            logger.info("Removed oldest managed background: %s", oldest.name)

        return deleted_ids

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
