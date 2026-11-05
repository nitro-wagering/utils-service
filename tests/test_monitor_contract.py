import re
from pathlib import Path

from nitro_utils.api.watchlist_live import WatchlistEntry
from nitro_utils.main import app

_MONITOR = Path(__file__).parent.parent / "src" / "nitro_utils" / "templates" / "monitor.html"

# Every API call monitor.html makes must be a real route, and none is known to be unrouted.
# History: the Upload and Refresh buttons called POST /api/watchlist/upload and /refresh. Both
# routes lived in api/watchlist.py, which was mounted from the initial commit (674bfc4,
# 2026-07-25) until ce3496a (2026-08-04) switched the router to watchlist_live; the file was
# deleted in #31. monitor.html first called them on 2026-08-05 (#16), so the buttons never
# worked, and they were removed here. PUT /api/watchlist/bets/{id} was routed by #42.
# Add an entry only for a call that is deliberately unrouted; the test fails if an entry
# becomes stale.
_KNOWN_UNROUTED_CALLS: frozenset[tuple[str, str]] = frozenset()
_HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch"})
_API_LITERAL = re.compile(r"""(['"`])(/api/[^'"`\s]*)\1""")
_METHOD_OPTION = re.compile(r"""method:\s*['"]([A-Za-z]+)['"]""")

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


def _called_operations() -> set[tuple[str, str]]:
    """(METHOD, path) for every /api/ literal in monitor.html, with ${...} reduced to {}.

    The method is the first `method: '...'` option after the literal and before the next
    fetch(; with none it is a GET. The query string is dropped.
    """
    html = _MONITOR.read_text(encoding="utf-8")
    operations: set[tuple[str, str]] = set()
    for match in _API_LITERAL.finditer(html):
        path = re.sub(r"\$\{[^}]*\}", "{}", match.group(2).split("?")[0])
        window = html[match.end() : match.end() + 200].split("fetch(")[0]
        method_match = _METHOD_OPTION.search(window)
        method = method_match.group(1).upper() if method_match else "GET"
        operations.add((method, path))
    return operations


def _routed_operations() -> set[tuple[str, str]]:
    paths = app.openapi()["paths"]
    return {
        (method.upper(), re.sub(r"\{[^}]+\}", "{}", path))
        for path, item in paths.items()
        for method in item
        if method in _HTTP_METHODS
    }


def test_monitor_finds_its_api_calls() -> None:
    """Guards the route check against matching nothing if the page's fetch style changes."""
    called = _called_operations()

    assert len(called) >= 8
    assert ("GET", "/api/watchlist") in called
    assert ("PUT", "/api/watchlist/bets/{}/payout") in called
    assert ("DELETE", "/api/watchlist/bets/{}") in called


def test_every_api_call_in_monitor_is_a_real_route() -> None:
    """A call to a route the app does not serve is a dead button; only the known ones pass."""
    unrouted = _called_operations() - _routed_operations()

    assert unrouted == _KNOWN_UNROUTED_CALLS, (
        f"monitor.html calls routes the app does not serve: {sorted(unrouted)}; "
        f"expected exactly {sorted(_KNOWN_UNROUTED_CALLS)}. Fix the page or the list."
    )
