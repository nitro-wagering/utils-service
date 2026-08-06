import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def fetch_live_odds(
    session: AsyncSession, race_date: date
) -> dict[tuple[int, int], dict[str, float | None]]:
    """Fetch latest odds per runner (race_id, horse_id) for given date.

    Returns dict[(race_id, horse_id)] -> {"fixed_win": float, "fixed_place": float}
    Uses DISTINCT ON (race_id, horse_id) ordered by polled_at DESC.
    """
    from sqlalchemy import TIMESTAMP, Column, Date, Integer, MetaData, Numeric, String, Table

    metadata = MetaData()
    odds_snapshots = Table(
        "odds_snapshots",
        metadata,
        Column("race_id", Integer),
        Column("race_date", Date),
        Column("horse_id", Integer),
        Column("source", String),
        Column("fixed_win", Numeric),
        Column("fixed_place", Numeric),
        Column("polled_at", TIMESTAMP),
    )

    # DISTINCT ON requires PostgreSQL-specific syntax
    stmt = (
        select(
            odds_snapshots.c.race_id,
            odds_snapshots.c.horse_id,
            odds_snapshots.c.fixed_win,
            odds_snapshots.c.fixed_place,
        )
        .where(odds_snapshots.c.race_date == race_date)
        .distinct(odds_snapshots.c.race_id, odds_snapshots.c.horse_id)
        .order_by(
            odds_snapshots.c.race_id,
            odds_snapshots.c.horse_id,
            odds_snapshots.c.polled_at.desc(),
        )
    )

    result = await session.execute(stmt)
    rows = result.all()

    odds_map: dict[tuple[int, int], dict[str, float | None]] = {}
    for row in rows:
        race_id = row.race_id
        horse_id = row.horse_id
        fixed_win = float(row.fixed_win) if row.fixed_win else None
        fixed_place = float(row.fixed_place) if row.fixed_place else None
        odds_map[(race_id, horse_id)] = {"fixed_win": fixed_win, "fixed_place": fixed_place}

    logger.info("Fetched live odds for %s: %d runners", race_date, len(odds_map))
    return odds_map


async def fetch_results(
    session: AsyncSession, race_date: date
) -> dict[tuple[int, int], dict[str, int | float | bool | None]]:
    """Fetch results (position, margin, is_scratched) per runner for given date.

    Returns dict[(race_id, form_id)] -> {"position": int, "margin": float, "is_scratched": bool}
    """
    from sqlalchemy import Boolean, Column, Date, Integer, MetaData, Numeric, Table

    metadata = MetaData()
    race_entries = Table(
        "race_entries",
        metadata,
        Column("race_id", Integer),
        Column("race_date", Date),
        Column("form_id", Integer),
        Column("horse_id", Integer),
        Column("position", Integer),
        Column("margin", Numeric),
        Column("is_scratched", Boolean),
    )

    stmt = select(
        race_entries.c.race_id,
        race_entries.c.form_id,
        race_entries.c.horse_id,
        race_entries.c.position,
        race_entries.c.margin,
        race_entries.c.is_scratched,
    ).where(race_entries.c.race_date == race_date)

    result = await session.execute(stmt)
    rows = result.all()

    results_map: dict[tuple[int, int], dict[str, int | float | bool | None]] = {}
    for row in rows:
        race_id = row.race_id
        form_id = row.form_id
        horse_id = row.horse_id
        position = row.position
        margin = float(row.margin) if row.margin else None
        is_scratched = bool(row.is_scratched) if row.is_scratched is not None else False
        results_map[(race_id, form_id)] = {
            "position": position,
            "margin": margin,
            "is_scratched": is_scratched,
            "horse_id": horse_id,
        }

    logger.info("Fetched results for %s: %d entries", race_date, len(results_map))
    return results_map


async def fetch_race_statuses(
    session: AsyncSession, race_date: date
) -> dict[int, str]:
    """Fetch race_status per race_id for given date.

    Returns dict[race_id] -> race_status ("resulted"/"open"/"interim")
    """
    from sqlalchemy import Column, Date, Integer, MetaData, String, Table

    metadata = MetaData()
    races = Table(
        "races",
        metadata,
        Column("race_id", Integer),
        Column("race_date", Date),
        Column("race_status", String),
    )

    stmt = select(races.c.race_id, races.c.race_status).where(
        races.c.race_date == race_date
    )

    result = await session.execute(stmt)
    rows = result.all()

    status_map = {row.race_id: row.race_status for row in rows}

    logger.info("Fetched race statuses for %s: %d races", race_date, len(status_map))
    return status_map
