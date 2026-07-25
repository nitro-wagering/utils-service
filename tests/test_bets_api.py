import pytest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nitro_utils.models import TrackerUser, UserBet


@pytest.mark.asyncio
async def test_create_user(async_session: AsyncSession):
    """Test creating a new tracker user."""
    from nitro_utils.api.bets import create_user, CreateUserRequest

    request = CreateUserRequest(username="testuser1")
    response = await create_user(request, async_session)

    assert response.status == "ok"
    assert response.username == "testuser1"
    assert response.created is True

    result = await async_session.execute(
        select(TrackerUser).where(TrackerUser.username == "testuser1")
    )
    user = result.scalar_one()
    assert user.username == "testuser1"
    assert user.created_at is not None


@pytest.mark.asyncio
async def test_create_user_idempotent(async_session: AsyncSession):
    """Test creating same user twice is idempotent."""
    from nitro_utils.api.bets import create_user, CreateUserRequest

    request = CreateUserRequest(username="testuser2")

    response1 = await create_user(request, async_session)
    assert response1.created is True

    response2 = await create_user(request, async_session)
    assert response2.status == "ok"
    assert response2.created is False


@pytest.mark.asyncio
async def test_get_users(async_session: AsyncSession):
    """Test listing users ordered by created_at DESC."""
    from nitro_utils.api.bets import get_users, create_user, CreateUserRequest

    await create_user(CreateUserRequest(username="user1"), async_session)
    await create_user(CreateUserRequest(username="user2"), async_session)
    await create_user(CreateUserRequest(username="user3"), async_session)

    response = await get_users(async_session)

    assert len(response.users) >= 3
    assert "user1" in response.users
    assert "user2" in response.users
    assert "user3" in response.users


