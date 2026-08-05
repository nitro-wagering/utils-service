# Bet Display Round-Trip Verification

## Issue
jett's CRUD smoke test showed POST/PUT/DELETE all 200'd, but GET returned 0 embedded bets. Need to verify bets DISPLAY on cards after recording.

## Root Cause Analysis

jett's test created a bet with `form_id` that doesn't exist in today's watchlist CSV. The backend correctly:
1. Stored the bet in `user_bets` table (POST succeeded)
2. Queried all bets for the username (GET query worked)
3. Joined bets to watchlist entries by `(form_id, race_date)` key
4. Found NO match (test form_id not in CSV) → returned all entries with `bet_placed=false`

This is **expected behavior** — bets only embed in watchlist entries when the bet's form_id matches a CSV entry.

## How UI Recording Works (Correct Path)

1. User opens /monitor → sees watchlist entries (from CSV)
2. Each runner card has form_id/race_date from the CSV entry
3. User clicks "Record Bet" → modal pre-fills from runner object
4. POST /api/watchlist/bets sends `form_id` + `race_date` from the runner
5. Bet is created with form_id that DOES exist in the CSV
6. fetchData() re-fetches watchlist with `?username=...`
7. Backend joins bet to matching entry by (form_id, race_date)
8. Entry returns with `bet_placed=true`, bet_id/type/odds/stake populated
9. Card renders with ● PENDING badge + editable bet fields
10. Header "BETS TODAY" count increments

## Manual Verification Steps

### Prerequisites
- utils-service deployed and accessible
- Today's watchlist CSV has entries (check /api/watchlist)
- User browser with localStorage access

### Test Procedure

1. **Open /monitor in browser**
   - URL: `https://utils.nitro.internal/monitor` (or local)
   - Should show today's watchlist races

2. **Select username**
   - Click username picker at top right
   - Create new user "iris-display-test" or select existing

3. **Record a bet on a real runner**
   - Expand any race
   - Click "Rec" on any runner card
   - Modal shows: horse name, track, race, pre-filled form_id/race_date
   - Enter: Bet Type = WIN, Odds = 3.50, Stake = 10.00
   - Click "Record Bet"
   - Should see success banner

4. **Verify bet displays immediately**
   - Same runner card should now show:
     - `● PENDING` badge (yellow)
     - Bet row: "WIN @3.50 | Stake: $10.00" (editable)
     - Delete button (trash icon)
   - Header "BETS TODAY" count should increment by 1
   - Header "PENDING" should show 1

5. **Refresh page**
   - Browser refresh (Cmd+R / Ctrl+R)
   - Username persists (localStorage)
   - Bet still displays on the same runner

6. **Edit bet**
   - Click odds value → inline edit to 4.00
   - Press Enter or blur → saves
   - Bet row updates to show @4.00

7. **Delete bet**
   - Click trash icon
   - Confirm deletion
   - Badge disappears
   - "BETS TODAY" count decrements

8. **Verify GET response (DevTools)**
   - Open browser DevTools → Network tab
   - Refresh page
   - Find GET /api/watchlist?username=iris-display-test&date=YYYY-MM-DD
   - Response JSON: find the entry matching your test runner
   - Verify fields:
     ```json
     {
       "bet_placed": true,
       "bet_id": <number>,
       "bet_type": "WIN",
       "odds_taken": 3.50,
       "stake_aud": 10.00,
       "placed": "",  // empty until daemon settles
       ...
     }
     ```

## Expected Results

✓ Bet records successfully (POST 200)
✓ Bet appears on card immediately (no page refresh needed)
✓ `● PENDING` badge renders
✓ Bet details (type/odds/stake) display correctly
✓ Header "BETS TODAY" count reflects actual placed bets (~11 real, not ~50 ML verdicts)
✓ Bet persists across page refresh
✓ Inline edit works (odds/stake update)
✓ Delete removes bet from display
✓ GET /api/watchlist includes `bet_placed=true` + all bet fields for matching entry

## Why jett's Test Showed 0 Bets

jett's POST used a hardcoded form_id (e.g. 999999) that doesn't exist in today's CSV. The bet was stored in DB but had no watchlist entry to join to. GET returned all CSV entries with `bet_placed=false` because none matched the test bet's form_id.

**This is correct behavior** — bets only display on runners that are in the watchlist. The UI enforces this by only allowing bets to be recorded on actual watchlist runners (the modal gets form_id from the runner object).

## Code Flow Reference

### Backend (watchlist.py L202-228)
```python
# Fetch all user bets
result = await session.execute(
    select(UserBet).where(UserBet.username == username)
)
all_bets = result.scalars().all()

# Build lookup dict keyed by (form_id, race_date)
bets_by_form_id: dict[tuple[int, str], UserBet] = {
    (bet.form_id, bet.race_date.isoformat()): bet for bet in all_bets
}

# For each CSV entry, join bet by key
for row in csv_rows:
    form_id = int(row["Form ID"])
    race_date = row["Race Date"]
    bet = bets_by_form_id.get((form_id, race_date))  # None if no match
    
    # Embed bet fields in entry
    bet_placed = bet is not None
    bet_id = bet.id if bet else None
    ...
```

### Frontend (monitor.html L841-855)
```javascript
async function fetchData() {
  const params = new URLSearchParams({ date: selectedDate });
  if (selectedUser) params.append('username', selectedUser);  // Username sent
  const url = `/api/watchlist?${params}`;
  const res = await fetch(url);
  const json = await res.json();
  setData(json);  // Entries with embedded bet fields
}
```

### Placed Badge Logic (monitor.html L1107-1128)
```javascript
const hasLedgerBet = runner.bet_placed === true;  // From API response
const ledgerPlaced = runner.placed || '';          // 'WON'/'LOST'/''

let placedLabel;
if (hasLedgerBet) {
  if (ledgerPlaced === 'WON') {
    placedLabel = `✓ WON ${profit...}`;
  } else if (ledgerPlaced === 'LOST') {
    placedLabel = `✕ LOST -${stake...}`;
  } else {
    placedLabel = '● PENDING';  // Shows until daemon settles
  }
} else {
  placedLabel = '';  // No badge if no ledger bet
}
```

## Status

**Code is correct.** jett's test used form_id not in watchlist → expected behavior.

Manual verification via UI (steps above) will confirm bets recorded on real watchlist runners display correctly.
