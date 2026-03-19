"""
models.py

Schema and validation helpers for CalendarApp domain data.

Responsibilities (V2):
- Define Doctor, Team, and Facility schemas
- Validate universe + relationship JSON payloads
- Provide normalized accessors for the editor UI

Non-goals:
- No scheduling logic
- No Qt dependencies

NOTE:
universe.json and team_relationships.json are authoritative domain sources.
UI layers must never mutate in-memory domain data directly.
All edits must be persisted and followed by reload_domain_data().
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Tuple


# -------------------------
# Core data structures
# -------------------------

@dataclass(frozen=True)
class Doctor:
    id: str
    last_name: str
    full_name: Optional[str]
    suffix: Optional[str]
    active: bool
    start_month: Optional[str] = None
    last_month: Optional[str] = None


@dataclass(frozen=True)
class TeamDefinition:
    id: str
    display_name: str
    active: bool


@dataclass(frozen=True)
class Facility:
    id: str
    full_name: str
    short_name: str
    aliases: List[str]
    active: bool


@dataclass(frozen=True)
class Team:
    """
    Represents a medical team for calendar generation.

    Attributes:
        name: Display name (e.g. "Team 6")
        doctors: Alphabetized list of default doctor names
                 NOTE: Editor should always add ONE extra
                 editable 'Exception' box on top of this list.
    """
    name: str
    doctors: List[str]


@dataclass(frozen=True)
class RelationshipFacility:
    id: str
    display_name: Optional[str] = None


@dataclass(frozen=True)
class ExtraAssignment:
    facility_id: str
    doctor_ids: List[str]


@dataclass(frozen=True)
class TeamRelationshipsEntry:
    team_id: str
    doctor_ids: List[str]
    facilities: List[RelationshipFacility]
    extra_assignments: List[ExtraAssignment]


@dataclass(frozen=True)
class UniverseData:
    doctors: List[Doctor]
    teams: List[TeamDefinition]
    facilities: List[Facility]
    doctor_by_id: Dict[str, Doctor]
    team_by_id: Dict[str, TeamDefinition]
    team_by_display_name: Dict[str, TeamDefinition]
    facility_by_id: Dict[str, Facility]
    facility_name_map: Dict[str, str]


@dataclass(frozen=True)
class TeamRelationshipsData:
    teams: List[TeamRelationshipsEntry]
    team_by_id: Dict[str, TeamRelationshipsEntry]


# ------------------------------------------------------------
# Core Shift Schema
# ------------------------------------------------------------

@dataclass(frozen=True)
class Shift:
    """
    Represents a single scheduled shift.
    
    This strict schema is defined for the sync engine contract.
    It includes optional metadata for external sync tracking.
    """
    doctor_id: str
    date: str
    shift_type: str
    outlook_event_id: Optional[str] = None


# ------------------------------------------------------------
# Shift rules (team-specific)
# ------------------------------------------------------------
# ------------------------------------------------------------
# Per-team shift rule overrides (V1)
#
# IMPORTANT:
# - Only teams listed here have custom or explicitly defined rules.
# - Any team NOT present in this mapping will automatically fall back
#   to default_shift_rules().
#
# Current behavior:
# - Team 1 → Explicit day/night splits on weekdays + Friday; all-day on weekend
# - Team 2 → Default rules with Friday weekend starting at 2PM
# - Team 3 → Default rules with Friday weekend starting at 2PM
# - Team 5 → Default rules except Friday day/night split at 3PM
# - Teams 4, 6, 7 → default_shift_rules() with standard 5PM Friday start
#
# This fallback behavior is INTENTIONAL for V1.
# Additional teams may be explicitly added here in future versions.
# ------------------------------------------------------------


def default_shift_rules(weekend_start_label: str = "5PM-7AM") -> dict:
    """
    Returns default shift rules for a team.
    weekend_start_label controls Friday weekend coverage start.
    """
    return {
        "weekday": [
            ("day", "7AM-5PM"),
            ("night", "5PM-7AM"),
            ("exception", "(exception)"),
        ],
        "friday": [
            ("day", "7AM-5PM"),
            ("weekend", weekend_start_label),
            ("exception", "(exception)"),
        ],
        "weekend": [
            ("weekend", "all day"),
            ("exception", "(exception)"),
        ],
    }

# ------------------------------------------------------------
# Per-team shift rule overrides
# ------------------------------------------------------------

_SHIFT_RULES: Dict[str, dict] = {
    "Team 1": {
        "weekday": [
            ("day", "7AM-5PM"),
            ("night", "5PM-7AM"),
            ("exception", "(exception)"),
        ],
        "friday": [
            ("day", "7AM-5PM"),
            ("night", "5PM-7AM"),
            ("exception", "(exception)"),
        ],
        "weekend": [
            ("allday", "all day"),
            ("exception", "(exception)"),
        ],
    },

    "Team 2": {
        "weekday": [
            ("day", "7AM-5PM"),
            ("night", "5PM-7AM"),
            ("exception", "(exception)"),
        ],
        "friday": [
            ("day", "7AM-2PM"),
            ("night", "2PM-7AM"),
            ("exception", "(exception)"),
        ],
        "weekend": [
            ("weekend", "all day"),
            ("exception", "(exception)"),
        ],
    },
    "Team 3": {
        "weekday": [
            ("day", "7AM-5PM"),
            ("night", "5PM-7AM"),
            ("exception", "(exception)"),
        ],
        "friday": [
            ("day", "7AM-2PM"),
            ("night", "2PM-7AM"),
            ("exception", "(exception)"),
        ],
        "weekend": [
            ("weekend", "all day"),
            ("exception", "(exception)"),
        ],
    },
    "Team 5": {
        "weekday": [
            ("day", "7AM-5PM"),
            ("night", "5PM-7AM"),
            ("exception", "(exception)"),
        ],
        "friday": [
            ("day", "7AM-3PM"),
            ("night", "3PM-7AM"),
            ("exception", "(exception)"),
        ],
        "weekend": [
            ("weekend", "all day"),
            ("exception", "(exception)"),
        ],
    },
    # Other teams can be added later
}

def get_team_shift_rules(team_name: str) -> dict:
    """
    Safe accessor for team shift rules.

    Behavior:
    - If a team has an explicit entry in _SHIFT_RULES, those rules are used.
    - Otherwise, the team intentionally falls back to default_shift_rules().

    NOTE:
    - This fallback is expected for Teams 4, 6, and 7 in V1.
    - Callers should NOT assume missing teams indicate an error.
    """
    return _SHIFT_RULES.get(team_name, default_shift_rules())


    



# -------------------------
# Public helper functions
# -------------------------

_UNIVERSE_PATH = Path(__file__).with_name("universe.json")
_TEAM_RELATIONSHIPS_PATH = Path(__file__).with_name("team_relationships.json")
_SAFE_MODE_DOCTOR_LABEL = "Custom"
_SAFE_MODE_TEAM_NAME = "Custom"
_SAFE_MODE_FACILITY_NAME = "Custom"
_MONTH_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")


def _read_json_file(path: Path) -> Tuple[Optional[dict], Optional[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, f"{path.name} not found."
    except json.JSONDecodeError:
        return None, f"{path.name} is invalid JSON."
    except OSError as exc:
        return None, f"Unable to read {path.name}: {exc}"


def _validate_required_str(value: object, label: str, errors: List[str]) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value
    errors.append(f"{label} must be a non-empty string.")
    return None


def _validate_required_bool(value: object, label: str, errors: List[str]) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    errors.append(f"{label} must be a boolean.")
    return None


def _validate_string_list(value: object, label: str, errors: List[str]) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{label} must be a list of strings.")
        return []
    result: List[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        else:
            errors.append(f"{label} entries must be strings.")
            return []
    return result


def _parse_month_string(value: Optional[str]) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    match = _MONTH_PATTERN.match(value.strip())
    if not match:
        return None
    return int(match.group("year")), int(match.group("month"))


def _normalize_month_string(
    value: object,
    label: str,
    warnings: List[str],
) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        warnings.append(f"{label} must be a string in YYYY-MM format; treating as null.")
        return None
    parsed = _parse_month_string(value)
    if not parsed:
        warnings.append(f"{label} must be in YYYY-MM format; treating as null.")
        return None
    year, month = parsed
    return f"{year:04d}-{month:02d}"


def _build_name_map(facilities: Iterable[Facility]) -> Dict[str, str]:
    name_map: Dict[str, str] = {}
    for facility in facilities:
        for name in [facility.full_name, facility.short_name, *facility.aliases]:
            if name:
                name_map.setdefault(name, facility.id)
    return name_map


def _validate_universe(payload: dict) -> Tuple[Optional[UniverseData], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    doctors_payload = payload.get("doctors")
    teams_payload = payload.get("teams")
    facilities_payload = payload.get("facilities")

    if not isinstance(doctors_payload, list):
        errors.append("doctors must be a list.")
    if not isinstance(teams_payload, list):
        errors.append("teams must be a list.")
    if not isinstance(facilities_payload, list):
        errors.append("facilities must be a list.")

    doctors: List[Doctor] = []
    teams: List[TeamDefinition] = []
    facilities: List[Facility] = []
    doctor_ids: set[str] = set()
    team_ids: set[str] = set()
    team_names: set[str] = set()
    facility_ids: set[str] = set()

    if isinstance(doctors_payload, list):
        for idx, doctor in enumerate(doctors_payload):
            if not isinstance(doctor, dict):
                errors.append(f"doctors[{idx}] must be an object.")
                continue
            doctor_id = _validate_required_str(doctor.get("id"), f"doctors[{idx}].id", errors)
            last_name = _validate_required_str(
                doctor.get("last_name"), f"doctors[{idx}].last_name", errors
            )
            full_name = doctor.get("full_name")
            if full_name is not None and not isinstance(full_name, str):
                errors.append(f"doctors[{idx}].full_name must be a string if provided.")
                full_name = None
            suffix = doctor.get("suffix")
            if suffix is not None and not isinstance(suffix, str):
                errors.append(f"doctors[{idx}].suffix must be a string if provided.")
                suffix = None
            start_month = _normalize_month_string(
                doctor.get("start_month"),
                f"doctors[{idx}].start_month",
                warnings,
            )
            last_month = _normalize_month_string(
                doctor.get("last_month"),
                f"doctors[{idx}].last_month",
                warnings,
            )
            active = _validate_required_bool(doctor.get("active"), f"doctors[{idx}].active", errors)
            if not doctor_id or not last_name or active is None:
                continue
            if doctor_id in doctor_ids:
                errors.append(f"Duplicate doctor id: {doctor_id}.")
                continue
            doctor_ids.add(doctor_id)
            doctors.append(
                Doctor(
                    id=doctor_id,
                    last_name=last_name,
                    full_name=full_name,
                    suffix=suffix,
                    active=active,
                    start_month=start_month,
                    last_month=last_month,
                )
            )

    if isinstance(teams_payload, list):
        for idx, team in enumerate(teams_payload):
            if not isinstance(team, dict):
                errors.append(f"teams[{idx}] must be an object.")
                continue
            team_id = _validate_required_str(team.get("id"), f"teams[{idx}].id", errors)
            display_name = _validate_required_str(
                team.get("display_name"), f"teams[{idx}].display_name", errors
            )
            active = _validate_required_bool(team.get("active"), f"teams[{idx}].active", errors)
            if not team_id or not display_name or active is None:
                continue
            if team_id in team_ids:
                errors.append(f"Duplicate team id: {team_id}.")
                continue
            if display_name in team_names:
                errors.append(f"Duplicate team display_name: {display_name}.")
                continue
            team_ids.add(team_id)
            team_names.add(display_name)
            teams.append(TeamDefinition(id=team_id, display_name=display_name, active=active))

    if isinstance(facilities_payload, list):
        for idx, facility in enumerate(facilities_payload):
            if not isinstance(facility, dict):
                errors.append(f"facilities[{idx}] must be an object.")
                continue
            facility_id = _validate_required_str(
                facility.get("id"), f"facilities[{idx}].id", errors
            )
            full_name = _validate_required_str(
                facility.get("full_name"), f"facilities[{idx}].full_name", errors
            )
            short_name = _validate_required_str(
                facility.get("short_name"), f"facilities[{idx}].short_name", errors
            )
            aliases = _validate_string_list(
                facility.get("aliases"), f"facilities[{idx}].aliases", errors
            )
            active = _validate_required_bool(
                facility.get("active"), f"facilities[{idx}].active", errors
            )
            if not facility_id or not full_name or not short_name or active is None:
                continue
            if facility_id in facility_ids:
                errors.append(f"Duplicate facility id: {facility_id}.")
                continue
            facility_ids.add(facility_id)
            facilities.append(
                Facility(
                    id=facility_id,
                    full_name=full_name,
                    short_name=short_name,
                    aliases=aliases,
                    active=active,
                )
            )

    if warnings:
        for warning in warnings:
            print(f"Warning: {warning}")

    if errors:
        return None, errors

    if not doctors or not teams or not facilities:
        return None, ["Universe lists must be non-empty."]

    doctor_by_id = {doctor.id: doctor for doctor in doctors}
    team_by_id = {team.id: team for team in teams}
    team_by_display_name = {team.display_name: team for team in teams}
    facility_by_id = {facility.id: facility for facility in facilities}
    facility_name_map = _build_name_map(facilities)

    return (
        UniverseData(
            doctors=doctors,
            teams=teams,
            facilities=facilities,
            doctor_by_id=doctor_by_id,
            team_by_id=team_by_id,
            team_by_display_name=team_by_display_name,
            facility_by_id=facility_by_id,
            facility_name_map=facility_name_map,
        ),
        [],
    )


def _validate_team_relationships(
    payload: dict,
    universe: UniverseData,
) -> Tuple[Optional[TeamRelationshipsData], List[str]]:
    errors: List[str] = []
    teams_payload = payload.get("teams")
    if not isinstance(teams_payload, list):
        return None, ["teams must be a list."]

    relationships: List[TeamRelationshipsEntry] = []
    team_by_id: Dict[str, TeamRelationshipsEntry] = {}

    for idx, team in enumerate(teams_payload):
        if not isinstance(team, dict):
            errors.append(f"teams[{idx}] must be an object.")
            continue
        team_id = _validate_required_str(team.get("id"), f"teams[{idx}].id", errors)
        doctor_ids = _validate_string_list(
            team.get("doctor_ids"), f"teams[{idx}].doctor_ids", errors
        )
        facilities_payload = team.get("facilities") or []
        extra_payload = team.get("extra_assignment_doctors") or []

        if not team_id:
            continue
        if not doctor_ids:
            errors.append(f"teams[{idx}].doctor_ids must be a non-empty list.")
            continue
        if team_id not in universe.team_by_id:
            errors.append(f"teams[{idx}].id does not exist in universe: {team_id}.")
            continue
        if team_id in team_by_id:
            errors.append(f"Duplicate team relationship entry: {team_id}.")
            continue
        if len(set(doctor_ids)) != len(doctor_ids):
            errors.append(f"teams[{idx}].doctor_ids must be unique.")
            continue

        invalid_doctors = [doc_id for doc_id in doctor_ids if doc_id not in universe.doctor_by_id]
        if invalid_doctors:
            errors.append(
                f"teams[{idx}].doctor_ids contains unknown doctors: {', '.join(invalid_doctors)}."
            )
            continue

        facilities: List[RelationshipFacility] = []
        if not isinstance(facilities_payload, list):
            errors.append(f"teams[{idx}].facilities must be a list.")
            continue
        for fac_idx, facility in enumerate(facilities_payload):
            if not isinstance(facility, dict):
                errors.append(f"teams[{idx}].facilities[{fac_idx}] must be an object.")
                continue
            facility_id = _validate_required_str(
                facility.get("id"),
                f"teams[{idx}].facilities[{fac_idx}].id",
                errors,
            )
            display_name = facility.get("display_name")
            if display_name is not None and not isinstance(display_name, str):
                errors.append(
                    f"teams[{idx}].facilities[{fac_idx}].display_name must be a string."
                )
                display_name = None
            if not facility_id:
                continue
            if facility_id not in universe.facility_by_id:
                errors.append(
                    f"teams[{idx}].facilities[{fac_idx}].id does not exist: {facility_id}."
                )
                continue
            facilities.append(RelationshipFacility(id=facility_id, display_name=display_name))
        facility_ids = [facility.id for facility in facilities]
        if len(set(facility_ids)) != len(facility_ids):
            errors.append(f"teams[{idx}].facilities ids must be unique.")
            continue

        extra_assignments: List[ExtraAssignment] = []
        if not isinstance(extra_payload, list):
            errors.append(f"teams[{idx}].extra_assignment_doctors must be a list.")
            continue
        for extra_idx, extra in enumerate(extra_payload):
            if not isinstance(extra, dict):
                errors.append(
                    f"teams[{idx}].extra_assignment_doctors[{extra_idx}] must be an object."
                )
                continue
            facility_id = _validate_required_str(
                extra.get("facility_id"),
                f"teams[{idx}].extra_assignment_doctors[{extra_idx}].facility_id",
                errors,
            )
            assignment_doctors = _validate_string_list(
                extra.get("doctor_ids"),
                f"teams[{idx}].extra_assignment_doctors[{extra_idx}].doctor_ids",
                errors,
            )
            if not facility_id or not assignment_doctors:
                continue
            if facility_id not in universe.facility_by_id:
                errors.append(
                    f"teams[{idx}].extra_assignment_doctors[{extra_idx}].facility_id "
                    f"does not exist: {facility_id}."
                )
                continue
            if len(set(assignment_doctors)) != len(assignment_doctors):
                errors.append(
                    f"teams[{idx}].extra_assignment_doctors[{extra_idx}].doctor_ids must be unique."
                )
                continue
            invalid_extra_doctors = [
                doc_id for doc_id in assignment_doctors if doc_id not in universe.doctor_by_id
            ]
            if invalid_extra_doctors:
                errors.append(
                    f"teams[{idx}].extra_assignment_doctors[{extra_idx}].doctor_ids "
                    f"contains unknown doctors: {', '.join(invalid_extra_doctors)}."
                )
                continue
            extra_assignments.append(
                ExtraAssignment(facility_id=facility_id, doctor_ids=assignment_doctors)
            )

        entry = TeamRelationshipsEntry(
            team_id=team_id,
            doctor_ids=doctor_ids,
            facilities=facilities,
            extra_assignments=extra_assignments,
        )
        relationships.append(entry)
        team_by_id[team_id] = entry

    if errors:
        return None, errors

    return TeamRelationshipsData(teams=relationships, team_by_id=team_by_id), []


@lru_cache(maxsize=1)
def _load_domain_data() -> Tuple[Optional[UniverseData], Optional[TeamRelationshipsData], bool]:
    universe_payload, _ = _read_json_file(_UNIVERSE_PATH)
    if not isinstance(universe_payload, dict):
        return None, None, True
    universe, universe_errors = _validate_universe(universe_payload)
    if universe_errors or universe is None:
        return None, None, True

    relationships_payload, _ = _read_json_file(_TEAM_RELATIONSHIPS_PATH)
    if not isinstance(relationships_payload, dict):
        return universe, None, True
    relationships, relationship_errors = _validate_team_relationships(
        relationships_payload, universe
    )
    if relationship_errors or relationships is None:
        return universe, None, True
    return universe, relationships, False


def is_safe_mode() -> bool:
    return _load_domain_data()[2]


def reload_domain_data() -> None:
    """
    Clears cached universe + relationship data.
    Must be called after modifying universe.json or team_relationships.json.
    """
    _load_domain_data.cache_clear()


def domain_is_valid() -> bool:
    universe, _, safe_mode = _load_domain_data()
    return bool(universe) and not safe_mode


def get_universe_data() -> Optional[UniverseData]:
    return _load_domain_data()[0]


def get_relationships_data() -> Optional[TeamRelationshipsData]:
    return _load_domain_data()[1]


def get_team_id(team_name: str) -> Optional[str]:
    universe = get_universe_data()
    if not universe:
        return None
    team = universe.team_by_display_name.get(team_name)
    return team.id if team else None


def get_facility_id(name: str) -> Optional[str]:
    universe = get_universe_data()
    if not universe:
        return None
    return universe.facility_name_map.get((name or "").strip())


def get_facility_display_name(facility_id: str) -> Optional[str]:
    universe = get_universe_data()
    if not universe:
        return None
    facility = universe.facility_by_id.get(facility_id)
    if not facility:
        return None
    return facility.short_name or facility.full_name


def _doctor_display_label(doctor: Doctor) -> str:
    suffix = (doctor.suffix or "").strip()
    if suffix:
        return f"{doctor.last_name} ({suffix})"
    return doctor.last_name


def get_doctor_last_name(doctor_id: str) -> Optional[str]:
    universe = get_universe_data()
    if not universe:
        return None
    doctor = universe.doctor_by_id.get(doctor_id)
    return doctor.last_name if doctor else None


def get_doctor_display_name(doctor_id: str) -> Optional[str]:
    universe = get_universe_data()
    if not universe:
        return None
    doctor = universe.doctor_by_id.get(doctor_id)
    return _doctor_display_label(doctor) if doctor else None


def is_doctor_visible_for_month(doctor_id: str, year: int, month: int) -> bool:
    universe = get_universe_data()
    if not universe:
        return False
    doctor = universe.doctor_by_id.get(doctor_id)
    if not doctor or not doctor.active:
        return False
    target = (int(year), int(month))
    start_value = _parse_month_string(doctor.start_month)
    end_value = _parse_month_string(doctor.last_month)
    if start_value and end_value and start_value > end_value:
        print(
            "Warning: doctor visibility window is invalid "
            f"for {doctor_id} (start_month > last_month); treating as invisible."
        )
        return False
    if start_value and target < start_value:
        return False
    if end_value and target > end_value:
        return False
    return True


def _safe_mode_team() -> Team:
    return Team(name=_SAFE_MODE_TEAM_NAME, doctors=[_SAFE_MODE_DOCTOR_LABEL] * 5)


def get_all_teams() -> List[Team]:
    """
    Returns all teams in universe order.
    Useful for building dropdowns or selectors.
    """
    if is_safe_mode():
        return [_safe_mode_team()]
    universe = get_universe_data()
    if not universe:
        return [_safe_mode_team()]
    return [get_team(team.display_name) for team in universe.teams if team.active]


def get_team(team_name: str, year: Optional[int] = None, month: Optional[int] = None) -> Team:
    """
    Returns a Team by name.
    """
    # NOTE:
    # Active flags affect UI selection only.
    # Inactive doctors must still load from saved calendars.
    if is_safe_mode():
        return _safe_mode_team()
    universe = get_universe_data()
    relationships = get_relationships_data()
    if not universe or not relationships:
        return _safe_mode_team()
    team_def = universe.team_by_display_name.get(team_name)
    if not team_def:
        return _safe_mode_team()
    rel_entry = relationships.team_by_id.get(team_def.id)
    if not rel_entry:
        return _safe_mode_team()
    doctors: List[str] = []
    for doctor_id in rel_entry.doctor_ids:
        if doctor_id not in universe.doctor_by_id:
            continue
        if year is not None and month is not None:
            if not is_doctor_visible_for_month(doctor_id, year, month):
                continue
        doctors.append(_doctor_display_label(universe.doctor_by_id[doctor_id]))
    if not doctors:
        return _safe_mode_team()
    return Team(name=team_def.display_name, doctors=doctors)


def get_team_names() -> List[str]:
    """
    Convenience helper for UI dropdowns.
    """
    if is_safe_mode():
        return [_SAFE_MODE_TEAM_NAME]
    universe = get_universe_data()
    if not universe:
        return [_SAFE_MODE_TEAM_NAME]
    return [team.display_name for team in universe.teams if team.active]


def get_doctor_choices(team: Team) -> List[str]:
    """
    Returns the list of doctor names for dropdown population.

    IMPORTANT:
    - This returns ONLY default doctors.
    - Editor is responsible for adding an extra editable
      'Exception' box on its own.
    """
    return list(team.doctors)
    

def get_facilities() -> list[str]:
    """
    Returns the list of known facilities.

    NOTE:
    - This intentionally excludes 'Custom...'
    - UI layers (editor) are responsible for adding Custom handling
    """
    if is_safe_mode():
        return [_SAFE_MODE_FACILITY_NAME]
    universe = get_universe_data()
    if not universe:
        return [_SAFE_MODE_FACILITY_NAME]
    return [
        (facility.short_name or facility.full_name)
        for facility in universe.facilities
        if facility.active
    ]
