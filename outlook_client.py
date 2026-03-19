"""
Outlook Calendar Reader — extracted from CalendarApp v1 ms365_sync.py

Read-only Graph API client for fetching Outlook calendar events.
Used by the Compare View to display Outlook events alongside PerfectServe data.

No write/push/sync operations — this is strictly read-only.
"""

import os
import json
import atexit
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

try:
    from distribution import load_user_settings
except ImportError:
    def load_user_settings(): return {}

try:
    import msal
    import requests
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False


SCOPES = [
    "User.Read",
    "Calendars.Read",
]

_CACHE_FILENAME = "msal_token_cache.bin"
_CACHE_PATH = Path.home() / ".calendarapp" / _CACHE_FILENAME


class OutlookCalendarReader:
    """Read-only Outlook calendar client using Microsoft Graph API."""

    def __init__(self, *, enabled: bool = False):
        self.enabled = enabled
        self.available = False
        self.config_error: Optional[str] = None
        self.app: Optional['msal.PublicClientApplication'] = None
        self.cache: Optional['msal.SerializableTokenCache'] = None
        self.tenant_id: Optional[str] = None
        self.client_id: Optional[str] = None

        if not self.enabled:
            return

        if not _DEPS_AVAILABLE:
            self.config_error = "Outlook dependencies missing (pip install msal requests)."
            return

        settings = load_user_settings()
        outlook_cfg = settings.get("outlook", {})

        try:
            from distribution import load_system_config
            system_config = load_system_config()
        except ImportError:
            system_config = {}

        self.tenant_id = (
            os.environ.get("AZURE_TENANT_ID")
            or outlook_cfg.get("tenant_id")
            or settings.get("azure_tenant_id")
            or system_config.get("azure_tenant_id")
        )
        self.client_id = (
            os.environ.get("AZURE_CLIENT_ID")
            or outlook_cfg.get("client_id")
            or settings.get("azure_client_id")
            or system_config.get("azure_client_id")
        )

        if not self.tenant_id or not self.client_id:
            missing = []
            if not self.tenant_id:
                missing.append("Azure Tenant ID")
            if not self.client_id:
                missing.append("Azure Client ID")
            self.config_error = (
                "Missing Outlook configuration: "
                + ", ".join(missing)
                + ". Set AZURE_TENANT_ID and AZURE_CLIENT_ID environment variables."
            )
            return

        self.cache = msal.SerializableTokenCache()
        self._load_cache()
        atexit.register(self._save_cache)

        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        try:
            self.app = msal.PublicClientApplication(
                self.client_id,
                authority=authority,
                token_cache=self.cache,
            )
            self.available = True
        except Exception:
            self.config_error = "Failed to initialize Outlook authentication."

    def _load_cache(self):
        if not self.cache:
            return
        if not _CACHE_PATH.parent.exists():
            try:
                _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        if _CACHE_PATH.exists():
            try:
                with open(_CACHE_PATH, "r") as f:
                    self.cache.deserialize(f.read())
            except Exception:
                pass

    def _save_cache(self):
        if not self.cache or not self.app:
            return
        if self.cache.has_state_changed:
            try:
                _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(_CACHE_PATH, "w") as f:
                    f.write(self.cache.serialize())
            except Exception:
                pass

    def _acquire_access_token(self) -> Optional[str]:
        if not self.enabled or not self.available or not self.app:
            return None

        accounts = self.app.get_accounts()
        result = None

        if accounts:
            result = self.app.acquire_token_silent(SCOPES, account=accounts[0])

        if not result:
            try:
                result = self.app.acquire_token_interactive(scopes=SCOPES)
            except Exception:
                return None

        if result and "access_token" in result:
            return result["access_token"]
        return None

    def test_connection(self) -> bool:
        """Returns True if authentication and a basic Graph request succeed."""
        if not self.enabled or not self.available:
            return False
        try:
            token = self._acquire_access_token()
            if not token:
                return False
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False

    def list_calendars(self) -> List[dict]:
        """
        List all calendar folders available to the user.
        Returns list of {"id": str, "name": str, "owner": str|None}.
        """
        if not self.enabled:
            return []
        token = self._acquire_access_token()
        if not token:
            return []
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(
                "https://graph.microsoft.com/v1.0/me/calendars?$select=id,name,owner",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "owner": item.get("owner", {}).get("name"),
                    }
                    for item in data.get("value", [])
                ]
            return []
        except Exception:
            return []

    def list_events_in_range(
        self,
        *,
        calendar_id: str,
        range_start: datetime,
        range_end: datetime,
    ) -> tuple[List[dict], Optional[str]]:
        """
        Fetch events from a specific calendar within a date range.
        Returns (events_list, error_string_or_None).
        """
        if not self.enabled or not self.available:
            return [], "Outlook reader not available."

        token = self._acquire_access_token()
        if not token:
            return [], "No access token available."

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="America/Chicago"',
        }
        start_iso = range_start.isoformat()
        end_iso = range_end.isoformat()
        events_url = (
            f"https://graph.microsoft.com/v1.0/me/calendars/{calendar_id}/events"
            f"?$select=id,subject,start,end,location,body"
            f"&$filter=start/dateTime ge '{start_iso}' and start/dateTime lt '{end_iso}'"
            f"&$orderby=start/dateTime"
        )

        events: List[dict] = []
        next_url: Optional[str] = events_url
        max_pages = 10

        while next_url and max_pages > 0:
            max_pages -= 1
            try:
                resp = requests.get(next_url, headers=headers, timeout=10)
            except Exception as exc:
                return [], f"Failed to fetch events: {exc}"
            if resp.status_code != 200:
                return [], f"Graph API error: {resp.status_code} - {resp.text[:200]}"
            payload = resp.json()
            events.extend(payload.get("value", []))
            next_url = payload.get("@odata.nextLink")

        return events, None
