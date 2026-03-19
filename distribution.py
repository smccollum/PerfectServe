import os
import re
import json
import calendar
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

EXPORT_FOLDER_NAME = "On-Call Calendar Exports"
SNAPSHOT_FOLDER_NAME = "MonthSnapshots"
SETTINGS_DIR_NAME = "CalendarApp"
SETTINGS_FILENAME = "settings.json"
APP_SETTINGS_FILENAME = "app_settings.json"
SYSTEM_CONFIG_FILENAME = "calendarapp_system_config.json"
_SYSTEM_CONFIG_CACHE = None


def _bootstrap_settings_dir() -> Path:
    appdata = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if appdata:
        return Path(appdata) / SETTINGS_DIR_NAME
    return Path.home() / f".{SETTINGS_DIR_NAME.lower()}"


def _settings_path() -> Path:
    return _bootstrap_settings_dir() / SETTINGS_FILENAME


def _system_config_path() -> Path:
    return Path(__file__).resolve().parent / SYSTEM_CONFIG_FILENAME


def load_system_config() -> dict:
    global _SYSTEM_CONFIG_CACHE
    if _SYSTEM_CONFIG_CACHE is not None:
        return _SYSTEM_CONFIG_CACHE

    config_path = _system_config_path()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except json.JSONDecodeError:
        data = {}

    default_base, _ = _resolve_export_folder_with_fallback()
    system_config = {
        "onedrive_default_path": str(default_base),
        "central_default_path": str(default_base),
        "central_note": "Requires membership in the Executive Assistant Team (Microsoft Teams)",
        "azure_tenant_id": "",
        "azure_client_id": "",
    }
    if isinstance(data, dict):
        for key in ("onedrive_default_path", "central_default_path", "central_note", "azure_tenant_id", "azure_client_id"):
            if key in data and isinstance(data[key], str):
                system_config[key] = data[key]

    system_config["onedrive_default_path"] = os.path.expandvars(system_config["onedrive_default_path"])
    system_config["central_default_path"] = os.path.expandvars(system_config["central_default_path"])

    _SYSTEM_CONFIG_CACHE = system_config
    return system_config


def load_user_settings() -> dict:
    path = _settings_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        # ------------------------------------------------------------
        # Schema Extension: Outlook (Auth & Sync)
        # ------------------------------------------------------------
        if "outlook" not in data:
            data["outlook"] = {
                "tenant_id": None,
                "client_id": None
            }
        # Ensure sub-keys exist if "outlook" was present but partial
        elif isinstance(data["outlook"], dict):
            if "tenant_id" not in data["outlook"]:
                data["outlook"]["tenant_id"] = None
            if "client_id" not in data["outlook"]:
                data["outlook"]["client_id"] = None
        else:
            # Correction if malformed
            data["outlook"] = {
                "tenant_id": None,
                "client_id": None
            }
        system_config = load_system_config()
        if not data.get("azure_tenant_id"):
            data["azure_tenant_id"] = system_config.get("azure_tenant_id")
        if not data.get("azure_client_id"):
            data["azure_client_id"] = system_config.get("azure_client_id")
        _normalize_calendar_management(data)
        return data
    return {}


def _default_calendar_management() -> dict:
    return {
        "default_team_id": None,
        "active_team_id": None,
        "admin_mode": False,
        "team_calendar_bindings": {},
    }


