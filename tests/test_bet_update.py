"""PUT /api/watchlist/bets/{bet_id}: edit a recorded bet's type, odds taken or stake (NIT-1133)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from nitro_utils.api.bets import BetUpdateRequest, PayoutUpdateRequest, update_bet, update_payout
from nitro_utils.models import TrackerUser, UserBet
from tests.seed import seed_reference_rows

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

RACE_DATE = date(2026, 7, 26)


async def _seed_bet(
    session: AsyncSession,
    ident: int,
    *,
    bet_type: str = "win",
    odds: str = "3.00",
    stake: str = "20.00",
) -> int:
    """A recorded bet on its own runner, under the real race_entries foreign key."""
    await seed_reference_rows(session, RACE_DATE)
    await session.execute(
        text(
            "INSERT INTO horses (horse_id, name) VALUES (:id, :name) "
            "ON CONFLICT (horse_id) DO NOTHING"
        ),
        {"id": ident, "name": f"Update Horse {ident}"},
    )
    await session.execute(
        text(
            "INSERT INTO races (race_id, race_date, meeting_id, race_number, pf_data) "
            "VALUES (:id, :race_date, 1, 1, '{\"weight_type\": \"Handicap\"}') "
            "ON CONFLICT (race_id, race_date) DO NOTHING"
        ),
        {"id": ident, "race_date": RACE_DATE},
    )
    await session.execute(
        text(
            "INSERT INTO race_entries (form_id, race_id, race_date, horse_id, jockey_id, "
            "trainer_id, pf_data) VALUES (:id, :id, :race_date, :id, 1, 1, "
            "'{\"barrier\": 1}') ON CONFLICT (form_id, race_date) DO NOTHING"
        ),
        {"id": ident, "race_date": RACE_DATE},
    )
    session.add(TrackerUser(username="editor"))
    await session.flush()
    bet = UserBet(
        username="editor",
        form_id=ident,
        race_date=RACE_DATE,
        bet_type=bet_type,
        odds_taken=Decimal(odds),
        stake_aud=Decimal(stake),
    )
    session.add(bet)
    await session.flush()
    return bet.id


async def _stored(session: AsyncSession, bet_id: int) -> UserBet:
    session.expire_all()
    return (await session.execute(select(UserBet).where(UserBet.id == bet_id))).scalar_one()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "column", "expected"),
    [
        ("bet_type", "place", "bet_type", "place"),
        ("odds_taken", 4.5, "odds_taken", Decimal("4.50")),
        ("stake_aud", 35.0, "stake_aud", Decimal("35.00")),
    ],
)
async def test_updates_only_the_field_sent(
    async_session: AsyncSession, field: str, value: object, column: str, expected: object
) -> None:
    bet_id = await _seed_bet(async_session, 990101)

    response = await update_bet(bet_id, BetUpdateRequest(**{field: value}), async_session)

    stored = await _stored(async_session, bet_id)
    assert response.status == "ok"
    assert getattr(stored, column) == expected
    untouched = {"bet_type": "win", "odds_taken": Decimal("3.00"), "stake_aud": Decimal("20.00")}
    for other, original in untouched.items():
        if other != column:
            assert getattr(stored, other) == original


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_bet_is_404(async_session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as caught:
        await update_bet(987654321, BetUpdateRequest(stake_aud=10.0), async_session)

    assert caught.value.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_editing_the_stake_of_a_settled_bet_recomputes_profit(
    async_session: AsyncSession,
) -> None:
    bet_id = await _seed_bet(async_session, 990102)
    await update_payout(bet_id, PayoutUpdateRequest(payout_aud=60.0), async_session)

    response = await update_bet(bet_id, BetUpdateRequest(stake_aud=30.0), async_session)

    assert response.profit_aud == 30.0
    assert (await _stored(async_session, bet_id)).profit_aud == Decimal("30.00")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_changing_to_a_bet_type_already_recorded_for_the_runner_is_409(
    async_session: AsyncSession,
) -> None:
    bet_id = await _seed_bet(async_session, 990103)
    async_session.add(
        UserBet(
            username="editor",
            form_id=990103,
            race_date=RACE_DATE,
            bet_type="place",
            odds_taken=Decimal("2.00"),
            stake_aud=Decimal("5.00"),
        )
    )
    await async_session.flush()

    with pytest.raises(HTTPException) as caught:
        await update_bet(bet_id, BetUpdateRequest(bet_type="place"), async_session)

    assert caught.value.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"bet_type": "lay"},
        {"odds_taken": 0},
        {"stake_aud": -5},
    ],
    ids=["nothing-to-change", "bad-bet-type", "zero-odds", "negative-stake"],
)
def test_request_obeys_the_create_path_rules(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BetUpdateRequest(**body)


def test_route_is_registered_for_put() -> None:
    from nitro_utils.main import app

    methods = app.openapi()["paths"]["/api/watchlist/bets/{bet_id}"]
    assert "put" in methods
    assert "delete" in methods
