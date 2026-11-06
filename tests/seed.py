"""Reference rows the bet tests need under the real races/race_entries foreign keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession


async def seed_horses(session: AsyncSession, *horses: tuple[int, str]) -> None:
    """Horses by (horse_id, name). ``sex`` is generated from pf_data and NOT NULL, so supply it."""
    for horse_id, name in horses:
        await session.execute(
            text(
                "INSERT INTO horses (horse_id, name, pf_data) "
                "VALUES (:horse_id, :name, CAST(:pf_data AS jsonb)) "
                "ON CONFLICT (horse_id) DO NOTHING"
            ),
            {"horse_id": horse_id, "name": name, "pf_data": '{"sex": "Gelding"}'},
        )


async def seed_reference_rows(session: AsyncSession, race_date: date) -> None:
    """One track, meeting, jockey and trainer (all id 1) that races and race_entries point at."""
    await session.execute(
        text(
            "INSERT INTO tracks (track_id, pf_data) VALUES "
            '(1, \'{"name": "Test Track", "state": "QLD", "location_category": "M"}\') '
            "ON CONFLICT (track_id) DO NOTHING"
        )
    )
    await session.execute(
        text(
            "INSERT INTO meetings (meeting_id, meeting_date, track_id) "
            "VALUES (1, :race_date, 1) ON CONFLICT (meeting_id, meeting_date) DO NOTHING"
        ),
        {"race_date": race_date},
    )
    await session.execute(
        text("INSERT INTO jockeys (jockey_id) VALUES (1) ON CONFLICT (jockey_id) DO NOTHING")
    )
    await session.execute(
        text("INSERT INTO trainers (trainer_id) VALUES (1) ON CONFLICT (trainer_id) DO NOTHING")
    )
