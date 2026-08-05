"""Read live paper bets from paper-monitor SQLite ledger."""

import logging
import sqlite3
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

LEDGER_BASE_PATH = Path("/ledger")


def fetch_paper_bets(target_date: date, race_ids: set[int]) -> dict[tuple[int, int], dict]:
    """Fetch live paper bets from SQLite ledger.

    Args:
        target_date: Date to read ledger for
        race_ids: Set of race_ids to filter by

    Returns:
        Dict keyed by (race_id, horse_id) with bet details:
        {
            (race_id, horse_id): {
                "win_placed": bool,
                "place_placed": bool,
                "win_result": str | None,  # "WON", "LOST", "PENDING"
                "place_result": str | None,
                "win_stake": float | None,
                "place_stake": float | None,
                "win_odds": float | None,
                "place_odds": float | None,
            }
        }
    """
    ledger_path = LEDGER_BASE_PATH / f"working_{target_date}"

    if not ledger_path.exists():
        logger.warning("Paper-bet ledger not found: %s", ledger_path)
        return {}

    try:
        conn = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Fetch bets for requested race_ids
        placeholders = ",".join("?" * len(race_ids))
        query = f"""
            SELECT race_id, horse_id, bet_type, result, stake, win_price, place_price
            FROM bets
            WHERE race_id IN ({placeholders})
        """
        cursor.execute(query, tuple(race_ids))
        rows = cursor.fetchall()
        conn.close()

        # Aggregate by (race_id, horse_id) — multiple rows if WIN + PLACE
        bets_by_runner: dict[tuple[int, int], dict] = {}
        for row in rows:
            key = (row["race_id"], row["horse_id"])
            if key not in bets_by_runner:
                bets_by_runner[key] = {
                    "win_placed": False,
                    "place_placed": False,
                    "win_result": None,
                    "place_result": None,
                    "win_stake": None,
                    "place_stake": None,
                    "win_odds": None,
                    "place_odds": None,
                }

            bet_type = row["bet_type"]
            if bet_type == "WIN":
                bets_by_runner[key]["win_placed"] = True
                bets_by_runner[key]["win_result"] = row["result"]
                bets_by_runner[key]["win_stake"] = row["stake"]
                bets_by_runner[key]["win_odds"] = row["win_price"]
            elif bet_type == "PLACE":
                bets_by_runner[key]["place_placed"] = True
                bets_by_runner[key]["place_result"] = row["result"]
                bets_by_runner[key]["place_stake"] = row["stake"]
                bets_by_runner[key]["place_odds"] = row["place_price"]

        logger.info(
            "Loaded %d paper bets from ledger %s", len(bets_by_runner), ledger_path
        )
        return bets_by_runner

    except sqlite3.Error as e:
        logger.exception("Failed to read paper-bet ledger %s", ledger_path)
        return {}
