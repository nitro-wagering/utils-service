from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from nitro_utils.api import watchlist_live
from nitro_utils.main import app
from nitro_utils.s3_loader import WatchlistUnavailableError


@pytest.mark.asyncio
async def test_root_serves_the_utilities_landing_page() -> None:
    """GET / is the landing page (index.html) that links to the tools."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text
    assert "<title>Nitro Wagering — Utilities</title>" in response.text
    assert 'href="/monitor"' in response.text


@pytest.mark.asyncio
async def test_monitor_contains_tracker_api_calls() -> None:
    """The monitor page carries the betting tracker and calls its watchlist endpoints."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/monitor")

    assert response.status_code == 200
    content = response.text

    for endpoint in (
        "/api/watchlist/users",
        "/api/watchlist/bets",
        "/api/watchlist/download",
    ):
        assert endpoint in content, f"monitor page does not call {endpoint}"
    for function in ("recordBet", "downloadWatchlist"):
        assert function in content

    for removed in ("/api/watchlist/upload", "/api/watchlist/refresh", "uploadWatchlist"):
        assert removed not in content, f"monitor page still references {removed}"


@pytest.mark.asyncio
async def test_monitor_template_structure() -> None:
    """The monitor page is a single-page app mounted on #root."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/monitor")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Race Day Monitor — Nitro Wagering</title>" in response.text
    assert '<div id="root"></div>' in response.text


@pytest.mark.asyncio
async def test_watchlist_without_username_returns_empty_when_there_are_no_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/watchlist needs no username; no frozen predictions is an empty 200, not an error."""

    async def no_predictions(_target_date: date) -> list[dict[str, str]]:
        return []

    monkeypatch.setattr(watchlist_live, "load_frozen_watchlist", no_predictions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/watchlist")

    assert response.status_code == 200
    body = response.json()
    assert body["entry_count"] == 0
    assert body["entries"] == []
    assert "No data available" in body["message"]


@pytest.mark.asyncio
async def test_watchlist_is_503_when_the_predictions_store_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An S3 failure is an unavailable dependency (503), not an internal error (500)."""

    async def s3_down(_target_date: date) -> list[dict[str, str]]:
        raise WatchlistUnavailableError("S3 list_objects_v2 failed: InvalidAccessKeyId")

    monkeypatch.setattr(watchlist_live, "load_frozen_watchlist", s3_down)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/watchlist")

    assert response.status_code == 503
    assert response.json() == {"detail": "Watchlist predictions unavailable"}
