# RESULTED Display Bug — Investigation Report

## Symptom
Kaity's /monitor shows MANY races as "RESULTED" (Cranbourne R1 02:25, Doomben R1 02:33, Canterbury R1 02:50, etc.), but jett's DB check found only 8 races on 2026-08-05 with `race_status='resulted'` (legit past races 23:00-00:45 UTC).

Frontend shows "RESULTED" for races the DB does NOT mark as resulted.

## Root Cause

### 1. Frontend Ignores DB race_status
**File:** `monitor.html`
**Lines:** 1132, 1408-1409

```javascript
const raceStatus = race.race_status || 'open';  // L1132 — fetched but NEVER USED

// L1408-1409 — countdown derived ONLY from scheduled time, not race_status
if (jumped) {
  countdown = secs > -900 ? 'JUMPED' : 'RESULTED';
}
```

**Bug:** Frontend derives "RESULTED" status purely from `secs <= -900` (scheduled time >15min past), completely ignoring the actual `race.race_status` field from the DB.

### 2. Timezone Mismatch in Time Comparison
**Lines:** 1128-1130, 798

```javascript
// L798 (getBrisbaneToday used for date selection)
const getBrisbaneToday = () => {
  const now = new Date();
  const brisbane = new Date(now.toLocaleString('en-US', { timeZone: 'Australia/Brisbane' }));
  return brisbane.toISOString().split('T')[0];
};

// L1128 — Parse race time as LOCAL (browser timezone)
const scheduledTime = new Date(`${race.race_date}T${race.race_time}`).getTime();

// L1129 — Compare against UTC now
const secs = Math.round((scheduledTime - now) / 1000);
const jumped = secs <= 0;
```

**Bug:** `new Date("2026-08-05T02:25")` parses the ISO string as **local browser time**, but the comparison is against `Date.now()` (UTC milliseconds). This creates a timezone-dependent offset.

**Example scenario (Brisbane UTC+10):**
- API returns: `race_date="2026-08-05"`, `race_time="02:25"` (Brisbane 02:25)
- Frontend parses: `new Date("2026-08-05T02:25")` as **local** time
  - If user's browser is in UTC: parses as 2026-08-05 02:25 UTC
  - If browser is Brisbane (UTC+10): parses as 2026-08-05 02:25 Brisbane = 2026-08-04 16:25 UTC
- Current time: 2026-08-05 04:20 UTC (Brisbane 14:20)
- Comparison:
  - UTC browser: secs = (02:25 UTC - 04:20 UTC) = -7500s → jumped=true → "JUMPED"
  - Brisbane browser: secs = (16:25 UTC prev day - 04:20 UTC) = -42900s → "RESULTED"

**The timezone interpretation of `race_time` is inconsistent.**

### 3. Display Time Also Local
**Line:** 1416-1417

```javascript
const d = new Date(scheduledTime);
const timeLabel = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
```

The displayed time (e.g. "02:25") is `d.getHours()` which returns **local** hours. If the race_time from the API is already Brisbane time, and the browser is NOT in Brisbane, the displayed time will be wrong.

## Correct Behavior

1. **RESULTED status should reflect actual race_status from DB**, not a time-based guess.
   - DB says `race_status='resulted'` → show "RESULTED"
   - DB says `race_status='open'` or `'interim'` → show time-based countdown/JUMPED
   - Don't show "RESULTED" for races that haven't actually resulted

2. **Timezone handling must be explicit:**
   - API sends `race_time` in Brisbane time (spec should confirm this)
   - Frontend should parse it explicitly as Brisbane, not local
   - All time comparisons should be in the same timezone

## Recommended Fix

### Option 1: Use race_status from DB (simplest)
```javascript
let countdown;
if (raceStatus === 'resulted') {
  countdown = 'RESULTED';
} else if (jumped) {
  countdown = 'JUMPED';
} else if (secs < 3600) {
  countdown = `${Math.floor(secs / 60)}m ${String(secs % 60).padStart(2, '0')}s`;
} else {
  countdown = `${Math.floor(secs / 3600)}h ${String(Math.floor(secs % 3600 / 60)).padStart(2, '0')}m`;
}
```

### Option 2: Fix timezone handling (if race_time is Brisbane)
```javascript
// Parse race_time explicitly as Brisbane
const BRISBANE_TZ = 'Australia/Brisbane';
const scheduledTime = new Date(`${race.race_date}T${race.race_time}`);
// Convert to Brisbane timezone for comparison
const brisbaneDateStr = scheduledTime.toLocaleString('en-US', { 
  timeZone: BRISBANE_TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false
});
const brisbaneScheduled = new Date(brisbaneDateStr).getTime();
const nowBrisbane = new Date(new Date().toLocaleString('en-US', { timeZone: BRISBANE_TZ })).getTime();
const secs = Math.round((brisbaneScheduled - nowBrisbane) / 1000);
```

**OR** if the API sends race_time already in Brisbane and the frontend should treat it as such, append timezone offset:
```javascript
const scheduledTime = new Date(`${race.race_date}T${race.race_time}+10:00`).getTime(); // Force Brisbane UTC+10
```

### Option 3: Hybrid (recommended)
- Use `race_status='resulted'` from DB as authoritative for "RESULTED"
- Fix timezone handling for accurate jump-time countdown
- Fall back to time-based "JUMPED" only when race_status is NOT 'resulted'

## Evidence

**DB query (jett):** Only 8 races on 2026-08-05 with `race_status='resulted'` (races 23:00-00:45 UTC, actual past races with finishers).

**Frontend display (Kaity):** Many races showing "RESULTED" including:
- Cranbourne R1 02:25
- Doomben R1 02:33
- Canterbury R1 02:50
- Cranbourne R2 03:00
- Doomben R2 03:08

These are Brisbane morning races (02:25-03:08 Brisbane = 16:25-17:08 UTC prev day), NOT past/resulted races.

## Impact

- Users see races as "RESULTED" when they haven't run yet
- Frontend countdown/JUMPED logic is unreliable
- RESULTED status doesn't reflect actual DB race_status
- Timezone confusion makes time displays wrong for non-Brisbane users

## Next Steps

1. Confirm API contract: is `race_time` sent in Brisbane time or UTC?
2. Implement fix: use `race_status` from DB for "RESULTED" display
3. Fix timezone handling for accurate time comparisons
4. Test with real data: verify "RESULTED" only shows for DB-resulted races
5. Verify time display matches API-sent race_time regardless of user timezone
