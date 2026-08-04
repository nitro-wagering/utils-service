# Live Watchlist Endpoint — Implementation Summary

**Tasked by**: team-lead (Nyx)  
**Agent**: ada-2 (Python specialist)  
**Date**: 2026-08-04  
**Task**: Rearchitect `/api/watchlist` from stale CSV snapshot to live three-source composition

---

## What Was Built

### 1. **S3 Loader** (`src/nitro_utils/s3_loader.py`)
- Async loader for frozen prediction artifacts from S3 `ml-v3/watchlists/{YYYY-MM-DD}.csv`
- Uses boto3 wrapped with `asyncio.to_thread` for true async
- Returns empty list when artifact doesn't exist (no fabrication)
- Handles s3.awgmi.dev quirk: HEAD lies (ContentLength=0), uses list_objects_v2 for existence check

### 2. **Live DB Queries** (`src/nitro_utils/live_data.py`)
Three async queries fetching latest DB state per date:
- **`fetch_live_odds`**: odds_snapshots DISTINCT ON (race_id, horse_id) ordered by polled_at DESC
- **`fetch_results`**: race_entries.position + margin (actual_position, actual_margin)
- **`fetch_race_statuses`**: races.race_status ("resulted"/"open"/"interim")

All queries composite-key correct (race_id, race_date).

### 3. **Live Composition Endpoint** (`src/nitro_utils/api/watchlist_live.py`)
`GET /api/watchlist?date=YYYY-MM-DD` (default Brisbane today)

**Three-source composition per runner:**
1. **FROZEN predictions** (from S3 CSV):
   - Win %/Place %, ML Win %/ML Place %
   - Our Win/Our Place (fair prices)
   - WIN Trigger/PLACE Trigger
   - Class Rank/ML Win Rank/Sim Order/Sim Win Rank
   - Jockey/Weight/Barrier
   - Race Time/Name/Distance/Class/Track Condition
   - **in_monitor_net** — FROZEN verdict (monitor's actual BET decision at decision time)

2. **LIVE odds + results** (from Postgres):
   - market_win/market_place (current fixed odds)
   - market_rank (derived from live odds ordering)
   - actual_position/actual_margin (results)
   - race_status ("resulted"/"open"/"interim")

3. **RECOMPUTED overlays** (live market × frozen fair):
   - win_overlay_pct = ((live_win / frozen_fair_win) - 1) × 100
   - win_distance_to_trigger = ((live_win - frozen_trigger) / frozen_trigger) × 100
   - Same for place

**Paper bets**: DEFERRED (pluggable seam, returns null for now — awaiting Kaity's betting-model decision).

**Missing artifact**: Returns `{"entries": [], "entry_count": 0, "message": "No data available for {date}"}` (no fabrication).

### 4. **Brisbane Timezone Handling** (`src/nitro_utils/date_utils.py`)
Per NIT-531 pattern:
- `brisbane_today()`: current date in Brisbane timezone (UTC+10 AEST)
- `utc_today()`: current date in UTC
- Prevents race-date mismatches around midnight (14:00 UTC = 00:00 Brisbane)

### 5. **Deployment Cleanup** (`k8s/deployment.yaml`, `config.py`)
Removed CSV snapshot dependencies:
- Deleted `/shared` PVC volumeMount
- Deleted `NITRO_WATCHLIST_CSV_PATH` env var
- Removed `watchlist_csv_path` from Settings

Service now reads ONLY from S3 + live DB.

### 6. **Dependencies** (`pyproject.toml`)
Added `boto3>=1.35.0` for S3 access.

### 7. **S3 Configuration** (`config.py`)
Added settings for S3 access:
```python
s3_endpoint_url: str = "https://s3.awgmi.dev"
s3_access_key_id: str = ""
s3_secret_access_key: str = ""
s3_bucket: str = "nitro"
```

Credentials come from `nitro-shared-env` secret (already mounted via envFrom).

---

## Design Decisions (FINAL — per ada-1)

1. **FROZEN `in_monitor_net` verdict**: The monitor's BET decision is frozen at decision time. A runner can show `in_monitor_net=BET` while its live overlay has since gone negative — that divergence is correct and informative (shows market moved since decision).

2. **Composite-key correct**: All DB queries use (race_id, race_date) where applicable per NIT-367 partition migration.

3. **No fabrication on missing artifact**: Coverage limited to dates where builder ran (~2026-08-03+). Empty response for unmaterialized dates is correct behavior.

4. **Recompute overlays LIVE**: Market-dependent fields (overlay %, distance to trigger, market_rank) reflect CURRENT odds, not the frozen CSV's morning odds.

5. **Paper bets deferred**: Pluggable seam (function stub returning no bet data). Awaiting Kaity's betting-model decision before adding ledger mount or user_bets query.

---

## Coordination Points

### cascade-1 (SQL verification)
Requested finalized SQL for:
- Latest odds per runner (DISTINCT ON pattern)
- Results per runner (position, margin)
- Race statuses

**Status**: Wrote queries myself per composite-PK patterns, awaiting cascade's verification.

### iris-2 (Frontend contract)
Sent field list:
- actual_position/actual_margin/race_status for results view
- market_win/market_place/market_rank for live odds
- Recomputed overlays (win_overlay_pct, win_distance_to_trigger, etc.)
- Client-side derivation: won/placed from actual_position + race_status

**Status**: Awaiting field name confirmation.

---

## Lint Status

**ruff check**: 1 warning (B008 — FastAPI `Depends` in defaults, safe to ignore)

---

## Next Step: Verify by Execution

Per standing rule: "The monitor shipped blank once because reviews were source-reads."

**Before PR:**
1. Actually CALL the endpoint (locally or in-cluster)
2. Confirm it returns real composed data for 2026-08-03 (artifact exists — real jockeys, live odds, results)
3. Confirm clean empty response for a no-artifact date
4. Report executed evidence to team-lead

**Not done yet** — awaiting team-lead's go for local test or direct PR.

---

## Files Changed

### New files:
- `src/nitro_utils/s3_loader.py` (S3 artifact loader)
- `src/nitro_utils/live_data.py` (DB live queries)
- `src/nitro_utils/api/watchlist_live.py` (composition endpoint)
- `src/nitro_utils/date_utils.py` (Brisbane timezone helpers)

### Modified files:
- `pyproject.toml` (boto3 dependency)
- `src/nitro_utils/config.py` (S3 settings, removed watchlist_csv_path)
- `src/nitro_utils/api/__init__.py` (router swap: watchlist → watchlist_live)
- `k8s/deployment.yaml` (removed /shared PVC mount + NITRO_WATCHLIST_CSV_PATH)

### Unchanged (old CSV path kept for other endpoints):
- `src/nitro_utils/api/watchlist.py` (old CSV-based GET /watchlist, now unused — can be deleted after cutover confirmation)

---

## S3 Artifact Key

Confirmed from value-model-service builder:
```
s3://nitro/ml-v3/watchlists/{YYYY-MM-DD}.csv
```

Builder outputs to `/tmp/watchlist_{date}.csv` but jett uploaded 2026-08-03.csv to S3 per task brief.
