# Nephrology On-Call Scheduling — Domain Model

This document captures the scheduling domain knowledge that helps agents understand why the data looks the way it does. It prevents false positives when validating or comparing schedule data.

---

## Core Concept: Master Schedule vs Facility View

**The master schedule is team-level truth**, especially for night and weekend coverage. A facility screen is a *slice* of that truth.

- Secondary facilities usually **inherit** the team's night coverage unless there's an explicit exception
- Day call is separate and facility-specific
- Extra/cross-team doctors are annotations for day coverage, not changes to core team truth
- Accepted facility-night differences must be explicit and require a reason — silent drift is dangerous

### Example: Team 1 / Sumner Regional

St. Thomas West = full Team 1 all-day coverage. But Sumner Regional is a *mixed view*:
- Weekday/Friday day: driven by Team 4 doctors (Choma default, Molini backup)
- Night: follows Team 1 master
- Weekend: all-day coverage

If scraped data shows Team 4 names at a Team 1 facility during the day, **that's correct**.

---

## Weekend/Friday Handoff Model

| Team | Weekday Split | Friday Split | Notes |
|------|--------------|-------------|-------|
| Team 1 | All day | All day | Modeled as all-day every day — the big exception |
| Team 2 | 5PM | 2PM | |
| Team 3 | 5PM | 2PM | |
| Team 4 | 5PM | 5PM | Major support team for other teams' day coverage |
| Team 5 | 5PM | 3PM | Maury Regional is the driver calendar |
| Team 6 | 5PM | 5PM | No online calendar — manual Excel/Word |
| Team 7 | 5PM | 5PM | Multiple source formats (Word, PowerPoint) |

For most teams: Friday = weekday day call first, then weekend coverage starts.
Saturday and Sunday are single all-day weekend coverage.

---

## Common Scheduling Patterns

### Rotation Patterns
- **Fixed n-week rotation**: 4 doctors = 4-week weekend rotation cycle
- **Alternating weekly**: Two doctors swap day call week-by-week
- **Fixed default**: One doctor covers all weekdays unless on vacation

### Fairness Rules
- **Pre-weekend rule**: Weekend doctor also covers Monday night that week
- **Rest rule**: After a weekend, doctor isn't assigned night again until Thursday of the following week
- **Equal distribution**: Night calls should be spread fairly

### Modified Rules (Doctor Out)
When 1 of 4 doctors is out:
- Weekend doctor: also covers Tuesday night + Friday-Sunday nights
- Previous weekend doctor: covers Wednesday night (shifted from Thursday)
- Third doctor: covers Monday + Thursday nights

### Backup Chains
- Formal backup pairs exist (e.g., Cardona/Rezk)
- Cross-team backup is common (e.g., Team 1's Atkinson backs up Team 5's Yu)
- Informal arrangements via email/text

---

## Exceptions Are Normal

Schedules always have exceptions. A doctor stuck on a flight, a partial shift swap, a one-off time change — these are routine, not edge cases.

- Never design around exactly 2 shifts per day — always allow a third row
- `shift_type: "exception"` and `visible_shift_rows: 3` support this
- 3+ entries for a single day in scraped data is valid
- Shift time changes for specific months happen (e.g., Team 6 changed weekend times)

---

## Validation Implications

When scraped PerfectServe data looks unexpected, check these before flagging as errors:

| Pattern | Likely Explanation |
|---------|-------------------|
| Same doctor on Monday night + weekend | Pre-weekend rule |
| Doctor absent from nights until Thursday after a weekend | Fairness/rest rule |
| Cross-team doctor names on day call | Backup chain / extra assignment |
| Same doctor across multiple facilities at night | Facility inheritance from driver calendar |
| 3+ shifts on one day | Exception / partial coverage |
| Different doctor on day vs night at same facility | Day call is facility-specific, night follows team master |

---

## Team Operational Notes

### Team 1
- If Yu is out, Atkinson should NOT be assigned to Team 1 call without verification

### Team 2
- Southern Hills transitioning from Word docs — verify when documents disagree

### Team 3
- Skyline day call managed outside the calendar app

### Team 5
- Maury Regional is the driver calendar
- Maury day call alternates weekly between Rezk and Cardona
- Ignore older Maury rotation calendars

### Team 6
- No online calendar — candidate for Outlook push (see `outlook_sync/`)
- Vacation context may require checking outside sources

### Team 7
- Multiple source formats — verify correct source document if things conflict