def _normalize_calendar_management(settings: dict) -> dict:
    if not isinstance(settings, dict):
        return _default_calendar_management()

    calendar_management = settings.get("calendar_management")
    if not isinstance(calendar_management, dict):
        calendar_management = {}

    admin_mode = calendar_management.get("admin_mode")
    if not isinstance(admin_mode, bool):
        admin_mode = False

    default_team_id = calendar_management.get("default_team_id")
    if not isinstance(default_team_id, str) or not default_team_id:
        default_team_id = None

    active_team_id = calendar_management.get("active_team_id")
    if not isinstance(active_team_id, str) or not active_team_id:
        active_team_id = None

    bindings = calendar_management.get("team_calendar_bindings")
    if not isinstance(bindings, dict):
        bindings = {}

    normalized_bindings = {}
    for team_id, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        calendar_id = binding.get("calendar_id")
        if not isinstance(calendar_id, str) or not calendar_id:
            continue

        normalized_binding = dict(binding)
        calendar_name = normalized_binding.get("calendar_name")
        if not isinstance(calendar_name, str):
            normalized_binding["calendar_name"] = ""

        added_by = normalized_binding.get("added_by")
        if not isinstance(added_by, str) or not added_by:
            normalized_binding["added_by"] = "local"

        added_at = normalized_binding.get("added_at")
        if not isinstance(added_at, str):
            normalized_binding["added_at"] = ""

        active = normalized_binding.get("active")
        if active is None or not isinstance(active, bool):
            normalized_binding["active"] = True

        normalized_bindings[team_id] = normalized_binding

    calendar_management["default_team_id"] = default_team_id
    calendar_management["active_team_id"] = active_team_id
    calendar_management["admin_mode"] = admin_mode
    calendar_management["team_calendar_bindings"] = normalized_bindings
    settings["calendar_management"] = calendar_management
    return calendar_management


def get_calendar_management(settings: dict) -> dict:
    if not isinstance(settings, dict):
        settings = {}
    return _normalize_calendar_management(dict(settings))


def get_default_team_id(settings: dict) -> Optional[str]:
    return get_calendar_management(settings).get("default_team_id")


def set_default_team_id(settings: dict, team_id: Optional[str]) -> None:
    if not isinstance(settings, dict):
        return
    calendar_management = _normalize_calendar_management(settings)
    if not isinstance(team_id, str) or not team_id:
        calendar_management["default_team_id"] = None
        return
    calendar_management["default_team_id"] = team_id


def get_active_team_id(settings: dict) -> Optional[str]:
    return get_calendar_management(settings).get("active_team_id")


def set_active_team_id(settings: dict, team_id: Optional[str]) -> None:
    if not isinstance(settings, dict):
        return
    calendar_management = _normalize_calendar_management(settings)
    if not isinstance(team_id, str) or not team_id:
        calendar_management["active_team_id"] = None
        return
    calendar_management["active_team_id"] = team_id


def get_admin_mode(settings: dict) -> bool:
    return bool(get_calendar_management(settings).get("admin_mode"))


def set_admin_mode(settings: dict, enabled: bool) -> None:
    if not isinstance(settings, dict):
        return
    calendar_management = _normalize_calendar_management(settings)
    calendar_management["admin_mode"] = bool(enabled)



def get_team_calendar_binding(settings: dict, team_id: str) -> Optional[dict]:
    if not isinstance(team_id, str) or not team_id:
        return None
    calendar_management = get_calendar_management(settings)
    binding = calendar_management.get("team_calendar_bindings", {}).get(team_id)
    if not isinstance(binding, dict):
        legacy_bindings = settings.get("outlook_team_calendars") if isinstance(settings, dict) else None
        if not isinstance(legacy_bindings, dict):
            return None
        binding = legacy_bindings.get(team_id)
        if not isinstance(binding, dict):
            return None
    calendar_id = binding.get("calendar_id")
    if not isinstance(calendar_id, str) or not calendar_id:
        return None
    return dict(binding)


