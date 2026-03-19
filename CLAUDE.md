# PerfectServe Pipeline — Project Context

> **Last Updated**: March 2026

---

## What This Is

A single-user desktop tool for a nephrology practice admin who manages on-call schedules across 7 teams and 18+ hospital facilities.

**Product shape**: "PerfectServe extractor + PDF generator + send assistant"

```
PerfectServe (web) → Playwright scraper → JSON → PDF renderer → Outlook send helper
```

PerfectServe already holds the authoritative schedule data. This tool extracts it, renders professional one-page PDFs, and helps distribute them. **We are not building a scheduling engine.**

---

## Heritage

This project was extracted from a legacy CalendarApp (v1) that tried to be a full scheduling + Outlook sync desktop app. The v1 repo (`_CalendarApp`) still exists for reference. Key modules were carried forward:

| Module | Origin | Role |
|---|---|---|
| `render.py` | v1 shared | Calendar image/PDF rendering (QPainter) |
| `models.py` | v1 shared | Domain schemas, validation, universe/relationship accessors |
| `distribution.py` | v1 shared | Output path resolution (OneDrive, central, custom) |
| `outlook_client.py` | Extracted from v1 `ms365_sync.py` | Read-only Outlook Graph API client |
| `backend_pdf_generator.py` | v2 native | Core scrape→PDF pipeline |
| `perfectserve_gui.py` | v2 native | PySide6 dashboard GUI |

---

## Architecture

### Scraper Pipeline (Node.js)

Located in `scraper/`:

1. **`setup-auth.js`** — Logs into PerfectServe via Playwright, saves session to `auth.json`
   - Credentials via env vars: `PERFECTSERVE_USERNAME`, `PERFECTSERVE_PASSWORD`
2. **`scrape-shifts.js`** — Intercepts bearer token, calls PerfectServe API directly
   - Maps team names to schedule IDs (currently Team1 and Team6 mapped)
   - Output: `{TeamPrefix}-{Month}-shifts.json`

### PDF Generation (Python)

1. `backend_pdf_generator.py` loads scraped JSON
2. `load_and_parse_shifts()` normalizes provider names + datetime ranges
3. `get_doctor_for_period()` uses time-overlap matching (not name matching)
4. `build_headless_calendar_data_v2()` constructs calendar grid:
   - Mon–Thu: 2 rows (Day 7AM–5PM, Night 5PM–7AM)
   - Friday: 2 rows (Day 7AM–5PM, Weekend start 5PM–7AM)
   - Sat–Sun: 1 row (all day)
   - Auto-detects shift split time from data (default 5PM)
5. `render.py` paints to QImage → QPdfWriter (landscape letter, 200 DPI)
6. `distribution.py` resolves output path

### Outlook Reader

`outlook_client.py` — Read-only Graph API client for the Compare View:
- Lists calendar folders
- Fetches events in a date range
- MSAL auth with persistent token cache
- Config: `AZURE_TENANT_ID` + `AZURE_CLIENT_ID` env vars

---

## Data Files

| File | Purpose |
|---|---|
| `universe.json` | Master definitions: 27 doctors, 7 teams, 18 facilities |
| `team_relationships.json` | Team ↔ facility ↔ doctor mappings + extra assignments |
| `team_notes.json` | Human-readable scheduling rules per team |

---

## Per-Team Shift Rules

Teams have different Friday split times (defined in `models.py`):

| Team | Weekday Split | Friday Split |
|---|---|---|
| Team 1 | 5PM | 5PM (night, not weekend) |
| Team 2 | 5PM | 2PM |
| Team 3 | 5PM | 2PM |
| Team 4 | 5PM | 5PM (default) |
| Team 5 | 5PM | 3PM |
| Team 6 | 5PM | 5PM (default) |
| Team 7 | 5PM | 5PM (default) |

---

## Domain Model (Why the data looks the way it does)

Understanding these concepts prevents misinterpreting scraped data:

**Master schedule = team-level truth.** Night and weekend coverage is defined at the team level. A facility view is a *slice* of that truth — secondary facilities inherit the team's night coverage unless there's an explicit exception.

**Day call is separate and facility-specific.** Extra/cross-team doctors (e.g., Team 4's Choma covering Sumner day for Team 1) are annotations for day coverage, not changes to core team truth.

**Example — Team 1 / Sumner Regional:** St. Thomas West = full Team 1 all-day. But Sumner is a *mixed view*: weekday day is Team 4 doctors, night follows Team 1 master. If scraped data shows Team 4 names at a Team 1 facility during the day, that's correct, not an error.

**Team 1 is modeled as all-day every day** (no day/night split on the master schedule). Other teams follow the standard day/night + weekend pattern.

**Team 6 has no online calendar** — they use manual Excel/Word. They may need Outlook push (see `outlook_sync/`).

---

## Planned Features

### 1. PerfectServe → PDF (Primary Engine) — Working
Scrape → normalize → render → save PDF

### 2. Compare View (Read-Only) — Planned
- Left: Outlook events (vertical list via `outlook_client.py`)
- Right: PerfectServe schedule (rendered preview)
- Purpose: quick mismatch spotting — no sync logic

### 3. Contacts + Distribution — Planned
- Internal/external contact storage
- Per-team presets: To/CC, subject template, body template

### 4. "Send PDF" Helper — Planned
- One-click: opens Outlook compose, attaches PDF, fills recipients
- User still hits send manually

### 5. Settings GUI — Planned
- Simple screens for contacts, distribution presets, templates

---

## What We Are NOT Doing

- Building a scheduling engine
- Multi-user support
- Heavy Outlook sync/push automation
- Replacing PerfectServe
- Solving every team's scheduling logic

---

## How to Run

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install scraper dependencies
cd scraper && npm install && cd ..

# Set credentials (PowerShell)
$env:PERFECTSERVE_USERNAME="your.username"
$env:PERFECTSERVE_PASSWORD="your.password"

# GUI mode
python perfectserve_gui.py

# CLI mode
python backend_pdf_generator.py --team team-1 --year 2026 --month 3 \
    --json-file scraper/Team1-March2026-shifts.json
```

---

## Agent Rules

1. **Read this file first** before making changes
2. Does NOT use `TeamYearSchedule` — reads raw scraped JSON directly
3. The PDF output format (one-page calendar) is sacred — don't change layout without approval
4. JSON save format must remain human-readable (2-space indentation)
5. `render.py` produces landscape letter-size PDFs at 200 DPI with Sunday-first grid
6. Credentials must NEVER be hardcoded — use environment variables
7. When in doubt, stop and ask
