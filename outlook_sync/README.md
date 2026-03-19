# Outlook Sync (Read/Write) — Preserved from CalendarApp v1

This directory contains the full Outlook Graph API sync client from the legacy CalendarApp.
It includes both **read** and **write** capabilities.

## Why It's Here

The main app uses `outlook_client.py` (read-only) for the Compare View. However,
some teams may need actual push-to-Outlook functionality:

- **Team 6** uses manual Excel/Word scheduling and doesn't have an online calendar.
  Pushing a generated calendar to an Outlook calendar could be valuable.
- One of the Team 6 doctors maintains a vacation Outlook calendar that could be
  a target for on-call schedule pushes.

## What's In Here

- **`ms365_sync.py`** — Full sync client with:
  - `OutlookSyncClient` — Create, update, delete events via Graph API
  - Identity-based ownership via extended property GUID (`554ce722-8c50-4ef7-88fb-445f0c3b6c8e`)
  - Compare-first mutation (list → diff → mutate, fail closed)
  - Retry logic with rate-limit handling
  - `sync_events()` — Full sync with create/update/delete
  - `delete_events()` / `delete_events_for_month()` — Scoped cleanup
  - `build_event_payloads()` — Calendar data → Graph event payloads
  - `parse_shift_time()` — Human-readable time string parser
  - `map_shift_to_event()` — Shift → Graph event payload builder

## Scopes Required

If you use the write client, you'll need `Calendars.ReadWrite` (not just `Calendars.Read`):

```python
SCOPES = [
    "User.Read",
    "Calendars.ReadWrite",
    "Calendars.ReadWrite.Shared",
]
```

## Status

Preserved for future use. Not currently wired into the v2 pipeline.