@pytest.mark.asyncio
async def test_create_bet_success(async_session: AsyncSession):
    """Test creating a bet with valid race_entry."""
    from nitro_utils.api.bets import create_bet, BetRequest

    test_race_date = date(2026, 7, 25)

    await async_session.execute(
        text("""
            INSERT INTO horses (horse_id, name)
            VALUES (999001, 'Test Horse')
            ON CONFLICT (horse_id) DO NOTHING
        """)
    )

    await async_session.execute(
        text("""
            INSERT INTO races (race_id, race_date, race_number, track_id, race_time)
            VALUES (999001, :race_date, 1, 1, '14:00:00')
            ON CONFLICT (race_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.execute(
        text("""
            INSERT INTO race_entries (form_id, race_id, race_date, horse_id, jockey_id, trainer_id)
            VALUES (999001, 999001, :race_date, 999001, 1, 1)
            ON CONFLICT (form_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.commit()

    request = BetRequest(
        username="testuser",
        race_id=999001,
        race_date=test_race_date.isoformat(),
        horse_name="Test Horse",
        track_name="Test Track",
        race_number=1,
        bet_type="win",
        odds_taken=5.50,
        stake_aud=10.00,
        field_size=10,
    )

    response = await create_bet(request, async_session)

    assert response.status == "ok"
    assert response.bet_id > 0

    result = await async_session.execute(select(UserBet).where(UserBet.id == response.bet_id))
    bet = result.scalar_one()

    assert bet.username == "testuser"
    assert bet.form_id == 999001
    assert bet.race_date == test_race_date
    assert bet.bet_type == "win"
    assert bet.odds_taken == Decimal("5.50")
    assert bet.stake_aud == Decimal("10.00")
    assert bet.result_position is None
    assert bet.payout_aud is None
    assert bet.settled_at is None


@pytest.mark.asyncio
async def test_create_bet_duplicate(async_session: AsyncSession):
    """Test duplicate bet constraint (username + form_id + race_date + bet_type)."""
    from nitro_utils.api.bets import create_bet, BetRequest
    from fastapi import HTTPException

    test_race_date = date(2026, 7, 25)

    await async_session.execute(
        text("""
            INSERT INTO horses (horse_id, name)
            VALUES (999002, 'Test Horse 2')
            ON CONFLICT (horse_id) DO NOTHING
        """)
    )

    await async_session.execute(
        text("""
            INSERT INTO races (race_id, race_date, race_number, track_id, race_time)
            VALUES (999002, :race_date, 2, 1, '14:30:00')
            ON CONFLICT (race_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.execute(
        text("""
            INSERT INTO race_entries (form_id, race_id, race_date, horse_id, jockey_id, trainer_id)
            VALUES (999002, 999002, :race_date, 999002, 1, 1)
            ON CONFLICT (form_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.commit()

    request = BetRequest(
        username="testuser",
        race_id=999002,
        race_date=test_race_date.isoformat(),
        horse_name="Test Horse 2",
        track_name="Test Track",
        race_number=2,
        bet_type="place",
        odds_taken=2.50,
        stake_aud=20.00,
        field_size=10,
    )

    await create_bet(request, async_session)

    with pytest.raises(HTTPException) as exc_info:
        await create_bet(request, async_session)

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_bet_horse_not_found(async_session: AsyncSession):
    """Test creating bet for non-existent horse returns 404."""
    from nitro_utils.api.bets import create_bet, BetRequest
    from fastapi import HTTPException

    request = BetRequest(
        username="testuser",
        race_id=999999,
        race_date="2026-07-25",
        horse_name="Nonexistent Horse",
        track_name="Test Track",
        race_number=1,
        bet_type="win",
        odds_taken=5.00,
        stake_aud=10.00,
        field_size=10,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_bet(request, async_session)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_bet(async_session: AsyncSession):
    """Test deleting a bet."""
    from nitro_utils.api.bets import create_bet, delete_bet, BetRequest

    test_race_date = date(2026, 7, 25)

    await async_session.execute(
        text("""
            INSERT INTO horses (horse_id, name)
            VALUES (999003, 'Test Horse 3')
            ON CONFLICT (horse_id) DO NOTHING
        """)
    )

    await async_session.execute(
        text("""
            INSERT INTO races (race_id, race_date, race_number, track_id, race_time)
            VALUES (999003, :race_date, 3, 1, '15:00:00')
            ON CONFLICT (race_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.execute(
        text("""
            INSERT INTO race_entries (form_id, race_id, race_date, horse_id, jockey_id, trainer_id)
            VALUES (999003, 999003, :race_date, 999003, 1, 1)
            ON CONFLICT (form_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.commit()

    request = BetRequest(
        username="testuser",
        race_id=999003,
        race_date=test_race_date.isoformat(),
        horse_name="Test Horse 3",
        track_name="Test Track",
        race_number=3,
        bet_type="each_way",
        odds_taken=10.00,
        stake_aud=5.00,
        field_size=10,
    )

    create_response = await create_bet(request, async_session)
    bet_id = create_response.bet_id

    delete_response = await delete_bet(bet_id, async_session)
    assert delete_response["status"] == "ok"

    result = await async_session.execute(select(UserBet).where(UserBet.id == bet_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_update_payout(async_session: AsyncSession):
    """Test manually updating bet payout."""
    from nitro_utils.api.bets import create_bet, update_payout, BetRequest, PayoutUpdateRequest

    test_race_date = date(2026, 7, 25)

    await async_session.execute(
        text("""
            INSERT INTO horses (horse_id, name)
            VALUES (999004, 'Test Horse 4')
            ON CONFLICT (horse_id) DO NOTHING
        """)
    )

    await async_session.execute(
        text("""
            INSERT INTO races (race_id, race_date, race_number, track_id, race_time)
            VALUES (999004, :race_date, 4, 1, '15:30:00')
            ON CONFLICT (race_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.execute(
        text("""
            INSERT INTO race_entries (form_id, race_id, race_date, horse_id, jockey_id, trainer_id)
            VALUES (999004, 999004, :race_date, 999004, 1, 1)
            ON CONFLICT (form_id, race_date) DO NOTHING
        """),
        {"race_date": test_race_date},
    )

    await async_session.commit()

    request = BetRequest(
        username="testuser",
        race_id=999004,
        race_date=test_race_date.isoformat(),
        horse_name="Test Horse 4",
        track_name="Test Track",
        race_number=4,
        bet_type="win",
        odds_taken=3.00,
        stake_aud=20.00,
        field_size=10,
    )

    create_response = await create_bet(request, async_session)
    bet_id = create_response.bet_id

    payout_request = PayoutUpdateRequest(payout_aud=60.00)
    payout_response = await update_payout(bet_id, payout_request, async_session)

    assert payout_response.status == "ok"
    assert payout_response.profit_aud == 40.00
    assert payout_response.roi_pct == 200.00

    result = await async_session.execute(select(UserBet).where(UserBet.id == bet_id))
    bet = result.scalar_one()

    assert bet.payout_aud == Decimal("60.00")
    assert bet.profit_aud == Decimal("40.00")


@pytest.mark.asyncio
async def test_bet_validation(async_session: AsyncSession):
    """Test bet request validation."""
    from nitro_utils.api.bets import BetRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        BetRequest(
            username="testuser",
            race_id=1,
            race_date="invalid-date",
            horse_name="Test",
            track_name="Test",
            race_number=1,
            bet_type="win",
            odds_taken=5.0,
            stake_aud=10.0,
            field_size=10,
        )

    with pytest.raises(ValidationError) as exc_info:
        BetRequest(
            username="testuser",
            race_id=1,
            race_date="2026-07-25",
            horse_name="Test",
            track_name="Test",
            race_number=1,
            bet_type="invalid_type",
            odds_taken=5.0,
            stake_aud=10.0,
            field_size=10,
        )

    with pytest.raises(ValidationError) as exc_info:
        BetRequest(
            username="testuser",
            race_id=1,
            race_date="2026-07-25",
            horse_name="Test",
            track_name="Test",
            race_number=1,
            bet_type="win",
            odds_taken=-5.0,
            stake_aud=10.0,
            field_size=10,
        )
