import logging
from datetime import date as Date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nitro_utils.database import get_db_session
from nitro_utils.models import TrackerUser, UserBet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["bets"])


def _check_bet_type(v: str) -> str:
    if v not in ("win", "place", "each_way"):
        raise ValueError("bet_type must be win, place, or each_way")
    return v


def _check_positive(v: float) -> float:
    if v <= 0:
        raise ValueError("must be positive")
    return v


class BetRequest(BaseModel):
    username: str
    race_id: int
    race_date: str
    form_id: int | None = None
    horse_name: str | None = None
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
        return _check_bet_type(v)

    @field_validator("odds_taken", "stake_aud")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        return _check_positive(v)

    def model_post_init(self, __context):
        if not self.form_id and not self.horse_name:
            raise ValueError("Either form_id or horse_name must be provided")


class BetResponse(BaseModel):
    status: str
    bet_id: int


class BetUpdateRequest(BaseModel):
    """Partial edit of a recorded bet: only the fields sent change.

    The values obey the same rules as when the bet is created.
    """

    bet_type: str | None = None
    odds_taken: float | None = None
    stake_aud: float | None = None

    @field_validator("bet_type")
    @classmethod
    def validate_bet_type(cls, v: str | None) -> str | None:
        return None if v is None else _check_bet_type(v)

    @field_validator("odds_taken", "stake_aud")
    @classmethod
    def validate_positive(cls, v: float | None) -> float | None:
        return None if v is None else _check_positive(v)

    @model_validator(mode="after")
    def validate_something_to_change(self) -> "BetUpdateRequest":
        if self.bet_type is None and self.odds_taken is None and self.stake_aud is None:
            raise ValueError("send at least one of bet_type, odds_taken, stake_aud")
        return self


class BetUpdateResponse(BaseModel):
    status: str
    bet_id: int
    bet_type: str
    odds_taken: float
    stake_aud: float
    profit_aud: float | None


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


def _bet_write_error(error: IntegrityError, duplicate_detail: str) -> HTTPException:
    """409 for the one-bet-per-runner-and-type rule, 500 for any other integrity error."""
    if "user_bets_dedup" in str(error):
        return HTTPException(status_code=409, detail=duplicate_detail)
    return HTTPException(status_code=500, detail=f"Database error: {error}")


async def _ensure_user_exists(session: AsyncSession, username: str) -> None:
    """Idempotent user creation (ON CONFLICT DO NOTHING)."""
    await session.execute(
        text("INSERT INTO tracker_users (username) VALUES (:username) ON CONFLICT (username) DO NOTHING"),
        {"username": username},
    )


@router.post("/bets", response_model=BetResponse)
async def create_bet(bet: BetRequest, session: AsyncSession = Depends(get_db_session)) -> BetResponse:
    race_date = Date.fromisoformat(bet.race_date)

    if bet.form_id:
        form_id = bet.form_id
    elif bet.horse_name:
        form_id = await _resolve_form_id(session, bet.horse_name, bet.race_id, race_date)
        if form_id is None:
            raise HTTPException(
                status_code=404,
                detail=f"Horse '{bet.horse_name}' not found in race {bet.race_id} on {bet.race_date}",
            )
    else:
        raise HTTPException(status_code=400, detail="Either form_id or horse_name must be provided")

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
        raise _bet_write_error(
            e,
            f"Bet already exists for {bet.username} on this runner with bet_type={bet.bet_type}",
        ) from e


@router.delete("/bets/{bet_id}")
async def delete_bet(bet_id: int, session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    result = await session.execute(delete(UserBet).where(UserBet.id == bet_id))
    await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Bet {bet_id} not found")

    logger.info("Deleted bet: id=%d", bet_id)
    return {"status": "ok"}


def _update_values(payload: BetUpdateRequest) -> dict[str, object]:
    """The columns an edit sets. Profit follows the stored payout inside the UPDATE itself."""
    values: dict[str, object] = {}
    if payload.bet_type is not None:
        values["bet_type"] = payload.bet_type
    if payload.odds_taken is not None:
        values["odds_taken"] = Decimal(str(payload.odds_taken))
    if payload.stake_aud is not None:
        stake = Decimal(str(payload.stake_aud))
        values["stake_aud"] = stake
        # A payout recorded by a concurrent PUT .../payout is read under the row lock the UPDATE
        # holds, so the profit can never be computed from a stale payout. No payout: unchanged.
        values["profit_aud"] = func.coalesce(UserBet.payout_aud - stake, UserBet.profit_aud)
    return values


@router.put("/bets/{bet_id}", response_model=BetUpdateResponse)
async def update_bet(
    bet_id: int, payload: BetUpdateRequest, session: AsyncSession = Depends(get_db_session)
) -> BetUpdateResponse:
    statement = (
        update(UserBet)
        .where(UserBet.id == bet_id)
        .values(**_update_values(payload), updated_at=text("now()"))
        .returning(UserBet.bet_type, UserBet.odds_taken, UserBet.stake_aud, UserBet.profit_aud)
    )
    try:
        row = (await session.execute(statement)).one_or_none()
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise _bet_write_error(
            e, f"Bet already exists on this runner with bet_type={payload.bet_type}"
        ) from e

    if row is None:
        raise HTTPException(status_code=404, detail=f"Bet {bet_id} not found")

    logger.info("Updated bet: id=%d fields=%s", bet_id, sorted(payload.model_fields_set))
    return BetUpdateResponse(
        status="ok",
        bet_id=bet_id,
        bet_type=row.bet_type,
        odds_taken=float(row.odds_taken),
        stake_aud=float(row.stake_aud),
        profit_aud=None if row.profit_aud is None else float(row.profit_aud),
    )


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
