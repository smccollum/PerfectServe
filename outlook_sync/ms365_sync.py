"""
This module will eventually handle push-only sync from CalendarApp -> Outlook

It is intentionally inert at this stage
No side effects occur by importing it
"""
import os
import json
import atexit
import logging
import time as time_module
from typing import Optional, Dict, Any, List, Generator, Tuple
from pathlib import Path
from datetime import datetime, time, timedelta, date

# Internal dependencies
try:
    from distribution import load_user_settings
except ImportError:
    # Fallback if run standalone or in tests without distribution
    def load_user_settings(): return {}

# External dependencies (Standard Library is preferred where possible, but using msal/requests as permitted)
try:
    import msal
    import requests
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False


# ------------------------------------------------------------------------------
# Constants & Configuration
# ------------------------------------------------------------------------------

SCOPES = [
    "User.Read",
    "Calendars.ReadWrite",
    "Calendars.ReadWrite.Shared",
]

CALENDARAPP_IDENTITY_PROP_ID = (
    "String {554ce722-8c50-4ef7-88fb-445f0c3b6c8e} Name CalendarApp.AppEventId"
)

# Cache file in the user's home directory or local app data would be ideal,
# but for now we'll keep it relative or use a sensible default.
# Using a hidden file in the user's home directory is safer than the current directory.
_CACHE_FILENAME = "msal_token_cache.bin"
_CACHE_PATH = Path.home() / ".calendarapp" / _CACHE_FILENAME


