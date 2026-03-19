# Compare View — Implementation Plan (Draft v1)

> **Status**: Draft — needs user review before execution
> **Created**: March 2026
> **Scope**: Build the core Compare View + wire up data pipelines

---

## Goal

A side-by-side view where the admin can visually compare Outlook calendar events against PerfectServe schedule data for any team/month, manage notes, and trigger PDF generation + distribution.

---

## Phase 1: Data Pipeline (Build First)

These are backend/CLI pieces that work regardless of UI choice.

### 1A. Scraper — Sub-Calendar "Follow" Resolution

**Problem**: Sub-calendars (e.g., Sumner Regional) say "Follow St. Thomas West Pod On-Call" instead of actual doctor names for night/weekend shifts.

**Implementation**:
- Update `scrape-shifts.js` to accept a `--master-json` flag
- When processing a sub-calendar, detect `title.startsWith("Follow ")` entries
- Look up the matching time window in the master calendar's scraped JSON
- Substitute the actual doctor name into the sub-calendar output
- Scrape order: master first, then subs

**Files**: `scraper/scrape-shifts.js`
**Test**: Scrape Team 1 STW (master), then Sumner (sub). Verify Sumner night/weekend entries have real doctor names.

### 1B. PDF Notes Sections

**Problem**: PDFs currently have empty `notes_left_html` and `notes_right_html`.

**Implementation**:
- Create `facility_notes.json` — standardized base notes per facility (right side)
- Add CLI args to `backend_pdf_generator.py`: `--vacation-notes` and `--facility-notes` (or read from config)
- Wire into `build_headless_calendar_data_v2()` → passes through to `render.py` (already supports it)
- Left side (vacation): manual text input, stored per team/month
- Right side (facility): base notes from config + optional per-month append

**Files**: `backend_pdf_generator.py`, new `facility_notes.json`
**Test**: Generate a PDF with vacation text on left and facility notes on right. Visual comparison against sample PDFs.

### 1C. Outlook Event Fetching

**Problem**: Need to pull Outlook events programmatically for the Compare View.

**Status**: Already done! `outlook_client.py` has:
- `list_calendars()` — personal/shared calendars
- `list_groups()` — M365 Group calendars (Teams 1 & 4)
- `list_events_in_range()` — personal calendar events
- `list_group_calendar_events()` — Group calendar events
- Auth with MSAL token cache working
- `scripts/dump_outlook_events.py` utility for testing

**Remaining**: Map team → calendar ID/group ID in a config file so the app knows which calendar to fetch for each team.

### 1D. Team → Calendar Mapping Config

**Implementation**: Add to `team_relationships.json` or a new `calendar_config.json`:

```json
{
  "team-1": { "type": "group", "id": "82150c9a-38f1-4392-babe-96ccd9a11d40" },
  "team-2": { "type": "calendar", "id": "AAMkADY2YWYx...UbnsasAAA=" },
  "team-3": { "type": "calendar", "id": "AAMkADY2YWYx...Q0_S6OAAA=" },
  "team-4": { "type": "group", "id": "67e582f3-3102-4d34-9e0e-604e3df9f40a" },
  "team-5": { "type": "calendar", "id": "AAMkADY2YWYx...U4RXrxAAA=" },
  "team-6": null,
  "team-7": null
}
```

**Files**: New `calendar_config.json` (gitignored since IDs are tenant-specific)

---

## Phase 2: Compare View UI

### Decision Needed: PySide6 or Web?

Not decided yet. Options:
- **PySide6**: Consistent with existing GUI, no hosting, but harder to iterate on UI
- **Web (Flask/FastAPI)**: Natural for the list+calendar layout, playground already proves the HTML/CSS, but adds a server
- **Hybrid**: PySide6 shell with embedded QWebEngineView rendering the HTML Compare View

Recommendation: Start with the HTML/CSS from the playground as the actual view. If PySide6, embed it via QWebEngineView. If web, serve it with FastAPI. The HTML is the same either way.

