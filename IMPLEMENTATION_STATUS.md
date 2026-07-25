# Utils-Service Persistence Layer — Implementation Status

**Task**: #75 — Implement persistence layer for manual betting tracker  
**Engineer**: remy-3  
**Date**: 2026-07-25

## ✅ Completed

### Database Layer
- [x] `database.py` — async session factory using nitro_common helpers
- [x] `models.py` — ORM models matching schema.hcl exactly:
  - `TrackerUser` (username PK, created_at, index)
  - `UserBet` (composite FK to race_entries, dedup constraint, all indexes)
- [x] Config — database_url + pool settings added to Settings

### API Endpoints — Bet CRUD
- [x] `POST /api/watchlist/bets` — Create bet with validation
  - Resolves horse_name → form_id via horses + race_entries JOIN
  - Auto-creates tracker_users entry (idempotent)
  - Enforces composite FK constraint (form_id, race_date) → race_entries
  - Handles duplicate bet constraint (409 on username + form_id + race_date + bet_type)
  - Validates bet_type ∈ {win, place, each_way}
  - Validates odds_taken > 0, stake_aud > 0
  - Returns bet_id on success

- [x] `DELETE /api/watchlist/bets/{bet_id}` — Delete bet
  - Returns 404 if bet not found
  - Cascade behavior: ON DELETE RESTRICT on race_entries FK (prevents deleting race_entries with bets)

- [x] `PUT /api/watchlist/bets/{bet_id}/payout` — Manual payout override
  - Recomputes profit_aud = payout_aud - stake_aud
  - Returns profit_aud + roi_pct
  - Validates payout_aud >= 0
  - Updates updated_at timestamp

### API Endpoints — User Management
- [x] `GET /api/watchlist/users` — List usernames
  - Ordered by created_at DESC (newest first)
  - Returns array of username strings

- [x] `POST /api/watchlist/users` — Create username
  - Idempotent (ON CONFLICT DO NOTHING)
  - Returns {status, username, created: bool}

### Tests
- [x] `tests/test_bets_api.py` — Comprehensive test coverage:
  - User creation (idempotent, listing)
  - Bet creation (success, duplicate constraint, horse not found)
  - Bet deletion
  - Payout update
  - Request validation (date format, bet_type, positive values)
- [x] `tests/conftest.py` — async session fixture with rollback

### Code Quality
- [x] Composite-PK discipline — all race_entries JOINs include (form_id, race_date)
- [x] Input validation — Pydantic field_validator for all user inputs
- [x] Error handling — IntegrityError → HTTP 409, not-found → HTTP 404
- [x] Logging — structured logs at INFO level for all mutations
- [x] No TODOs or stubs in shipped code

## ⏸️ Blocked / Deferred

### GET /api/watchlist Enhancement
**Status**: Blocked on upstream watchlist CSV generation

**Gap**: Current watchlist CSV (parsed by `_parse_watchlist_csv`) doesn't include:
- `race_id` (required for bet correlation)
- `race_date` (required for composite PK joins)
- `neds_event_id` (for deep links per contract)

**Contract requirement**: GET /watchlist should return entries with:
- User bet tracking fields (bet_placed, bet_type, odds_taken, stake_aud)
- Settlement fields (result_position, payout_aud, profit_aud, roi_pct)
- Summary aggregates (total_bets, total_stake_aud, total_payout_aud, roi_pct)
- Neds deep link (neds_url built from races.neds_event_id)

**Implementation plan** (once CSV updated):
```python
# Join user_bets on (form_id, race_date) WHERE username = :username
# Join races on (race_id, race_date) for neds_event_id
# Build neds_url: f"https://www.neds.com.au/racing/{track-slug}/{neds_event_id}"
# Aggregate summary stats from user_bets
```

### POST /api/watchlist/upload
**Status**: Blocked on same CSV gap

**Gap**: Upload handler parses Excel but can't persist bets without race_id + race_date from spreadsheet.

