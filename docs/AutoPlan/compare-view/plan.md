# Compare View — Implementation Plan v2

> **Status**: Ready to execute — Phase 1 first
> **Updated**: March 2026

---

## Architecture Decision

Build the Compare View as **standalone HTML/CSS/JS** backed by JSON data files. This keeps the PySide6-vs-web decision open:
- PySide6 route: embed via `QWebEngineView` (same HTML)
- Web route: serve via FastAPI (same HTML)
- For now: open in browser, load JSON via fetch or inline

The HTML playground at `docs/design/compare-view-v3.html` is the approved layout reference.

---

## Phase 1: Data Pipeline

Backend pieces that work regardless of UI. Build these first.

### 1A. PDF Notes Sections (Quick Win)

The render engine already supports `notes_left_html` (vacation) and `notes_right_html` (facility/contact info). Currently set to empty strings in `backend_pdf_generator.py:86-87`.

**Create `facility_notes.json`:**
```json
{
  "st-thomas-west": {
    "base_notes": "Night call follows Team 1 master schedule\nDay call at STW = same as night call"
  },
  "sumner-regional": {
    "base_notes": "Day call: Choma default, Molini backup (Team 4)\nNight call: Follows St. Thomas West"
  },
  "cmc": {
    "base_notes": "Friday night/weekend starts at 2PM\nCalendar managed by Dr. Soni"
  }
}
```

**Create `vacation_notes.json`:**
```json
{
  "team-1": {
    "2026-03": "Yu off: Mar 7-15\nRezk off: Mar 18-20"
  }
}
```

Storage is simple HTML/text keyed by team + month. Future: Team 6 structured vacation calendar can *generate* this same format instead of manual entry — no refactoring needed.

**Changes to `backend_pdf_generator.py`:**
1. Add `--vacation-notes` CLI arg (raw text, optional)
2. Add `--append-notes` CLI arg (extra right-side text, optional)
3. Load `facility_notes.json` to get base right-side text for the facility
4. Concatenate base + append for `notes_right_html`
5. Pass vacation text as `notes_left_html`

**Files to change:** `backend_pdf_generator.py` (lines 68-90, 166-248)
**Files to create:** `facility_notes.json`, `vacation_notes.json`
**Test:** Generate a Team 5 Maury PDF with vacation notes. Compare against `docs/samplepdfs/2026-03 – Team 5 – Maury Regional.pdf` which shows the notes layout.

### 1B. Sub-Calendar "Follow" Resolution

**Problem:** Sub-calendar PS JSON has `title: "Follow St. Thomas West Pod On-Call"` instead of doctor names for night/weekend shifts.

**Detection:** `title.startsWith("Follow ")` in the scraped JSON.

**Solution — resolve in Python, not JavaScript:**

The scraper (`scrape-shifts.js`) stays simple — it dumps whatever PS returns. The resolution happens in `backend_pdf_generator.py` when building the calendar data.

Add function to `backend_pdf_generator.py`:
```python
def resolve_follow_entries(sub_shifts, master_shifts):
    """
    For each shift in sub_shifts where the provider starts with "Follow ",
    find the matching time window in master_shifts and substitute the
    master's doctor name.
    """
    resolved = []
    for shift in sub_shifts:
        if shift["doctor"].startswith("Follow "):
            # Find master shift that overlaps this time window
            doc = get_doctor_for_period(master_shifts, shift["start"], shift["end"])
            resolved.append({**shift, "doctor": doc if doc else "Unresolved"})
        else:
            resolved.append(shift)
    return resolved
```

**Flow:**
1. Scrape master facility JSON (e.g., Team1-STW-March2026-shifts.json)
2. Scrape sub facility JSON (e.g., Team1-Sumner-March2026-shifts.json)
3. Load both in `backend_pdf_generator.py`
4. Call `resolve_follow_entries(sub_shifts, master_shifts)` before building calendar data
5. Render PDF as usual

**Add CLI args:** `--master-json <path>` (optional, only needed for sub-calendars)

**Files to change:** `backend_pdf_generator.py`
**Test:** Use `docs/samplejson/samplesumner.txt` (sub) + `docs/samplejson/samplestthomaswest.master.txt` (master). Verify Sumner night entries get real doctor names.

### 1C. Team → Calendar Config

**Create `calendar_config.json`** (gitignored — contains tenant-specific IDs):
```json
{
  "team-1": { "type": "group", "id": "82150c9a-38f1-4392-babe-96ccd9a11d40", "name": "Team1 Group Calendar" },
  "team-2": { "type": "calendar", "id": "AAMkADY2YWYx...UbnsasAAA=", "name": "CMC POD Call Schedule" },
  "team-3": { "type": "calendar", "id": "AAMkADY2YWYx...Q0_S6OAAA=", "name": "4Call" },
  "team-4": { "type": "group", "id": "67e582f3-3102-4d34-9e0e-604e3df9f40a", "name": "Team4 Group Calendar" },
  "team-5": { "type": "calendar", "id": "AAMkADY2YWYx...U4RXrxAAA=", "name": "Team 5" },
  "team-6": null,
  "team-7": null
}
```

**Add helper to `outlook_client.py`:**
```python
def fetch_team_events(self, team_id, year, month, calendar_config):
    """Fetch events for a team using the right endpoint (calendar vs group)."""
    config = calendar_config.get(team_id)
    if not config:
        return [], "No calendar configured for this team"
    range_start = datetime(year, month, 1)
    range_end = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)
    if config["type"] == "group":
        return self.list_group_calendar_events(group_id=config["id"], ...)
    else:
        return self.list_events_in_range(calendar_id=config["id"], ...)
```

