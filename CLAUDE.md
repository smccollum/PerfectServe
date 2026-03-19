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

## Architecture

| Component | Location | Stack |
|---|---|---|
| Scraper | `scraper/` | Node.js + Playwright |
| PDF pipeline | `backend_pdf_generator.py` | Python + PySide6 |
| Rendering | `render.py` | QPainter → QPdfWriter |
| GUI | `perfectserve_gui.py` | PySide6 |
| Outlook reader | `outlook_client.py` | MSAL + Graph API (read-only) |
| Outlook push | `outlook_sync/` | Full read/write client (preserved for Team 6) |
| Domain data | `universe.json`, `team_relationships.json`, `team_notes.json` | JSON |
| Domain model | `models.py` | Python dataclasses |
| Output paths | `distribution.py` | OneDrive / central / custom / fallback |

---

## How to Run

```bash
pip install -r requirements.txt
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
7. Exceptions to 2-shifts-per-day are normal — always support `visible_shift_rows: 3`
8. When in doubt, stop and ask

---

## Deep Context (read when relevant)

| Topic | File | When to Read |
|---|---|---|
| Domain model (scheduling, team rules, exceptions) | `docs/domain/scheduling-model.md` | Validating scraped data, building Compare View, understanding cross-team coverage |
| Review pipeline (multi-model review process) | `.claude/review-profile.md` | Before reviewing any plan or running `/review-squad` |
| Outlook push context (Team 6) | `outlook_sync/README.md` | Working on Outlook integration or Team 6 features |
| Gemini reviewer instructions | `GEMINI.md` | Generating Gemini review prompts |
| Heritage (v1 legacy context) | Legacy repo at `D:\_CalendarApp` | If something seems missing or needs v1 reference |
