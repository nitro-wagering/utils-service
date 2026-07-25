import logging
from datetime import date as Date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nitro_utils.database import get_db_session
from nitro_utils.models import TrackerUser, UserBet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["bets"])


class BetRequest(BaseModel):
    username: str
    race_id: int
    race_date: str
    horse_name: str
    track_name: str
    race_number: int
    bet_type: str
    odds_taken: float
    stake_aud: float
    field_size: int

    @field_validator("race_date")
    @classmethod
    def validate_race_date(cls, v: str) -> str:
        try:
            Date.fromisoformat(v)
        except ValueError as e:
            raise ValueError("race_date must be ISO format (YYYY-MM-DD)") from e
        return v

    @field_validator("bet_type")
    @classmethod
    def validate_bet_type(cls, v: str) -> str:
        if v not in ("win", "place", "each_way"):
            raise ValueError("bet_type must be win, place, or each_way")
        return v

    @field_validator("odds_taken", "stake_aud")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("must be positive")
        return v


class BetResponse(BaseModel):
    status: str
    bet_id: int


class PayoutUpdateRequest(BaseModel):
    payout_aud: float

    @field_validator("payout_aud")
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("payout_aud cannot be negative")
        return v


class PayoutUpdateResponse(BaseModel):
    status: str
    profit_aud: float
    roi_pct: float


class UsersResponse(BaseModel):
    users: list[str]


class CreateUserRequest(BaseModel):
    username: str


class CreateUserResponse(BaseModel):
    status: str
    username: str
    created: bool


async def _resolve_form_id(
    session: AsyncSession, horse_name: str, race_id: int, race_date: Date
) -> int | None:
    """Resolve horse_name → form_id via horses + race_entries JOIN.

    Raises 409 if ambiguous (multiple matches) - caller must specify form_id directly.
    """
    result = await session.execute(
        text("""
            SELECT re.form_id
            FROM race_entries re
            JOIN horses h ON h.horse_id = re.horse_id
            WHERE LOWER(h.name) = LOWER(:horse_name)
              AND re.race_id = :race_id
              AND re.race_date = :race_date
        """),
        {"horse_name": horse_name, "race_id": race_id, "race_date": race_date},
    )
    rows = result.fetchall()

    if len(rows) == 0:
        return None
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail=f"Ambiguous horse name '{horse_name}' - {len(rows)} matches found. Specify form_id directly.",
        )
    return rows[0][0]


async def _ensure_user_exists(session: AsyncSession, username: str) -> None:
    """Idempotent user creation (ON CONFLICT DO NOTHING)."""
    await session.execute(
        text("INSERT INTO tracker_users (username) VALUES (:username) ON CONFLICT (username) DO NOTHING"),
        {"username": username},
    )


@router.post("/bets", response_model=BetResponse)
async def create_bet(bet: BetRequest, session: AsyncSession = Depends(get_db_session)) -> BetResponse:
    race_date = Date.fromisoformat(bet.race_date)

    form_id = await _resolve_form_id(session, bet.horse_name, bet.race_id, race_date)
    if form_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"Horse '{bet.horse_name}' not found in race {bet.race_id} on {bet.race_date}",
        )

    await _ensure_user_exists(session, bet.username)

    new_bet = UserBet(
        username=bet.username,
        form_id=form_id,
        race_date=race_date,
        bet_type=bet.bet_type,
        odds_taken=Decimal(str(bet.odds_taken)),
        stake_aud=Decimal(str(bet.stake_aud)),
    )

    try:
        session.add(new_bet)
        await session.commit()
        await session.refresh(new_bet)

        logger.info(
            "Created bet: id=%d username=%s form_id=%d race_date=%s type=%s odds=%s stake=%s",
            new_bet.id,
            bet.username,
            form_id,
            race_date,
            bet.bet_type,
            bet.odds_taken,
            bet.stake_aud,
        )

        return BetResponse(status="ok", bet_id=new_bet.id)

    except IntegrityError as e:
        await session.rollback()
        if "user_bets_dedup" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"Bet already exists for {bet.username} on this runner with bet_type={bet.bet_type}",
            )
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.delete("/bets/{bet_id}")
async def delete_bet(bet_id: int, session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    result = await session.execute(delete(UserBet).where(UserBet.id == bet_id))
    await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Bet {bet_id} not found")

    logger.info("Deleted bet: id=%d", bet_id)
    return {"status": "ok"}


@router.put("/bets/{bet_id}/payout", response_model=PayoutUpdateResponse)
async def update_payout(
    bet_id: int, payload: PayoutUpdateRequest, session: AsyncSession = Depends(get_db_session)
) -> PayoutUpdateResponse:
    result = await session.execute(select(UserBet).where(UserBet.id == bet_id))
    bet = result.scalar_one_or_none()

    if bet is None:
        raise HTTPException(status_code=404, detail=f"Bet {bet_id} not found")

    payout = Decimal(str(payload.payout_aud))
    profit = payout - bet.stake_aud
    roi_pct = (profit / bet.stake_aud) * 100 if bet.stake_aud > 0 else Decimal(0)

    await session.execute(
        update(UserBet)
        .where(UserBet.id == bet_id)
        .values(payout_aud=payout, profit_aud=profit, updated_at=text("now()"))
    )
    await session.commit()

    logger.info(
        "Updated payout: bet_id=%d payout=%s profit=%s roi=%s",
        bet_id,
        payout,
        profit,
        roi_pct,
    )

    return PayoutUpdateResponse(
        status="ok",
        profit_aud=float(profit),
        roi_pct=float(roi_pct),
    )


@router.get("/users", response_model=UsersResponse)
async def get_users(session: AsyncSession = Depends(get_db_session)) -> UsersResponse:
    result = await session.execute(select(TrackerUser.username).order_by(TrackerUser.created_at.desc()))
    usernames = [row[0] for row in result.fetchall()]
    return UsersResponse(users=usernames)


@router.post("/users", response_model=CreateUserResponse)
async def create_user(
    payload: CreateUserRequest, session: AsyncSession = Depends(get_db_session)
) -> CreateUserResponse:
    result = await session.execute(select(TrackerUser).where(TrackerUser.username == payload.username))
    existing = result.scalar_one_or_none()

    if existing:
        return CreateUserResponse(status="ok", username=payload.username, created=False)

    new_user = TrackerUser(username=payload.username)
    session.add(new_user)
    await session.commit()

    logger.info("Created tracker user: username=%s", payload.username)
    return CreateUserResponse(status="ok", username=payload.username, created=True)