**Current state**: Parse-only (validates headers, logs parsed bets, returns imported_count=N but doesn't persist)

**Workaround considered**: Resolve track_name + race_number + brisbane_today() → race_id via DB query
- **Rejected**: Fragile (assumes same-day upload), breaks for historical bets, wrong for multi-day meets

**Recommended fix**: Update `build_watchlist_final.py` to include race_id + race_date in CSV output

### Auto-Settlement Background Job
**Status**: Not started (lower priority, awaits GET /watchlist completion)

**Requirements**:
```python
# SELECT from user_bets WHERE settled_at IS NULL (partial index optimized)
# JOIN race_entries ON (form_id, race_date) WHERE races.race_status = 'resulted'
# Compute payout via settlement.py (field_size + position → place terms)
# UPDATE user_bets SET result_position, payout_aud, profit_aud, settled_at
```

**Dependencies**:
- settlement.py (already complete, 17 tests passing)
- Needs cron/scheduler integration (k8s CronJob or daemon loop)

### Template Serving
**Status**: Not started

**Requirements**:
- Serve Iris's HTML template at GET /
- Template path: `src/nitro_utils/templates/watchlist.html` (already exists per handoff notes)
- FastAPI TemplateResponse with Jinja2

## 🚀 Ready to Ship (Partial)

### What Works Now
- Direct API bet creation: `POST /api/watchlist/bets` with race_id + race_date + horse_name
- User management: `GET /users`, `POST /users`
- Bet deletion: `DELETE /bets/{id}`
- Manual payout override: `PUT /bets/{id}/payout`

### Integration Path
Frontend can:
1. Call `GET /users` to populate username picker
2. Call `POST /bets` when user records bet (pass race_id from watchlist data source)
3. Call `PUT /bets/{id}/payout` for bookmaker-corrected payouts
4. Call `DELETE /bets/{id}` to remove mistaken bets

### Missing for Full Contract Compliance
- GET /watchlist username-filtered response with bet tracking fields
- POST /upload bulk import
- Auto-settlement job

## Next Steps

**Recommended**:
1. **Upstream fix** (assign to ada-2 or watchlist maintainer):
   - Update `build_watchlist_final.py` to include race_id, race_date, neds_event_id in CSV
   - Columns to add: `Race ID`, `Race Date`, `Neds Event ID`
   - Deploy watchlist refresh job with updated script

2. **Complete GET /watchlist** (remy-3, once CSV updated):
   - Parse new CSV columns
   - Join user_bets on (form_id, race_date)
   - Join races on (race_id, race_date) for neds_event_id
   - Build response per contract

3. **Complete POST /upload** (remy-3, depends on step 2):
   - Read race_id + race_date from uploaded Excel
   - Call bet creation logic (reuse from bets.py)

4. **Auto-settlement job** (remy-3 or new task):
   - Background worker polling unsettled bets
   - settlement.py integration

5. **Template serving** (iris or remy-3):
   - Serve HTML at GET /

## PR Readiness

**What to test**:
```bash
# Run test suite
cd /Volumes/Expansion/src/nitro-wagering/utils-service
pytest tests/test_bets_api.py -v

# Manual API testing (requires NITRO_DATABASE_URL set)
curl -X POST http://localhost:8000/api/watchlist/users \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser"}'

curl -X GET http://localhost:8000/api/watchlist/users

# Bet creation (requires valid race_id + race_date + horse in DB)
curl -X POST http://localhost:8000/api/watchlist/bets \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "race_id": 1356329,
    "race_date": "2026-07-25",
    "horse_name": "Ayasaki",
    "track_name": "Grafton",
    "race_number": 1,
    "bet_type": "win",
    "odds_taken": 5.50,
    "stake_aud": 10.00,
    "field_size": 10
  }'
```

**Pre-merge checklist**:
- [ ] All tests passing (`pytest tests/ -v`)
- [ ] No linting errors (`ruff check src/`)
- [ ] Type checking passes (`mypy src/`)
- [ ] Database migrations applied (schema.hcl already merged @ migrate ed641f0)
- [ ] NITRO_DATABASE_URL env var documented in deployment config
- [ ] Code review (Sage)
- [ ] QA validation (Maren)
