# Review Profile — PerfectServe Pipeline

> **Last Updated**: March 2026
> **Project Stage**: Early development — building core pipeline features

---

## Role → Model Mapping

| # | Role | Model | CLI / Method |
|---|------|-------|-------------|
| 1 | Ground-truth | GPT-5.4 (Codex) | `codex exec` |
| 2 | Systems-safety | Gemini 3.1 Pro | `gemini -p` |
| 3 | Collateral-damage | Claude Opus 4.6 | Fresh subagent |
| 4 | Integration-audit | GPT-5.4 (ChatGPT) | Manual (web) |
| 5 | Fresh-eyes | Flexible | Assign per feature |

---

## Hard Invariants

Every reviewer must verify changes do NOT violate these:

1. **PDF layout is sacred** — one-page landscape letter (11"x8.5") at 200 DPI. Sunday-first grid. Do not change without explicit approval.
2. **JSON stays human-readable** — 2-space indentation, no minification for data files.
3. **No hardcoded credentials** — all secrets via environment variables. Never in source.
4. **PerfectServe is truth** — scraped data is authoritative for on-call schedules. App does not create or modify schedules.
5. **No TeamYearSchedule** — v2 reads raw scraped JSON directly. Do not wire in v1 intermediate formats.
6. **Render engine contract** — `render_calendar_to_image()` accepts a dict with `days`, `team`, `facility`, `month`, `year`, `visible_shift_rows`, `notes_left_html`, `notes_right_html`. Do not change this interface.
7. **Shift flexibility** — always support exception/override shifts beyond the 2-per-day base. `visible_shift_rows: 3` minimum.
8. **Facility views are slices** — a facility showing cross-team doctors on day call is correct behavior, not an error.
9. **Distribution paths must work offline** — OneDrive, central, custom, or fallback. Never require network for saving PDFs.

---

## Technology-Specific Focus Areas

- **PySide6/Qt** — QPainter rendering, QProcess for subprocess management, no QML
- **Node.js / Playwright** — headless browser automation, API interception, auth state persistence
- **Windows paths** — forward slashes in code, but output paths must work on Windows (NTFS)
- **Microsoft Graph API** — MSAL public client auth, token cache, calendar read operations
- **Python 3.11+** — dataclasses, pathlib, type hints

---

## Domain Context

Medical on-call scheduling for nephrology. Getting the schedule wrong has real consequences for patient care. Key domain concepts:

- Master schedule = team-level truth (especially night/weekend)
- Facility views are slices — secondary facilities inherit night coverage
- Day call is separate and facility-specific
- Extra/cross-team doctors are annotations for day coverage
- Exceptions are normal (partial shifts, backup coverage, flight delays)
- Teams have different Friday split times (2PM, 3PM, 5PM)

See `docs/domain/scheduling-model.md` for full domain context.

---

## File Conventions

| Type | Location |
|------|----------|
| Plans | `docs/AutoPlan/<feature>/plan.md` |
| Plan versions | `docs/AutoPlan/<feature>/versions/` |
| Review prompts/findings | `docs/AutoPlan/<feature>/reviews/` |
| Pipeline state | `docs/AutoPlan/<feature>/status.json` |
| Changelog/learning | `docs/AutoPlan/<feature>/changelog.md` |
| Domain context | `docs/domain/` |

---

## Phase-Specific Review Focus

Current phase: **Early development**

- Focus on: correctness, contract stability, clean boundaries
- Lighter focus on: performance, edge cases, scalability
- Skip: heavy security audit (single user, local app)

As the app matures and if features like Outlook push (Team 6) are added, shift to pilot-phase focus: user-facing edge cases, error UX, data integrity.