### 2A. Compare View Core

**Layout** (finalized via playground):
- Left panel (260px): Dense scrollable Outlook event list by day
- Right panel: Full month calendar grid (Sun-Sat) with PS shifts
- Below calendar: Facility notes + contact/distribution info
- Top toolbar: Team + facility selectors, month nav, PDF/Sent timestamps
- Click calendar cell → auto-scroll left list to that day

**Data flow**:
1. User selects team + month
2. App fetches Outlook events via `outlook_client.py` (using calendar_config mapping)
3. App loads PS JSON from scraped files (or triggers scrape)
4. Both displayed side-by-side
5. Vacation entries shown in red italic, instructions in blue italic on Outlook side
6. PS side shows colored shift type bars (day/night/weekend/allday/exception)

### 2B. Notes Input

- Vacation notes: editable text area (left panel bottom or below calendar)
- Facility notes: base from `facility_notes.json` + editable append
- Contact info: per-team presets from contacts config
- All notes flow into PDF generation when "Generate PDF" is clicked

### 2C. Actions

- **Generate PDF**: Calls `backend_pdf_generator.py` with current team/month/facility + notes
- **Send PDF**: Opens Outlook compose with PDF attached, recipients from contacts preset
- **Push to SharePoint**: Future — upload PDF to configured document library

---

## Phase 3: Contacts + Distribution

### 3A. Contact Storage

- JSON file with internal + external contacts
- Per-person: name, email, role (internal/external), teams they care about

### 3B. Distribution Presets

- Per-team (or per-facility): To list, CC list, subject template, body template
- Templates can use variables: `{team}`, `{month}`, `{year}`, `{facility}`

### 3C. Send Helper

- "Send PDF" button opens Outlook compose (via `mailto:` or Graph API)
- Pre-fills: recipients from preset, subject from template, body from template
- Attaches the most recently generated PDF
- User still manually hits send

---

## Phase 4: Version Tracking + Distribution Status

### 4A. PDF Version Log

- Track when each PDF was generated: team, facility, month, timestamp, file path
- Track when it was sent: timestamp, recipients
- Display in status bar and in a history panel

### 4B. Drift Detection

- After generating a PDF, record a "snapshot" of the PS data
- On next compare, flag if PS data changed since last PDF generation
- Flag if Outlook changed since last PDF generation
- Surface as: "PS updated since last PDF" warning

---

## Not In Scope

- Scheduling logic (PS owns the schedules)
- Outlook push for Teams 1-5 (they manage their own)
- Multi-user support
- Automated sync/push without user confirmation
- Replacing PerfectServe

---

## Open Questions

1. **PySide6 vs Web vs Hybrid** — affects Phase 2 implementation significantly
2. **Where do vacation notes persist?** — JSON file per team/month? SQLite? Just in-memory until PDF generation?
3. **Scraper team ID mapping** — only Team1 and Team6 are mapped in `scrape-shifts.js` TEAM_IDS. Need all 7.
4. **Exception handling in scraper** — what does a Team 1 exception look like in PS JSON? (e.g., doctor stuck on flight, split shift)
5. **Team 6/7 Outlook push** — hybrid approach (recurring weekends + push weekdays) not decided. Park for Phase 5?

---

## Execution Order

```
Phase 1A: Sub-calendar Follow resolution ← enables multi-facility PDFs
Phase 1B: PDF notes sections ← quick win, uses existing render engine
Phase 1D: Calendar config mapping ← needed before Compare View
Phase 2A: Compare View core ← the main deliverable
Phase 1C: Already done (Outlook fetching)
Phase 2B: Notes input ← feeds into PDF generation
Phase 2C: Actions (Generate/Send) ← ties it all together
Phase 3:  Contacts + distribution ← high value but independent
Phase 4:  Version tracking ← nice to have, builds on Phase 2
```