**Files to change:** `outlook_client.py`
**Files to create:** `calendar_config.json` (gitignored)
**Status:** Outlook calendar IDs confirmed for Teams 1-5 (see `domain_calendar_types.md` memory). Teams 6-7 = null (no Outlook calendar).

### 1D. Scraper Team ID Mapping

Currently `scraper/scrape-shifts.js` only maps Team1 and Team6 in the `TEAM_IDS` object (line 8-11). Need all 22 schedule IDs.

**Status: RESOLVED.** All 22 PS schedule IDs captured in `ps_schedule_config.json`. Update `scrape-shifts.js` to read from this config instead of hardcoded mapping.

### 1E. Settings GUI — NOT NEEDED

Since v2 just displays what PS gives us, there's no need for doctor/team/facility management screens. If PS adds a new doctor or changes a relationship, the scraped data reflects it automatically. The only config files are:
- `ps_schedule_config.json` — PS schedule IDs (rarely changes, edit JSON directly)
- `calendar_config.json` — Outlook calendar IDs (rarely changes)
- `facility_notes.json` — editable in the Compare View UI
- `vacation_notes.json` — editable in the Compare View UI

The v1 CalendarApp has ~3,000 lines of settings GUI in `editor.py` (lines 424-3777) that can be referenced if management screens are ever needed. For now, skip it.

---

## Phase 2: Compare View UI

### 2A. Core Layout

Build as a single HTML file (like the playground) that reads data from JSON.

**Layout** (approved via playground iteration):
- **Left panel (260px):** Dense scrollable Outlook event list. ~24px rows for single events, adaptive height for multi-event days. Vacation in red italic, instructions in blue italic. Click day → scroll right calendar.
- **Right panel:** Full month calendar grid (Sun-Sat). Colored left-edge bars: blue=day, purple=night, green=weekend/allday, amber=exception. Notes sections pinned below.
- **Top nav:** Schedules | Contacts | Distribution tabs
- **Toolbar:** Team + Facility dropdowns, month nav arrows, PDF/Sent timestamps

**Data loading:**
1. Read `calendar_config.json` to know which Outlook source to use
2. Read scraped PS JSON for the selected team/month/facility
3. Read `facility_notes.json` for right-side base notes
4. Read `vacation_notes.json` for left-side vacation text

**Interaction:**
- Change team → reload both panels, update facility dropdown
- Change facility → reload PS side only (Outlook is team-level)
- Click calendar cell → left list auto-scrolls to that day
- Click left list day → highlight corresponding calendar cell

### 2B. Notes Input

- Vacation notes: editable text area below left list (or below calendar — TBD based on space)
- Facility notes: base from config shown as read-only, plus editable append area
- Contact info: from contacts config (Phase 3), shown below calendar
- "Save Notes" persists to `vacation_notes.json`

### 2C. Actions

- **Generate PDF** button: calls `backend_pdf_generator.py` with current selections + notes
- **Open PDF** button: opens the most recent PDF for this team/facility/month
- **Send PDF** button: placeholder for Phase 3 (opens Outlook compose)
- **Push to SharePoint** button: placeholder for future

---

## Phase 3: Contacts + Distribution (After Phase 2 works)

- `contacts.json`: name, email, role, teams
- `distribution_presets.json`: per-team To/CC/subject/body templates
- Send helper: pre-fills Outlook compose with PDF + recipients
- UI: Contacts tab in the nav

---

## Phase 4: Version Tracking (Nice to Have)

- Log each PDF generation: team, facility, month, timestamp, path
- Log each send: timestamp, recipients
- Show in status bar: "PDF: Mar 15 3:42PM | Sent: Mar 15 3:45PM"
- Flag drift: "PS updated since last PDF" warning

---

## Phase 5: Team 6/7 Outlook Push (Parked)

- Hybrid approach: recurring weekends + push weekdays
- Uses `outlook_sync/ms365_sync.py` (preserved)
- Standardized events with `~` prefix for vacation sorting
- Single-day entries only (never multi-day spans)
- Not started — decision pending

---

## Execution Order

```
1A. PDF notes sections   ← quickest win, ~30 min
1B. Follow resolution    ← enables sub-calendar PDFs
1C. Calendar config      ← enables Compare View data loading
1D. Scraper ID mapping   ← RESOLVED (ps_schedule_config.json), just wire into scrape-shifts.js
1E. Settings GUI         ← NOT NEEDED for v2
2A. Compare View core    ← the main deliverable
2B. Notes input          ← feeds into PDF generation
2C. Actions              ← ties it together
3.  Contacts             ← independent, high value
4.  Version tracking     ← nice to have
5.  Outlook push         ← parked
```

**No open blockers.** Start with **1A** (PDF notes) — it's a quick win that proves the notes pipeline works before building the full Compare View.

---

## Key Reference Files

| File | Purpose |
|---|---|
| `ps_schedule_config.json` | All 22 PS schedule IDs, master/follow relationships, active flags |
| `calendar_config.json` | Outlook calendar IDs per team (gitignored) |
| `docs/samplejson/ps-*.json` | Real PS API responses for all teams/facilities (March 2026) |
| `docs/sampleoutlookcalendars/*_graph.json` | Real Outlook events for Teams 1-5 (March 2026) |
| `docs/samplepdfs/*.pdf` | Real production PDFs for all 18 facilities (March 2026) |
| `docs/design/compare-view-v3.html` | Approved Compare View layout (interactive playground) |
| `CLAUDE.md` | Project context + deep context reference table |
| `.claude/review-profile.md` | Review invariants and role→model mapping |
