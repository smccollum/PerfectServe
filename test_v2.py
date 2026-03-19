"""Quick visual test: render Team 1 March 2026 via the v2 backend and save as PNG."""
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render
from backend_pdf_generator import load_and_parse_shifts, build_headless_calendar_data_v2
import models

app = QGuiApplication(sys.argv)

json_path = Path(__file__).resolve().parent / "scraper" / "1-shifts.json"
shifts = load_and_parse_shifts(json_path)
print(f"Loaded {len(shifts)} shifts")

universe = models.get_universe_data()
relationships = models.get_relationships_data()

cal_data = build_headless_calendar_data_v2(
    shifts_data=shifts,
    team_name="Team 1",
    team_id="team-1",
    facility_id="st-thomas-west",
    facility_name="St. Thomas West",
    year=2026,
    month=3
)

total_with_doc = 0
for d in (cal_data.get("days") or []):
    if d:
        for s in d.get("shifts", []):
            if s.get("doctor"):
                total_with_doc += 1

print(f"Total shift slots with a doctor name: {total_with_doc}")

# Show a sample weekday
for d in (cal_data.get("days") or []):
    if d and d.get("shifts") and len(d["shifts"]) >= 2:
        print(f"\nSample day {d['day']}:")
        for s in d["shifts"]:
            print(f"  type={s['shift_type']}  time='{s['time_text']}'  doc='{s['doctor']}'")
        break

LOGO_PATH = Path(__file__).resolve().parent / "resources" / "logo.jpg"
image = render.render_calendar_to_image(cal_data, str(LOGO_PATH))
out = Path(__file__).resolve().parent / "test_output.png"
image.save(str(out))
print(f"\nSaved test image: {out}")
