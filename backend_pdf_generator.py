import json
import argparse
import calendar
import sys
from pathlib import Path
from datetime import datetime, timedelta

from PySide6.QtGui import QGuiApplication

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import models
import render
import distribution

LOGO_PATH = Path(__file__).resolve().parent / "resources" / "logo.jpg"

def load_and_parse_shifts(json_path: Path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    shifts = []
    for item in data:
        raw_provider = item.get("provider", "Unassigned")
        if raw_provider == "Unassigned" or not raw_provider:
            continue
        last_name = raw_provider.split(',')[0].strip()
        
        start_str = item.get("startDate")
        end_str = item.get("endDate")
        if not start_str or not end_str:
            continue
            
        # Example format: "01/30/2026 17:00:00"
        start_dt = datetime.strptime(start_str, "%m/%d/%Y %H:%M:%S")
        end_dt = datetime.strptime(end_str, "%m/%d/%Y %H:%M:%S")
        
        shifts.append({
            "doctor": last_name,
            "start": start_dt,
            "end": end_dt
        })
    return shifts

def get_doctor_for_period(shifts, period_start, period_end):
    best_doc = ""
    max_overlap = 0
    for s in shifts:
        s_start = s["start"]
        s_end = s["end"]
        overlap_start = max(s_start, period_start)
        overlap_end = min(s_end, period_end)
        overlap = (overlap_end - overlap_start).total_seconds()
        if overlap > 0 and overlap > max_overlap:
            max_overlap = overlap
            best_doc = s["doctor"]
    return best_doc

def format_time(dt: datetime) -> str:
    temp = dt.strftime("%I:%M%p").lstrip("0")
    if temp.endswith(":00AM"):
        return temp.replace(":00AM", "AM")
    elif temp.endswith(":00PM"):
        return temp.replace(":00PM", "PM")
    return temp

def build_headless_calendar_data_v2(
    shifts_data: list,
    team_name: str,
    team_id: str,
    facility_id: str,
    facility_name: str,
    year: int,
    month: int
) -> dict:
    
    data = {
        "title": f"Nephrology Associates On-Call",
        "team": team_name,
        "facility": facility_name,
        "team_id": team_id,
        "facility_id": facility_id,
        "year": year,
        "month": month,
        "notes_left_html": "",
        "notes_right_html": "",
        "visible_shift_rows": 3,
        "days": []
    }
    
    calendar.setfirstweekday(6)  # Sunday-first to match render.py headers
    cal = calendar.monthcalendar(year, month)
    
    for row in cal:
        for weekday, day_num in enumerate(row):
            if day_num == 0:
                data["days"].append(None)
                continue
                
            current_date = datetime(year, month, day_num)
            day_shifts = []
            
            window_start = current_date.replace(hour=7, minute=0)
            window_end = (current_date + timedelta(days=1)).replace(hour=7, minute=0)
            
            if 1 <= weekday <= 4:
                # Mon-Thu (columns 1-4): 2 shifts — Day and Night
                split_time = current_date.replace(hour=17, minute=0) # Default to 5 PM
                
                # Check JSON for an actual afternoon/evening start time that reaches next morning
                for s in shifts_data:
                    if window_start < s["start"] < window_end and s["end"] >= window_end:
                        split_time = s["start"]
                        
                doc_day = get_doctor_for_period(shifts_data, window_start, split_time)
                doc_night = get_doctor_for_period(shifts_data, split_time, window_end)
                
                day_shifts.append({
                    "shift_type": "day",
                    "time_text": f"{format_time(window_start)}-{format_time(split_time)}",
                    "doctor": doc_day
                })
                day_shifts.append({
                    "shift_type": "night",
                    "time_text": f"{format_time(split_time)}-{format_time(window_end)}",
                    "doctor": doc_night
                })
            elif weekday == 5:
                # Friday (column 5): 2 shifts — Day + Weekend start
                split_time = current_date.replace(hour=17, minute=0)
                
                for s in shifts_data:
                    if window_start < s["start"] < window_end and s["end"] >= window_end:
                        split_time = s["start"]
                
                doc_day = get_doctor_for_period(shifts_data, window_start, split_time)
                doc_weekend = get_doctor_for_period(shifts_data, split_time, window_end)
                
                day_shifts.append({
                    "shift_type": "day",
                    "time_text": f"{format_time(window_start)}-{format_time(split_time)}",
                    "doctor": doc_day
                })
                day_shifts.append({
                    "shift_type": "weekend",
                    "time_text": f"{format_time(split_time)}-{format_time(window_end)}",
                    "doctor": doc_weekend
                })
            else:
                # Weekend — Sat (column 6) and Sun (column 0): 1 shift — All Day
                doc_weekend = get_doctor_for_period(shifts_data, window_start, window_end)
                day_shifts.append({
                    "shift_type": "allday",
                    "time_text": "all day",
                    "doctor": doc_weekend
                })
                
            data["days"].append({
                "day": day_num,
                "shifts": day_shifts
            })
            
    return data

def main():
    app = QGuiApplication(sys.argv)
    
    parser = argparse.ArgumentParser(description="Generate PDF from PerfectServe mappings.")
    parser.add_argument("--team", default="team-1", help="Team ID (e.g. team-1)")
    parser.add_argument("--year", type=int, default=2026, help="Target Year")
    parser.add_argument("--month", type=int, default=3, help="Target Month")
    parser.add_argument("--json-file", required=True, help="Path to the scraped JSON file")
    args = parser.parse_args()

    try:
        json_path = Path(args.json_file)
        if not json_path.exists():
            print(f"Error: Could not find scraped JSON file: {json_path}")
            sys.exit(1)
            
        shifts_data = load_and_parse_shifts(json_path)
    except Exception as e:
        print(f"Failed to load scraped JSON: {e}")
        sys.exit(1)

    universe = models.get_universe_data()
    relationships = models.get_relationships_data()
    if not universe or not relationships:
        print("Error: Could not load universe.json or team_relationships.json")
        sys.exit(1)

    team_def = universe.team_by_id.get(args.team)
    team_name = team_def.display_name if team_def else args.team

    team_rel = next((t for t in relationships.teams if t.team_id == args.team), None)
    facilities_to_render = []
    if team_rel:
        facilities_to_render = [fac.id for fac in team_rel.facilities]
    else:
        facilities_to_render = ["st-thomas-west"]

    last_export_path = None

    for facility_id in facilities_to_render:
        print(f"Generating PDF for {facility_id}...")
        
        facility_def = universe.facility_by_id.get(facility_id)
        facility_name = facility_def.full_name if facility_def else facility_id
        
        calendar_data = build_headless_calendar_data_v2(
            shifts_data=shifts_data,
            team_name=team_name,
            team_id=args.team,
            facility_id=facility_id,
            facility_name=facility_name,
            year=args.year,
            month=args.month
        )
        
        # Determine output path natively via distribution
        export_path, _ = distribution.resolve_calendar_artifact_path(
            team=team_name,
            year=args.year,
            month=args.month,
            artifact_type="pdf",
            facility=facility_name
        )
        
        # Make sure directory exists
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        image = render.render_calendar_to_image(calendar_data, str(LOGO_PATH))
        render.export_calendar_to_pdf(image, export_path)
        print(f"Success! Saved PDF: {export_path}")
        last_export_path = export_path

    print("\nBatch generation complete!")
    if last_export_path and last_export_path.exists():
        import os
        try:
            os.startfile(str(last_export_path.parent))
            print(f"Opened destination folder.")
        except Exception as e:
            print(f"Could not open folder automatically: {e}")

if __name__ == "__main__":
    main()