class OutlookSyncClient:
    def __init__(self, *, enabled: bool = False):
        self.enabled = enabled
        self.available = False
        self.config_error: Optional[str] = None
        self.app: Optional['msal.PublicClientApplication'] = None
        self.cache: Optional['msal.SerializableTokenCache'] = None
        self.tenant_id: Optional[str] = None
        self.client_id: Optional[str] = None
        self.account: Optional[Dict[str, Any]] = None

        if not self.enabled:
            return

        if not _DEPS_AVAILABLE:
            # Mark as unavailable but do not crash
            self.config_error = "Outlook sync dependencies are missing."
            return

        # 1. Load Environment Variables, User Settings, or System Config (in priority order)
        settings = load_user_settings()
        outlook_cfg = settings.get("outlook", {})
        
        # Import system config for fallback
        try:
            from distribution import load_system_config
            system_config = load_system_config()
        except ImportError:
            system_config = {}
        
        # Priority: env var > user config > system config
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
            # Mark as unavailable (missing config)
            missing = []
            if not self.tenant_id:
                missing.append("Azure Tenant ID")
            if not self.client_id:
                missing.append("Azure Client ID")
            self.config_error = (
                "Missing Outlook configuration: "
                + ", ".join(missing)
                + ". Please set values in Outlook Settings or system defaults."
            )
            return

        # 2. Initialize Token Cache
        self.cache = msal.SerializableTokenCache()
        self._load_cache()
        
        # 3. Register persistence hook
        # We save on exit. We could also save immediately after token acquisition.
        atexit.register(self._save_cache)

        # 4. Initialize Public Client Application
        # Authority URL for single tenant
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        
        try:
            self.app = msal.PublicClientApplication(
                self.client_id,
                authority=authority,
                token_cache=self.cache
            )
            self.available = True
        except Exception:
            # Failed to initialize MSAL
            self.available = False
            self.config_error = "Failed to initialize Outlook authentication."

    def _load_cache(self):
        if not self.cache:
            return
        
        # Ensure directory exists
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
                # Cache corrupted or unreadable, ignore
                pass

    def _save_cache(self):
        if not self.cache or not self.app:
            return
        
        if self.cache.has_state_changed:
            try:
                # Ensure directory exists (in case it was deleted)
                _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(_CACHE_PATH, "w") as f:
                    f.write(self.cache.serialize())
            except Exception:
                # Best effort save
                pass

    def _acquire_access_token(self) -> Optional[str]:
        """
        Acquire a token interactively or silently.
        """
        if not self.enabled or not self.available or not self.app:
            return None

        result = None
        accounts = self.app.get_accounts()
        
        # 1. Try Silent Auth
        if accounts:
            # Pick the first account (sufficient for now)
            result = self.app.acquire_token_silent(SCOPES, account=accounts[0])

        # 2. Try Interactive Auth if silent failed
        if not result:
            try:
                print("Initiating interactive authentication...")
                result = self.app.acquire_token_interactive(scopes=SCOPES)
            except Exception:
                return None

        if result and "access_token" in result:
            return result["access_token"]
        
        return None

    def test_connection(self) -> bool:
        """
        Returns True if authentication and a basic Graph request succeed.
        Returns False otherwise.
        Never raises.
        """
        if not self.enabled or not self.available:
            return False

        try:
            token = self._acquire_access_token()
            if not token:
                return False

            # Basic Graph Request
            # Using requests directly as permitted by instruction
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
                timeout=10
            )

            return response.status_code == 200

        except Exception:
            return False

    def sync_calendar(self, calendar_data: dict, settings: Optional[dict] = None) -> dict:
        """
        Push calendar data to Outlook.
        Deprecated: Use sync_events instead. Keeping for Stage 1 contract compatibility.
        """
        return self.sync_events(calendar_data, dry_run=False, settings=settings)

    def list_calendars(self) -> List[dict]:
        """
        List all calendar folders available to the user.
        Returns a list of dicts: {"id": str, "name": str, "owner": str|None}
        """
        if not self.enabled:
            return []
        
        token = self._acquire_access_token()
        if not token:
            return []
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        try:
            # We want /me/calendars
            # $select=id,name,owner
            resp = requests.get(
                "https://graph.microsoft.com/v1.0/me/calendars?$select=id,name,owner",
                headers=headers,
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                calendars = []
                for item in data.get("value", []):
                    owner = item.get("owner", {}).get("name")
                    calendars.append({
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "owner": owner
                    })
                return calendars
            else:
                return []
        except Exception:
            return []

    def _list_events_in_range(
        self,
        *,
        token: str,
        calendar_id: str,
        range_start: datetime,
        range_end: datetime,
    ) -> tuple[List[dict], Optional[str]]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="America/Chicago"',
        }
        start_iso = range_start.isoformat()
        end_iso = range_end.isoformat()
        base_url = "https://graph.microsoft.com/v1.0/me"
        events_url = (
            f"{base_url}/calendars/{calendar_id}/events"
            f"?$select=id,subject,start,end"
            f"&$filter=start/dateTime ge '{start_iso}' and start/dateTime lt '{end_iso}'"
            f"&$expand=singleValueExtendedProperties($filter=id eq '{CALENDARAPP_IDENTITY_PROP_ID}')"
        )
        events: List[dict] = []
        next_url: Optional[str] = events_url
        attempts = 0
        max_attempts = 5
        while next_url:
            attempts += 1
            try:
                resp = requests.get(next_url, headers=headers, timeout=10)
            except Exception as exc:
                return [], f"Failed to list Outlook events: {exc}"
            if resp.status_code in {429, 503, 504}:
                if attempts >= max_attempts:
                    return [], f"Failed to list Outlook events: {resp.status_code} - {resp.text[:200]}"
                retry_after = resp.headers.get("Retry-After")
                sleep_seconds = 2
                if retry_after and retry_after.isdigit():
                    sleep_seconds = max(1, int(retry_after))
                time_module.sleep(sleep_seconds)
                continue
            if resp.status_code != 200:
                return [], f"Failed to list Outlook events: {resp.status_code} - {resp.text[:200]}"
            payload = resp.json()
            events.extend(payload.get("value", []))
            next_url = payload.get("@odata.nextLink")
        return events, None

    def sync_events(
        self,
        calendar_json: dict,
        dry_run: bool = False,
        target_calendar_id: Optional[str] = None,
        settings: Optional[dict] = None,
    ) -> dict:
        """
        Synchronize calendar data to Outlook.
        
        Performs CREATE (POST) or UPDATE (PATCH).
        Deletes events only when a cell becomes unassigned and has a stored event_id.
        
        :param target_calendar_id: If set, target this specific calendar.
                                   If retrieval fails, ABORT (Strict Mode).
                                   If None, use default /me/events.
        """
        stats = {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
            "skip_categories": {},
            "error_categories": {},
            "skipped_invalid_team_id": 0,
            "skipped_no_calendar": 0,
            "skipped_invalid_identity": 0,
            "skipped_unassigned_doctor": 0,
            "skipped_not_managed": 0,
        }
        settings = settings if isinstance(settings, dict) else {}

        def _record_category(store: dict, key: str, message: Optional[str] = None) -> None:
            entry = store.setdefault(key, {"count": 0, "examples": []})
            entry["count"] += 1
            if message and len(entry["examples"]) < 5:
                entry["examples"].append(message)

        def _record_skip(key: str, message: Optional[str] = None) -> None:
            stats["skipped"] += 1
            stats_key = f"skipped_{key}"
            if stats_key in stats:
                stats[stats_key] += 1
            _record_category(stats["skip_categories"], key, message)

        def _record_error(key: str, message: str) -> None:
            stats["failed"] += 1
            stats["errors"].append(message)
            _record_category(stats["error_categories"], key, message)

        def _count_shift_cells(payload: dict) -> int:
            days = payload.get("days", [])
            if isinstance(days, dict):
                count = 0
                for day_data in days.values():
                    if not isinstance(day_data, dict):
                        continue
                    shifts = day_data.get("shifts", [])
                    if isinstance(shifts, list):
                        count += len([s for s in shifts if isinstance(s, dict)])
                return count
            if isinstance(days, list):
                count = 0
                for day_data in days:
                    if not isinstance(day_data, dict):
                        continue
                    shifts = day_data.get("shifts", [])
                    if isinstance(shifts, list):
                        count += len([s for s in shifts if isinstance(s, dict)])
                return count
            return 0

        shift_total = _count_shift_cells(calendar_json)

        team_id = calendar_json.get("team_id")
        valid_team_ids = {f"team-{idx}" for idx in range(1, 8)}
        if not isinstance(team_id, str) or team_id not in valid_team_ids:
            logging.warning("Missing or invalid team_id for Outlook sync; skipping all shifts.")
            for _ in range(shift_total):
                _record_skip("invalid_team_id", "Missing or invalid team_id; skipping shift.")
            return stats

        if not target_calendar_id:
            for _ in range(shift_total):
                _record_skip("no_calendar", "Missing target calendar binding; skipping shift.")
            return stats

        if not calendar_json.get("facility_id"):
            for _ in range(shift_total):
                _record_skip("invalid_identity", "Missing facility_id; invalid identity payload.")
            return stats

        # 1. Acquire Token (Required for preview as well)
        token = None
        if not self.enabled:
            _record_error("auth", "Sync disabled.")
            return stats
        if not self.available:
            _record_error("auth", self.config_error or "Outlook sync is unavailable.")
            return stats

        try:
            token = self._acquire_access_token()
        except Exception as e:
            _record_error("auth", f"Auth failed: {e}")
            return stats

        if not token:
            _record_error("auth", "No access token available.")
            return stats

        # Prepare Headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # 2. Resolve Base URL
        base_url = "https://graph.microsoft.com/v1.0/me"

        if target_calendar_id:
            # STRICT mode: Verify calendar existence first or assume strict path
            # A simple way to verify/target is to use the full URL:
            # /me/calendars/{id}/events
            base_url = f"https://graph.microsoft.com/v1.0/me/calendars/{target_calendar_id}"
        events_endpoint = f"{base_url}/events"

        # 2. Read existing CalendarApp-owned events in scope
        existing_events: Dict[str, List[str]] = {}
        year = calendar_json.get("year")
        month = calendar_json.get("month")
        try:
            year_int = int(year)
            month_int = int(month)
            range_start = datetime(year_int, month_int, 1)
            if month_int == 12:
                range_end = datetime(year_int + 1, 1, 1)
            else:
                range_end = datetime(year_int, month_int + 1, 1)
        except (TypeError, ValueError):
            _record_error("invalid_scope", "Invalid year/month; cannot determine sync scope.")
            return stats

        events, error = self._list_events_in_range(
            token=token,
            calendar_id=target_calendar_id,
            range_start=range_start,
            range_end=range_end,
        )
        if error:
            _record_error("list_events", error)
            return stats

        for event in events:
            identity = parse_event_identity(event, expected_team_id=team_id)
            if not identity:
                continue
            identity_json = identity["json"]
            event_id = event.get("id")
            if not event_id:
                continue
            existing_events.setdefault(identity_json, []).append(event_id)

        def _request_with_retries(
            method: str,
            url: str,
            json_payload: Optional[dict] = None,
        ) -> tuple[Optional[requests.Response], Optional[str]]:
            delays = [2, 4, 8]
            for attempt in range(len(delays) + 1):
                try:
                    resp = requests.request(
                        method,
                        url,
                        headers=headers,
                        json=json_payload,
                        timeout=10,
                    )
                except Exception as exc:
                    return None, f"Network error: {exc}"
                if resp.status_code == 429 and attempt < len(delays):
                    time_module.sleep(delays[attempt])
                    continue
                return resp, None
            return None, "Rate limit retries exhausted."

        def _fetch_event_for_delete(event_id: str) -> tuple[Optional[dict], Optional[str], Optional[int]]:
            expand_query = (
                f"$expand=singleValueExtendedProperties($filter=id eq '{CALENDARAPP_IDENTITY_PROP_ID}')"
            )
            url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}?{expand_query}"
            resp, error = _request_with_retries("GET", url)
            if error:
                return None, error, None
            if not resp:
                return None, "No response from Graph.", None
            if resp.status_code == 404:
                return None, None, 404
            if resp.status_code in {401, 403}:
                return None, f"Auth error fetching event {event_id}: {resp.status_code}", resp.status_code
            if resp.status_code != 200:
                return None, f"Fetch failed for {event_id}: {resp.status_code} - {resp.text[:100]}", resp.status_code
            return resp.json(), None, 200

        # 3. Traverse and Sync
        days_value = calendar_json.get("days")
        days_type = type(days_value).__name__
        top_level_keys = ", ".join(sorted(calendar_json.keys()))
        shift_count = 0
        batch_identities: Dict[str, int] = {}
        for _, _, identity_json in iter_shifts_and_payloads(calendar_json, settings=settings):
            if not identity_json:
                continue
            batch_identities[identity_json] = batch_identities.get(identity_json, 0) + 1

        conflicted_identities = {
            identity for identity, count in batch_identities.items() if count > 1
        }
        for identity_json, ids in existing_events.items():
            if len(ids) > 1:
                conflicted_identities.add(identity_json)

        for shift_ref, payload, identity_json in iter_shifts_and_payloads(calendar_json, settings=settings):
            shift_count += 1

            if not payload or not identity_json:
                _record_skip("invalid_identity", "Missing or invalid identity payload.")
                continue
            if identity_json in conflicted_identities:
                _record_skip("invalid_identity", "Duplicate identity detected; skipping shift.")
                continue

            if _is_unassigned_doctor(shift_ref):
                event_id = shift_ref.get("outlook_event_id")
                if isinstance(event_id, str) and event_id:
                    if dry_run:
                        stats["deleted"] += 1
                        shift_ref["outlook_event_id"] = None
                    else:
                        event_payload, fetch_error, fetch_status = _fetch_event_for_delete(event_id)
                        if fetch_status == 404:
                            stats["deleted"] += 1
                            shift_ref["outlook_event_id"] = None
                        elif fetch_status in {401, 403}:
                            _record_error("auth", fetch_error or "Auth error during delete fetch.")
                            return stats
                        elif fetch_error:
                            _record_error("delete", fetch_error)
                        else:
                            identity = parse_event_identity(event_payload, expected_team_id=team_id)
                            if not identity:
                                _record_skip("not_managed", f"Event {event_id} missing CalendarApp identity.")
                            else:
                                delete_url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}"
                                resp, error = _request_with_retries("DELETE", delete_url)
                                if error:
                                    _record_error("delete", error)
                                elif not resp:
                                    _record_error("delete", f"Delete failed for {event_id}: no response.")
                                elif resp.status_code in {202, 204}:
                                    stats["deleted"] += 1
                                    shift_ref["outlook_event_id"] = None
                                elif resp.status_code == 404:
                                    stats["deleted"] += 1
                                    shift_ref["outlook_event_id"] = None
                                elif resp.status_code in {401, 403}:
                                    _record_error(
                                        "auth",
                                        f"Auth error deleting {event_id}: {resp.status_code}",
                                    )
                                    return stats
                                elif resp.status_code == 429:
                                    _record_error(
                                        "delete",
                                        f"Delete rate limited for {event_id}: {resp.status_code}",
                                    )
                                else:
                                    _record_error(
                                        "delete",
                                        f"Delete failed for {event_id}: {resp.status_code} - {resp.text[:100]}",
                                    )
                else:
                    _record_skip("unassigned_doctor", "Unassigned doctor; no event_id to delete.")
                continue

            outlook_id = None
            mapped_id = shift_ref.get("outlook_event_id")
            if isinstance(mapped_id, str) and mapped_id:
                outlook_id = mapped_id
            else:
                outlook_ids = existing_events.get(identity_json, [])
                outlook_id = outlook_ids[0] if outlook_ids else None

            if outlook_id:
                if dry_run:
                    stats["updated"] += 1
                    shift_ref["outlook_event_id"] = outlook_id
                    continue
                update_url = f"https://graph.microsoft.com/v1.0/me/events/{outlook_id}"
                resp, error = _request_with_retries("PATCH", update_url, json_payload=payload)
                if error:
                    _record_error("update", error)
                    continue
                if not resp:
                    _record_error("update", f"Update failed for {outlook_id}: no response.")
                    continue
                if resp.status_code == 200:
                    stats["updated"] += 1
                    shift_ref["outlook_event_id"] = outlook_id
                elif resp.status_code == 404:
                    shift_ref["outlook_event_id"] = None
                    resp_create, error_create = _request_with_retries(
                        "POST",
                        events_endpoint,
                        json_payload=payload,
                    )
                    if error_create:
                        _record_error("create", error_create)
                        continue
                    if not resp_create:
                        _record_error("create", "Create failed after 404 update; no response.")
                        continue
                    if resp_create.status_code == 201:
                        stats["created"] += 1
                        new_event = resp_create.json()
                        shift_ref["outlook_event_id"] = new_event.get("id")
                    elif resp_create.status_code in {401, 403}:
                        _record_error(
                            "auth",
                            f"Auth error creating after 404 update: {resp_create.status_code}",
                        )
                        return stats
                    elif resp_create.status_code == 429:
                        _record_error(
                            "create",
                            f"Create rate limited after 404 update: {resp_create.status_code}",
                        )
                    else:
                        _record_error(
                            "create",
                            f"Create failed after 404 update: {resp_create.status_code} - {resp_create.text[:100]}",
                        )
                elif resp.status_code in {401, 403}:
                    _record_error("auth", f"Auth error updating {outlook_id}: {resp.status_code}")
                    return stats
                elif resp.status_code == 429:
                    _record_error("update", f"Update rate limited for {outlook_id}: {resp.status_code}")
                elif resp.status_code == 409:
                    _record_error("update", f"Update conflict for {outlook_id}: {resp.status_code}")
                else:
                    _record_error(
                        "update",
                        f"Update failed for {outlook_id}: {resp.status_code} - {resp.text[:100]}",
                    )
                continue

            if dry_run:
                stats["created"] += 1
                continue
            resp, error = _request_with_retries("POST", events_endpoint, json_payload=payload)
            if error:
                _record_error("create", error)
                continue
            if not resp:
                _record_error("create", "Create failed: no response.")
                continue
            if resp.status_code == 201:
                stats["created"] += 1
                new_event = resp.json()
                shift_ref["outlook_event_id"] = new_event.get("id")
            elif resp.status_code in {401, 403}:
                _record_error("auth", f"Auth error creating event: {resp.status_code}")
                return stats
            elif resp.status_code == 404:
                _record_error("create", f"Target calendar not found ({target_calendar_id}).")
                return stats
            elif resp.status_code == 429:
                _record_error("create", f"Create rate limited: {resp.status_code}")
            else:
                _record_error(
                    "create",
                    f"Create failed: {resp.status_code} - {resp.text[:100]}",
                )

        if shift_count == 0:
            _record_error(
                "no_shifts",
                "Warning: 0 shifts found (days type: "
                f"{days_type}; top-level keys: {top_level_keys}).",
            )

        return stats

    def delete_events(self, event_ids: List[str]) -> dict:
        """
        Deletes Outlook events by ID.
        Returns stats dict with deleted/failed counts and errors.
        """
        stats = {
            "deleted": 0,
            "failed": 0,
            "errors": [],
            "deleted_ids": [],
        }
        if not event_ids:
            return stats

        if not self.enabled:
            stats["errors"].append("Cleanup disabled.")
            return stats
        if not self.available:
            stats["errors"].append(self.config_error or "Outlook cleanup is unavailable.")
            return stats

        try:
            token = self._acquire_access_token()
        except Exception as e:
            stats["failed"] += len(event_ids)
            stats["errors"].append(f"Auth failed: {e}")
            return stats

        if not token:
            stats["failed"] += len(event_ids)
            stats["errors"].append("No access token available.")
            return stats

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        for event_id in event_ids:
            try:
                resp = requests.delete(
                    f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in {202, 204}:
                    stats["deleted"] += 1
                    stats["deleted_ids"].append(event_id)
                elif resp.status_code == 404:
                    # Event already gone; treat as deleted to clear local cache.
                    stats["deleted"] += 1
                    stats["deleted_ids"].append(event_id)
                else:
                    stats["failed"] += 1
                    stats["errors"].append(
                        f"Delete failed for {event_id}: {resp.status_code} - {resp.text[:100]}"
                    )
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append(f"Delete error for {event_id}: {e}")

        return stats

    def delete_events_for_month(
        self,
        *,
        calendar_json: dict,
        target_calendar_id: Optional[str],
    ) -> dict:
        stats = {
            "deleted": 0,
            "failed": 0,
            "errors": [],
            "deleted_ids": [],
        }
        if not target_calendar_id:
            stats["errors"].append("Missing target calendar binding.")
            stats["failed"] += 1
            return stats
        if not self.enabled:
            stats["errors"].append("Cleanup disabled.")
            return stats
        if not self.available:
            stats["errors"].append(self.config_error or "Outlook cleanup is unavailable.")
            return stats

        try:
            token = self._acquire_access_token()
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append(f"Auth failed: {e}")
            return stats

        if not token:
            stats["failed"] += 1
            stats["errors"].append("No access token available.")
            return stats

        year = calendar_json.get("year")
        month = calendar_json.get("month")
        team_id = calendar_json.get("team_id")
        facility_id = calendar_json.get("facility_id")
        if not team_id or not facility_id:
            stats["failed"] += 1
            stats["errors"].append("Missing team_id or facility_id; cannot scope cleanup.")
            return stats
        try:
            year_int = int(year)
            month_int = int(month)
            range_start = datetime(year_int, month_int, 1)
            if month_int == 12:
                range_end = datetime(year_int + 1, 1, 1)
            else:
                range_end = datetime(year_int, month_int + 1, 1)
        except (TypeError, ValueError):
            stats["failed"] += 1
            stats["errors"].append("Invalid year/month; cannot determine cleanup scope.")
            return stats

        events, error = self._list_events_in_range(
            token=token,
            calendar_id=target_calendar_id,
            range_start=range_start,
            range_end=range_end,
        )
        if error:
            stats["failed"] += 1
            stats["errors"].append(error)
            return stats

        event_ids: List[str] = []
        by_identity: Dict[str, List[str]] = {}
        for event in events:
            identity = parse_event_identity(event, expected_team_id=team_id)
            if not identity:
                continue
            identity_payload = identity["identity"]
            if identity_payload.get("f") != facility_id:
                continue
            date_str = identity_payload.get("d")
            try:
                date_obj = date.fromisoformat(date_str)
            except (TypeError, ValueError):
                continue
            if date_obj.year != year_int or date_obj.month != month_int:
                continue
            event_id = event.get("id")
            if event_id:
                by_identity.setdefault(identity["json"], []).append(event_id)

        for identity_json, ids in by_identity.items():
            if len(ids) > 1:
                stats["errors"].append(
                    f"Duplicate identity in Outlook for {identity_json}; skipping delete for this identity."
                )
                continue
            event_ids.append(ids[0])

        if not event_ids:
            return stats

        delete_stats = self.delete_events(event_ids)
        stats["deleted"] = delete_stats.get("deleted", 0)
        stats["failed"] = delete_stats.get("failed", 0)
        stats["errors"] = delete_stats.get("errors", [])
        stats["deleted_ids"] = delete_stats.get("deleted_ids", [])
        return stats


# ------------------------------------------------------------------------------
# Pure Helpers (Stage 4)
# ------------------------------------------------------------------------------

def build_identity_json(
    *,
    team_id: str,
    facility_id: str,
    date_obj: date,
    shift_type: str,
    row_index: int,
) -> str:
    payload = {
        "t": team_id,
        "f": facility_id,
        "d": date_obj.isoformat(),
        "s": shift_type,
        "r": row_index,
    }
    return json.dumps(payload, separators=(",", ":"))


def parse_event_identity(event: dict, expected_team_id: Optional[str]) -> Optional[dict]:
    props = event.get("singleValueExtendedProperties") or []
    identity_value = None
    for prop in props:
        if prop.get("id") == CALENDARAPP_IDENTITY_PROP_ID:
            identity_value = prop.get("value")
            break
    if not identity_value or not isinstance(identity_value, str):
        return None
    try:
        identity = json.loads(identity_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(identity, dict):
        return None
    team_id = identity.get("t")
    if not team_id or (expected_team_id and team_id != expected_team_id):
        return None
    return {"json": identity_value, "identity": identity}


def parse_shift_time(
    base_date: date,
    time_text: str
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parses human-readable time strings into naive datetime objects.
    
    Rules:
    - "all day" -> 7:00 AM on date to 7:00 AM on date + 1 day
    - "XAM-YPM" -> Standard range
    - "XPM-YAM" -> Crosses midnight (end date + 1)
    - Returns (None, None) on failure
    """
    if not time_text:
        return None, None

    # Normalize dashes: en-dash (–) and em-dash (—) to hyphen-minus (-)
    normalized = time_text.lower().replace(" ", "").replace("–", "-").replace("—", "-").strip()
    
    # Rule 1: "all day" -> 7AM to 7AM next day (STRICT)
    if "allday" in normalized:
        start_dt = datetime.combine(base_date, time(7, 0))
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt

    # Rule 2: Parse "7am-5pm", "2pm-7am"
    # Expected format: [start]-[end]
    if "-" not in normalized:
        return None, None

    parts = normalized.split("-", 1)
    if len(parts) != 2:
        return None, None

    start_str, end_str = parts[0], parts[1]

    def _parse_single_time(t_str: str) -> Optional[time]:
        # Handle "7am", "5pm", "7:30am"
        # Since standard library strptime is strict, we do manual normalize
        try:
            # simple attempt
            return datetime.strptime(t_str, "%I%p").time()
        except ValueError:
            try:
                return datetime.strptime(t_str, "%I:%M%p").time()
            except ValueError:
                return None

    start_time = _parse_single_time(start_str)
    end_time = _parse_single_time(end_str)

    if not start_time or not end_time:
        return None, None

    start_dt = datetime.combine(base_date, start_time)
    end_dt = datetime.combine(base_date, end_time)

    # Midnight crossing rule:
    # If end time is earlier or strictly equal to start time (e.g. 7am-7am),
    # assume it ends the next day.
    # Typically 5PM -> 7AM, 7AM < 17:00.
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return start_dt, end_dt


def _normalize_prefix(prefix: Optional[str]) -> str:
    if not isinstance(prefix, str):
        return ""
    normalized = " ".join(prefix.split())
    if not normalized:
        return ""
    return f"{normalized} "


def _resolve_doctor_name(shift: dict) -> str:
    doctor = shift.get("doctor") if isinstance(shift, dict) else None
    if not isinstance(doctor, str) or not doctor.strip():
        return "Unassigned"
    return doctor.strip()


def _is_unassigned_doctor(shift: dict) -> bool:
    doctor = shift.get("doctor") if isinstance(shift, dict) else None
    if doctor is None:
        return True
    value = str(doctor).strip()
    if not value:
        return True
    return value.lower() in {"unassigned", "tbd", "unknown", "n/a", "na", "--"}


def _resolve_prefix(settings: dict, team_id: str, shift_type: str) -> str:
    if not isinstance(settings, dict):
        return ""
    if not team_id or not shift_type:
        return ""
    team_calendars = settings.get("outlook_team_calendars")
    if not isinstance(team_calendars, dict):
        return ""
    team_entry = team_calendars.get(team_id)
    if not isinstance(team_entry, dict):
        return ""
    event_names = team_entry.get("event_names")
    if not isinstance(event_names, dict):
        return ""
    prefix = event_names.get(shift_type, "")
    return _normalize_prefix(prefix)


def _truncate_subject(prefix: str, doctor_name: str) -> str:
    doctor_name = doctor_name.strip()
    if not doctor_name:
        doctor_name = "Unassigned"
    if len(doctor_name) > 255:
        return f"{doctor_name[:252]}..."

    if not prefix:
        return doctor_name

    allowed_prefix_len = 255 - len(doctor_name)
    if allowed_prefix_len <= 0:
        return doctor_name
    if len(prefix) <= allowed_prefix_len:
        return f"{prefix}{doctor_name}"

    if allowed_prefix_len <= 4:
        return doctor_name

    base_prefix = prefix.rstrip()
    trimmed_base = base_prefix[: allowed_prefix_len - 4]
    if not trimmed_base:
        return doctor_name
    return f"{trimmed_base}... {doctor_name}"


def _build_subject(
    *,
    settings: dict,
    team_id: str,
    shift_type: str,
    shift: dict,
) -> str:
    doctor_name = _resolve_doctor_name(shift)
    prefix = _resolve_prefix(settings, team_id, shift_type)
    return _truncate_subject(prefix, doctor_name)


def map_shift_to_event(
    *,
    date_obj: date,
    team: str,
    facility: str,
    shift: dict,
    identity_json: str,
    settings: dict,
    team_id: str,
) -> Optional[dict]:
    """
    Maps a single shift to a Microsoft Graph Event payload.
    Returns None if validation fails or doctor is missing.
    """
    doctor = _resolve_doctor_name(shift)

    time_text = shift.get("time_text", "")
    start_dt, end_dt = parse_shift_time(date_obj, time_text)
    
    if not start_dt or not end_dt:
        return None

    shift_type = shift.get("shift_type", "")
    if shift_type not in {"day", "night", "allday", "exception"}:
        shift_type = ""
    subject = _build_subject(
        settings=settings,
        team_id=team_id,
        shift_type=shift_type,
        shift=shift,
    )

    # Construct Body
    shift_type = shift.get("shift_type", "shift")
    body = f"{shift_type} shift – {time_text}"
    call_shift_types = {"day", "night", "weekend", "allday"}
    is_call_shift = shift_type in call_shift_types
    if is_call_shift:
        if "all day" in (time_text or "").lower():
            coverage_hours = "7:00 AM – 7:00 AM next day"
        else:
            coverage_hours = (time_text or "").replace("-", " – ")
        coverage_note = f"Actual coverage hours: {coverage_hours}"
        if coverage_note and coverage_note not in body:
            body = f"{body}\n{coverage_note}"

    category_mapping = {
        "day": "CalendarApp-Day",
        "night": "CalendarApp-Night",
        "weekend": "CalendarApp-Day",
        "allday": "CalendarApp-Day",
    }
    category_name = category_mapping.get(shift_type)

    # Use 'America/Chicago' as default TimeZone for Graph API compatibility.
    # Graph requires a valid Windows or IANA TimeZone ID. 'Local' is not robustly supported.
    event_payload = {
        "subject": subject,
        "body": {
            "contentType": "Text",
            "content": body
        },
        "location": {
            "displayName": facility
        },
        "showAs": "free",   # Default to free so it doesn't block user's personal calendar
        "singleValueExtendedProperties": [
            {
                "id": CALENDARAPP_IDENTITY_PROP_ID,
                "value": identity_json,
            }
        ],
    }
    if category_name and is_call_shift:
        event_payload["categories"] = [category_name]

    if is_call_shift:
        all_day_start = datetime.combine(date_obj, time(0, 0))
        all_day_end = all_day_start + timedelta(days=1)
        event_payload["start"] = {
            "dateTime": all_day_start.isoformat(),
            "timeZone": "America/Chicago"
        }
        event_payload["end"] = {
            "dateTime": all_day_end.isoformat(),
            "timeZone": "America/Chicago"
        }
        event_payload["isAllDay"] = True
    else:
        # We explicitly set start/end times even for "all day" shifts.
        # Setting isAllDay=False ensures Outlook respects our exact 7AM-7AM block.
        event_payload["start"] = {
            "dateTime": start_dt.isoformat(),
            "timeZone": "America/Chicago"
        }
        event_payload["end"] = {
            "dateTime": end_dt.isoformat(),
            "timeZone": "America/Chicago"
        }
        event_payload["isAllDay"] = False

    return event_payload


def iter_shifts_and_payloads(
    calendar_json: dict,
    settings: Optional[dict] = None,
) -> Generator[Tuple[dict, Optional[dict], Optional[str]], None, None]:
    """
    Generator that yields (shift_dict, payload) pairs.
    Allows the caller to modify shift_dict (e.g., adding IDs) while syncing.
    
    Reuses the traversal logic from build_event_payloads but yields objects instead of list.
    """
    # Robust extraction
    year = calendar_json.get("year")
    month = calendar_json.get("month")
    team = calendar_json.get("team", "Unknown Team")
    team_id = calendar_json.get("team_id")
    calendar_facility = calendar_json.get("facility", "")
    facility_id = calendar_json.get("facility_id")
    days = calendar_json.get("days", [])
    settings = settings if isinstance(settings, dict) else {}

    if not isinstance(team_id, str) or team_id not in {f"team-{idx}" for idx in range(1, 8)}:
        logging.warning("Missing or invalid team_id for Outlook sync; skipping subject construction.")
        team_id = None

    if not year or not month:
        return

    try:
        year_int = int(year)
        month_int = int(month)
    except (ValueError, TypeError):
        return

    def _build_payload(
        *,
        current_date: date,
        shift: dict,
        row_index: int,
    ) -> Tuple[Optional[dict], Optional[str]]:
        shift_type = shift.get("shift_type", "")
        if not shift_type or shift_type == "exception":
            return None, None
        if not team_id or not facility_id:
            return None, None
        identity_json = build_identity_json(
            team_id=team_id,
            facility_id=facility_id,
            date_obj=current_date,
            shift_type=shift_type,
            row_index=row_index,
        )
        shift_facility = shift.get("facility") or calendar_facility or "Unknown Facility"
        payload = map_shift_to_event(
            date_obj=current_date,
            team=team,
            facility=shift_facility,
            shift=shift,
            identity_json=identity_json,
            settings=settings,
            team_id=team_id,
        )
        return payload, identity_json

    if isinstance(days, dict):
        sorted_day_keys = sorted(days.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)
        for day_str in sorted_day_keys:
            if not str(day_str).isdigit():
                continue

            try:
                current_date = date(year_int, month_int, int(day_str))
            except (ValueError, TypeError):
                continue

            day_data = days.get(day_str, {})
            shifts = day_data.get("shifts", [])
            row_counters: Dict[str, int] = {}
            for shift in shifts:
                if not isinstance(shift, dict):
                    continue
                shift_type = shift.get("shift_type", "")
                row_index = row_counters.get(shift_type, 0)
                row_counters[shift_type] = row_index + 1
                payload, identity_json = _build_payload(
                    current_date=current_date,
                    shift=shift,
                    row_index=row_index,
                )
                yield shift, payload, identity_json
        return

    if isinstance(days, list):
        for day_data in days:
            if not day_data or not isinstance(day_data, dict):
                continue

            day_int = day_data.get("day")
            if not day_int:
                continue

            try:
                current_date = date(year_int, month_int, int(day_int))
            except (ValueError, TypeError):
                continue

            shifts = day_data.get("shifts", [])
            row_counters: Dict[str, int] = {}

            for shift in shifts:
                if not isinstance(shift, dict):
                    continue

                shift_type = shift.get("shift_type", "")
                row_index = row_counters.get(shift_type, 0)
                row_counters[shift_type] = row_index + 1
                payload, identity_json = _build_payload(
                    current_date=current_date,
                    shift=shift,
                    row_index=row_index,
                )

                yield shift, payload, identity_json

def build_event_payloads(calendar_json: dict, settings: Optional[dict] = None) -> List[dict]:
    """
    Wrapper around iterator for Stage 4 backward compatibility or testing.
    """
    payloads = []
    for _, payload, _ in iter_shifts_and_payloads(calendar_json, settings=settings):
        if payload:
            payloads.append(payload)
    return payloads
