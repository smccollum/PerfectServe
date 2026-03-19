"""
Quick utility to dump Outlook calendar events via Graph API.

Usage:
  python scripts/dump_outlook_events.py                        # List all calendars + groups
  python scripts/dump_outlook_events.py --calendar-id <ID>     # Dump events from a personal/shared calendar
  python scripts/dump_outlook_events.py --group-id <ID>        # Dump events from an M365 Group calendar
  python scripts/dump_outlook_events.py --calendar-id <ID> --year 2026 --month 4
  python scripts/dump_outlook_events.py --group-id <ID> --output docs/team1_outlook.json

Set AZURE_TENANT_ID and AZURE_CLIENT_ID env vars, or place calendarapp_system_config.json in project root.
"""

import sys
import json
import argparse
import os
from pathlib import Path
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outlook_client import OutlookCalendarReader


def _load_config():
    """Load Azure config from file if env vars not set."""
    if os.environ.get("AZURE_TENANT_ID"):
        return
    for config_path in [
        Path(__file__).resolve().parent.parent / "calendarapp_system_config.json",
        Path("D:/_CalendarApp/calendarapp_system_config.json"),
    ]:
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            os.environ["AZURE_TENANT_ID"] = config.get("azure_tenant_id", "")
            os.environ["AZURE_CLIENT_ID"] = config.get("azure_client_id", "")
            print(f"Loaded Azure config from {config_path}")
            return


def _print_events(events, output_path=None):
    """Print event summary or save to file."""
    print(f"Found {len(events)} events.\n")

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)
        print(f"Saved to {path}")
    else:
        for event in events[:30]:
            subject = event.get("subject", "???")
            start = event.get("start", {}).get("dateTime", "???")[:16]
            end = event.get("end", {}).get("dateTime", "???")[:16]
            is_all_day = event.get("isAllDay", False)
            tag = " [all day]" if is_all_day else ""
            print(f"  {start}  ->  {end}  |  {subject}{tag}")

        if len(events) > 30:
            print(f"\n  ... and {len(events) - 30} more. Use --output to save all.")


def main():
    parser = argparse.ArgumentParser(description="Dump Outlook calendar events via Graph API")
    parser.add_argument("--calendar-id", help="Personal/shared calendar ID")
    parser.add_argument("--group-id", help="M365 Group ID (for Group calendars like Teams 1 & 4)")
    parser.add_argument("--year", type=int, default=2026, help="Year (default: 2026)")
    parser.add_argument("--month", type=int, default=3, help="Month (default: 3)")
    parser.add_argument("--output", help="Save JSON to file instead of printing")
    args = parser.parse_args()

    _load_config()

    reader = OutlookCalendarReader(enabled=True)
    if not reader.available:
        print(f"Error: {reader.config_error}")
        sys.exit(1)

    # If no IDs given, list everything available
    if not args.calendar_id and not args.group_id:
        print("\n--- Personal/Shared Calendars ---\n")
        calendars = reader.list_calendars()
        if calendars:
            for cal in calendars:
                print(f"  Name:  {cal['name']}")
                print(f"  Owner: {cal['owner']}")
                print(f"  ID:    {cal['id']}")
                print()
        else:
            print("  (none found)\n")

        print("--- M365 Groups ---\n")
        groups = reader.list_groups()
        if groups:
            for grp in groups:
                desc = f"  ({grp['description']})" if grp.get('description') else ""
                print(f"  Name:  {grp['name']}{desc}")
                print(f"  ID:    {grp['id']}")
                print()
        else:
            print("  (none found)\n")

        print("Re-run with --calendar-id <ID> or --group-id <ID> to dump events.")
        return

    # Build date range
    year, month = args.year, args.month
    range_start = datetime(year, month, 1)
    range_end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    if args.group_id:
        print(f"\nFetching Group calendar events for {year}-{month:02d}...\n")
        events, error = reader.list_group_calendar_events(
            group_id=args.group_id,
            range_start=range_start,
            range_end=range_end,
        )
    else:
        print(f"\nFetching calendar events for {year}-{month:02d}...\n")
        events, error = reader.list_events_in_range(
            calendar_id=args.calendar_id,
            range_start=range_start,
            range_end=range_end,
        )

    if error:
        print(f"Error: {error}")
        sys.exit(1)

    _print_events(events, args.output)


if __name__ == "__main__":
    main()
