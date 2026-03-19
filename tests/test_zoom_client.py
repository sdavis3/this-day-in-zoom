"""Tests for tdiz.zoom_client — OAuth, VB CRUD, lifecycle management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tdiz.config import ZoomCredentials
from tdiz.zoom_client import MANAGED_PREFIX, VirtualBackground, ZoomClient


@pytest.fixture
def creds():
    return ZoomCredentials(
        account_id="test-acct",
        client_id="test-client",
        client_secret="test-secret",
    )


@pytest.fixture
def mock_http(creds):
    """Return a ZoomClient with a mocked httpx.Client."""
    client = ZoomClient(creds)
    client._http = MagicMock()
    # Pre-set a valid token so we skip OAuth calls
    client._token.access_token = "mock-token"
    client._token.expires_at = 9999999999.0
    return client


class TestVirtualBackground:
    def test_is_managed_true(self):
        bg = VirtualBackground(id="1", name="tdiz_03-18_test.jpg", size=100, is_default=False)
        assert bg.is_managed is True

    def test_is_managed_false(self):
        bg = VirtualBackground(id="1", name="my-custom-bg.jpg", size=100, is_default=False)
        assert bg.is_managed is False


class TestLifecycleManagement:
    def _make_backgrounds(self, managed_names: list[str], user_names: list[str]) -> list[dict]:
        """Build a list of VB dicts as the Zoom API would return."""
        bgs = []
        for i, name in enumerate(managed_names):
            bgs.append({"id": f"m{i}", "name": name, "size": 1000, "is_default": False})
        for i, name in enumerate(user_names):
            bgs.append({"id": f"u{i}", "name": name, "size": 1000, "is_default": False})
        return bgs

    def test_enforce_cap_deletes_oldest_managed(self, mock_http):
        managed = [
            f"tdiz_03-{i:02d}_event{i}.jpg" for i in range(1, 7)  # 6 managed
        ]
        user = ["my-bg.jpg", "office.png"]  # 2 user
        files = self._make_backgrounds(managed, user)

        # Mock the GET response for list_backgrounds
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "in_meeting": {
                "virtual_background_settings": {"files": files}
            }
        }
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_http._http.request.return_value = mock_resp

        # enforce_cap with max_managed=5 should delete 1 (oldest)
        deleted = mock_http.enforce_cap(max_managed=5)

        # The first call is the GET (list), subsequent calls are DELETEs
        delete_calls = [
            c for c in mock_http._http.request.call_args_list
            if c[0][0] == "DELETE"
        ]
        assert len(delete_calls) >= 1

    def test_enforce_cap_respects_zoom_10_limit(self, mock_http):
        managed = [f"tdiz_03-{i:02d}_e{i}.jpg" for i in range(1, 9)]  # 8 managed
        user = ["a.jpg", "b.jpg"]  # 2 user — total = 10
        files = self._make_backgrounds(managed, user)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "in_meeting": {
                "virtual_background_settings": {"files": files}
            }
        }
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_http._http.request.return_value = mock_resp

        deleted = mock_http.enforce_cap(max_managed=5)
        # Should delete enough managed images to get below both caps
        assert len(deleted) >= 3  # 8 managed → need to get to 5, and total to <10

    def test_enforce_cap_no_action_when_under_limit(self, mock_http):
        managed = [f"tdiz_03-0{i}_e{i}.jpg" for i in range(1, 3)]  # 2 managed
        user = ["a.jpg"]  # 1 user — total = 3
        files = self._make_backgrounds(managed, user)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "in_meeting": {
                "virtual_background_settings": {"files": files}
            }
        }
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_http._http.request.return_value = mock_resp

        deleted = mock_http.enforce_cap(max_managed=5)
        assert deleted == []


class TestGetManagedBackgrounds:
    def test_filters_only_managed(self, mock_http):
        files = [
            {"id": "1", "name": "tdiz_03-18_apollo.jpg", "size": 100, "is_default": False},
            {"id": "2", "name": "my-office.jpg", "size": 200, "is_default": True},
            {"id": "3", "name": "tdiz_03-17_eiffel.jpg", "size": 150, "is_default": False},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "in_meeting": {"virtual_background_settings": {"files": files}}
        }
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_http._http.request.return_value = mock_resp

        managed = mock_http.get_managed_backgrounds()
        assert len(managed) == 2
        assert all(bg.is_managed for bg in managed)
        # Should be sorted by name (date order)
        assert managed[0].name < managed[1].name
