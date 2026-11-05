import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("NITRO_DATABASE_URL", "postgresql://localhost/test")

from nitro_utils.main import app
from nitro_utils.s3_loader import WatchlistUnavailableError


@pytest.mark.asyncio
async def test_root_returns_utilities_landing_page() -> None:
    """GET / is the Utilities landing page linking to the Race Day Monitor."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text
    assert "<title>Nitro Wagering — Utilities</title>" in response.text
    assert 'href="/monitor"' in response.text


@pytest.mark.asyncio
async def test_monitor_page_has_betting_tracker_api_calls() -> None:
    """GET /monitor serves the Race Day Monitor, which carries the betting tracker."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/monitor")

    assert response.status_code == 200
    content = response.text
    assert "<title>Race Day Monitor — Nitro Wagering</title>" in content
    for function in ("recordBet", "downloadWatchlist", "uploadWatchlist"):
        assert f"function {function}(" in content
    for endpoint in (
        "/api/watchlist/bets",
        "/api/watchlist/download",
        "/api/watchlist/upload",
        "/api/watchlist/users",
    ):
        assert endpoint in content


def test_template_file_exists() -> None:
    """Test that the watchlist.html template file exists and is readable."""
    template_path = (
        Path(__file__).parent.parent / "src" / "nitro_utils" / "templates" / "watchlist.html"
    )
    assert template_path.exists()
    assert template_path.is_file()

    content = template_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Betting Tracker" in content


@pytest.mark.asyncio
async def test_template_schema_contract() -> None:
    """Test that template field references match WatchlistEntry/WatchlistResponse schema."""
    from nitro_utils.api.watchlist_live import WatchlistEntry

    template_path = (
        Path(__file__).parent.parent / "src" / "nitro_utils" / "templates" / "watchlist.html"
    )
    template_content = template_path.read_text(encoding="utf-8")

    # Fields that template JS actually references
    template_used_fields = [
        "track",
        "country",
        "race_number",
        "horse",
        "our_win",
        "win_pct",
        "neds_win",
        "race_id",
        "race_date",
    ]

    for field in template_used_fields:
        assert f"entry.{field}" in template_content, f"Template missing reference to entry.{field}"

    # Verify model has the fields template uses
    model_fields = set(WatchlistEntry.model_fields.keys())
    for field in template_used_fields:
        assert field in model_fields, f"WatchlistEntry missing field '{field}' used by template"


@pytest.mark.asyncio
async def test_api_watchlist_without_username_returns_503_when_predictions_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/watchlist works without a username; an unreachable S3 store is a 503."""

    async def unavailable(_target_date: object) -> list[dict[str, str]]:
        raise WatchlistUnavailableError("S3 list_objects_v2 failed: InvalidAccessKeyId")

    monkeypatch.setattr("nitro_utils.api.watchlist_live.load_frozen_watchlist", unavailable)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/watchlist")

    assert response.status_code == 503
    assert response.json() == {"detail": "Watchlist predictions unavailable"}


@pytest.mark.asyncio
async def test_api_watchlist_without_username_returns_empty_when_no_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No frozen watchlist for the day: 200 with an explanatory message."""

    async def no_artifact(_target_date: object) -> list[dict[str, str]]:
        return []

    monkeypatch.setattr("nitro_utils.api.watchlist_live.load_frozen_watchlist", no_artifact)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/watchlist", params={"date": "2026-11-05"})

    assert response.status_code == 200
    body = response.json()
    assert body["entry_count"] == 0
    assert body["message"] == "No data available for 2026-11-05"