def set_team_calendar_binding(settings: dict, team_id: str, binding: dict) -> None:
    if not isinstance(settings, dict):
        return
    if not isinstance(team_id, str) or not team_id:
        return
    if not isinstance(binding, dict):
        return
    calendar_id = binding.get("calendar_id")
    if not isinstance(calendar_id, str) or not calendar_id:
        return

    calendar_management = _normalize_calendar_management(settings)
    normalized_binding = dict(binding)

    calendar_name = normalized_binding.get("calendar_name")
    if not isinstance(calendar_name, str):
        normalized_binding["calendar_name"] = ""

    added_by = normalized_binding.get("added_by")
    if not isinstance(added_by, str) or not added_by:
        normalized_binding["added_by"] = "local"

    added_at = normalized_binding.get("added_at")
    if not isinstance(added_at, str) or not added_at:
        normalized_binding["added_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    active = normalized_binding.get("active")
    if active is None or not isinstance(active, bool):
        normalized_binding["active"] = True

    calendar_management["team_calendar_bindings"][team_id] = normalized_binding


def clear_team_calendar_binding(settings: dict, team_id: str) -> None:
    if not isinstance(settings, dict):
        return
    if not isinstance(team_id, str) or not team_id:
        return
    calendar_management = _normalize_calendar_management(settings)
    calendar_management["team_calendar_bindings"].pop(team_id, None)


def load_user_settings_with_error() -> tuple[dict, str | None]:
    path = _settings_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data, None
        return {}, f"{path.name} must contain a JSON object."
    except FileNotFoundError:
        return {}, None
    except json.JSONDecodeError:
        return {}, f"{path.name} contains invalid JSON and was not overwritten."


def save_user_settings(settings: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def resolve_export_folder() -> Path:
    folder, _ = _resolve_export_folder_with_fallback()
    return folder


def _resolve_export_folder_with_fallback() -> tuple[Path, bool]:
    onedrive_root = (
        os.environ.get("OneDrive")
        or os.environ.get("OneDriveCommercial")
        or os.environ.get("OneDriveConsumer")
    )
    if onedrive_root:
        onedrive_docs = Path(onedrive_root) / "Documents"
        if onedrive_docs.exists():
            return onedrive_docs / EXPORT_FOLDER_NAME, False

    user_profile = os.environ.get("USERPROFILE")
    documents = Path(user_profile) / "Documents" if user_profile else Path.home() / "Documents"
    if documents.exists():
        return documents / EXPORT_FOLDER_NAME, False

    downloads = Path(user_profile) / "Downloads" if user_profile else Path.home() / "Downloads"
    return downloads / EXPORT_FOLDER_NAME, True


def _resolve_base_folder_from_settings(settings: dict, system_config: dict) -> tuple[Path, bool]:
    mode = (settings.get("base_path_mode") or "onedrive").lower()

    def _ensure_folder(path_value: str) -> Path | None:
        raw_path = os.path.expandvars(path_value or "").strip()
        if not raw_path:
            return None
        base_folder = Path(raw_path)
        try:
            base_folder.mkdir(parents=True, exist_ok=True)
            return base_folder
        except OSError:
            return None

    if mode == "onedrive":
        base_folder = _ensure_folder(system_config.get("onedrive_default_path") or "")
        if base_folder is not None:
            return base_folder, False
        return _resolve_export_folder_with_fallback()

    if mode == "central":
        base_folder = _ensure_folder(settings.get("central_path") or "")
        if base_folder is not None:
            return base_folder, False
        base_folder = _ensure_folder(system_config.get("central_default_path") or "")
        if base_folder is not None:
            return base_folder, False
        return _resolve_export_folder_with_fallback()

    if mode == "custom":
        base_folder = _ensure_folder(settings.get("custom_path") or "")
        if base_folder is not None:
            return base_folder, False
        return _resolve_export_folder_with_fallback()

    return _resolve_export_folder_with_fallback()


def resolve_base_folder_for_mode(
    mode: str,
    central_path: str,
    custom_path: str,
    system_config: dict | None = None,
) -> tuple[Path, bool]:
    if system_config is None:
        system_config = load_system_config()

    settings = {
        "base_path_mode": mode,
        "central_path": central_path,
        "custom_path": custom_path,
    }
    return _resolve_base_folder_from_settings(settings, system_config)


def resolve_calendar_artifact_path(
    team: str,
    year: int,
    month: int,
    artifact_type: str,
    facility: str | None = None,
) -> tuple[Path, bool]:
    settings = load_user_settings()
    system_config = load_system_config()
    base_folder, used_fallback = _resolve_base_folder_from_settings(settings, system_config)
    return _build_calendar_artifact_path(
        base_folder,
        used_fallback,
        team,
        year,
        month,
        artifact_type,
        facility,
    )


def resolve_calendar_artifact_path_for_settings(
    team: str,
    year: int,
    month: int,
    artifact_type: str,
    facility: str | None = None,
    base_path_mode: str = "onedrive",
    central_path: str = "",
    custom_path: str = "",
    system_config: dict | None = None,
) -> tuple[Path, bool]:
    base_folder, used_fallback = resolve_base_folder_for_mode(
        base_path_mode,
        central_path,
        custom_path,
        system_config,
    )
    return _build_calendar_artifact_path(
        base_folder,
        used_fallback,
        team,
        year,
        month,
        artifact_type,
        facility,
    )


def resolve_calendar_snapshot_path(
    team: str,
    year: int,
    month: int,
    facility: str | None = None,
) -> tuple[Path, bool]:
    settings = load_user_settings()
    system_config = load_system_config()
    base_folder, used_fallback = _resolve_base_folder_from_settings(settings, system_config)
    return _build_calendar_snapshot_path(
        base_folder,
        used_fallback,
        team,
        year,
        month,
        facility,
    )


def resolve_calendar_snapshot_path_for_settings(
    team: str,
    year: int,
    month: int,
    facility: str | None = None,
    base_path_mode: str = "onedrive",
    central_path: str = "",
    custom_path: str = "",
    system_config: dict | None = None,
) -> tuple[Path, bool]:
    base_folder, used_fallback = resolve_base_folder_for_mode(
        base_path_mode,
        central_path,
        custom_path,
        system_config,
    )
    return _build_calendar_snapshot_path(
        base_folder,
        used_fallback,
        team,
        year,
        month,
        facility,
    )


def _build_calendar_artifact_path(
    base_folder: Path,
    used_fallback: bool,
    team: str,
    year: int,
    month: int,
    artifact_type: str,
    facility: str | None,
) -> tuple[Path, bool]:
    safe_team = _sanitize_filename_part(team or "Team")
    month_number = int(month)
    month_name = calendar.month_name[month_number] if 1 <= month_number <= 12 else str(month)
    month_label = f"{month_number:02d} - {month_name}"
    safe_month = _sanitize_filename_part(month_label)

    target_folder = base_folder / safe_team / str(year) / safe_month
    target_folder.mkdir(parents=True, exist_ok=True)

    if artifact_type == "pdf":
        filename = build_calendar_filename(year, month_number, team, facility, ".pdf")
    elif artifact_type == "json":
        filename = build_calendar_filename(year, month_number, team, facility, ".json")
    else:
        raise ValueError(f"Unsupported artifact type: {artifact_type}")

    return target_folder / filename, used_fallback


def _build_calendar_snapshot_path(
    base_folder: Path,
    used_fallback: bool,
    team: str,
    year: int,
    month: int,
    facility: str | None,
) -> tuple[Path, bool]:
    safe_team = _sanitize_filename_part(team or "Team")
    month_number = int(month)
    month_name = calendar.month_name[month_number] if 1 <= month_number <= 12 else str(month)
    month_label = f"{month_number:02d} - {month_name}"
    safe_month = _sanitize_filename_part(month_label)

    target_folder = base_folder / safe_team / str(year) / safe_month / SNAPSHOT_FOLDER_NAME
    target_folder.mkdir(parents=True, exist_ok=True)
    filename = build_calendar_filename(year, month_number, team, facility, ".json")
    return target_folder / filename, used_fallback


def build_calendar_filename(
    year: int,
    month: int,
    team: str | None,
    facility: str | None,
    extension: str,
) -> str:
    safe_team = _sanitize_filename_part(team or "Team")
    facility_label = facility.strip() if facility else ""
    safe_facility = _sanitize_filename_part(facility_label or "Unknown Facility")
    month_label = f"{int(year):04d}-{int(month):02d}"
    extension = extension if extension.startswith(".") else f".{extension}"
    return f"{month_label} – {safe_team} – {safe_facility}{extension}"


def build_outlook_web_compose_url(subject: str, body: str) -> str:
    query = f"subject={quote(subject)}&body={quote(body)}"
    return f"https://outlook.office.com/mail/deeplink/compose?{query}"


def _sanitize_filename_part(value: str) -> str:
    sanitized = re.sub(r"[<>:\"/\\|?*]+", "-", value).strip()
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .-")
    return sanitized or "Calendar"
