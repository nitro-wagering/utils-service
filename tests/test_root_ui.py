import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("NITRO_DATABASE_URL", "postgresql://localhost/test")

from nitro_utils.main import app


@pytest.mark.asyncio
async def test_root_returns_html() -> None:
    """Test that GET / returns HTML with 200 status."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text
    assert "Betting Tracker" in response.text


@pytest.mark.asyncio
async def test_root_contains_api_calls() -> None:
    """Test that the HTML template contains the expected API endpoint references."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    content = response.text

    assert "const API_BASE = '/api'" in content
    assert "fetchWatchlist" in content
    assert "recordBet" in content
    assert "downloadWatchlist" in content
    assert "uploadWatchlist" in content


@pytest.mark.asyncio
async def test_root_template_structure() -> None:
    """Test that the template has the expected DOM structure."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    content = response.text

    assert '<title>Betting Tracker — Nitro Wagering</title>' in content
    assert 'id="refresh-btn"' in content
    assert 'id="download-btn"' in content
    assert 'id="upload-btn"' in content
    assert 'id="content"' in content


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
    from nitro_utils.api.watchlist import WatchlistEntry

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
async def test_api_default_username() -> None:
    """Test that GET /api/watchlist works without username parameter (defaults to 'kaity')."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/watchlist")

    assert response.status_code in (200, 503)  # 200 if CSV exists, 503 if unavailable
