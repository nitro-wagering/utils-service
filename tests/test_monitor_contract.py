import re
from pathlib import Path

from nitro_utils.api.watchlist_live import WatchlistEntry

_MONITOR = Path(__file__).parent.parent / "src" / "nitro_utils" / "templates" / "monitor.html"

# monitor.html reads each API row as `runner.<field>` (per-runner data) or `entry.<field>`
# (race-level data when it groups rows into races), then builds a view-model for its
# components that carries these extra names, also under `runner`. They are not
# WatchlistEntry fields. A new name must be classified here on purpose.
_VIEW_MODEL_ONLY = frozenset(
    {
        "accent",
        "classRank",
        "fairWin",
        "field_size",
        "hasUserBet",
        "horse_name",
        "jockey",
        "marketWin",
        "mlRank",
        "monitorBadge",
        "name",
        "no",
        "overlayPct",
        "reasons",
        "simPos",
        "stats",
        "userBetLabel",
        "verdict",
        "verdictBg",
        "verdictColor",
    }
)

# Entry fields monitor.html needs from the API for bets, results, the runner card and
# the race key it groups rows by.
_CORE_ENTRY_FIELDS = frozenset(
    {
        "race_id",
        "race_date",
        "horse",
        "win_pct",
        "class_rank",
        "market_place",
        "bet_id",
        "bet_type",
        "odds_taken",
        "stake_aud",
        "payout_aud",
        "profit_aud",
        "result_position",
    }
)


def _row_properties() -> set[str]:
    html = _MONITOR.read_text(encoding="utf-8")
    return set(re.findall(r"\b(?:runner|entry)\.([A-Za-z_][A-Za-z0-9_]*)", html))


def test_monitor_reads_only_watchlist_entry_fields_or_known_view_model_names() -> None:
    """A renamed or removed WatchlistEntry field that monitor.html still reads fails here."""
    unknown = _row_properties() - set(WatchlistEntry.model_fields) - _VIEW_MODEL_ONLY

    assert not unknown, (
        f"monitor.html reads runner./entry. {sorted(unknown)} but WatchlistEntry has no such "
        "field and it is not a listed view-model name"
    )


def test_monitor_still_reads_the_core_entry_fields() -> None:
    """Guards the scan above against matching nothing if the page's variable names change."""
    properties = _row_properties()

    assert _CORE_ENTRY_FIELDS <= properties
    assert _CORE_ENTRY_FIELDS <= set(WatchlistEntry.model_fields)


def test_view_model_allowlist_has_no_stale_names() -> None:
    """Names the page no longer uses must leave the allowlist so it cannot become a free pass."""
    stale = _VIEW_MODEL_ONLY - _row_properties()

    assert not stale, f"monitor.html no longer uses {sorted(stale)}; remove them from the list"
