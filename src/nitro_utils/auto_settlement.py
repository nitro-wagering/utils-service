"""Auto-settlement job for user bets.

Polls unsettled bets, joins race_entries for position, computes payout via settlement.py,
and updates user_bets with settlement data.

Run as k8s CronJob or background daemon.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from nitro_utils.config import settings
from nitro_utils.database import session_factory
from nitro_utils.models import UserBet
from nitro_utils.settlement import calculate_payout

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def settle_unsettled_bets(session: AsyncSession) -> tuple[int, int]:
    """
    Settle all unsettled bets with resulted races.

    Returns: (settled_count, error_count)
    """
    result = await session.execute(
        text("""
            SELECT
                ub.id AS bet_id,
                ub.username,
                ub.form_id,
                ub.race_date,
                ub.bet_type,
                ub.odds_taken,
                ub.stake_aud,
                re.position AS result_position,
                r.race_status,
                (
                    SELECT COUNT(*)
                    FROM race_entries re2
                    WHERE re2.race_id = r.race_id
                      AND re2.race_date = r.race_date
                      AND COALESCE((re2.bm_data->>'is_scratched')::boolean, false) = false
                ) AS field_size
            FROM user_bets ub
            JOIN race_entries re ON re.form_id = ub.form_id AND re.race_date = ub.race_date
            JOIN races r ON r.race_id = re.race_id AND r.race_date = re.race_date
            WHERE ub.settled_at IS NULL
              AND r.race_status = 'resulted'
              AND re.position IS NOT NULL
            ORDER BY ub.race_date ASC, ub.id ASC
        """)
    )

    rows = result.fetchall()

    if not rows:
        logger.info("No unsettled bets with resulted races found")
        return 0, 0

    logger.info("Found %d unsettled bets with results", len(rows))

    settled_count = 0
    error_count = 0

    for row in rows:
        try:
            bet_id = row.bet_id
            bet_type = row.bet_type
            odds_taken = float(row.odds_taken)
            stake_aud = float(row.stake_aud)
            position = row.result_position
            field_size = row.field_size

            payout = calculate_payout(
                bet_type=bet_type,
                odds=odds_taken,
                stake=stake_aud,
                position=position,
                field_size=field_size,
            )

            profit = payout - stake_aud

            await session.execute(
                update(UserBet)
                .where(UserBet.id == bet_id)
                .values(
                    result_position=position,
                    payout_aud=payout,
                    profit_aud=profit,
                    settled_at=datetime.now(timezone.utc),
                    updated_at=text("now()"),
                )
            )

            settled_count += 1

            logger.info(
                "Settled bet %d: username=%s form_id=%d position=%d payout=%.2f profit=%.2f",
                bet_id,
                row.username,
                row.form_id,
                position,
                payout,
                profit,
            )

        except Exception as e:
            error_count += 1
            logger.error(
                "Failed to settle bet %d: %s",
                bet_id,
                e,
                exc_info=True,
            )

    await session.commit()

    logger.info("Settlement complete: %d settled, %d errors", settled_count, error_count)
    return settled_count, error_count


async def run_settlement_job() -> None:
    """Run auto-settlement job once."""
    logger.info("Starting auto-settlement job")

    async with session_factory() as session:
        try:
            settled, errors = await settle_unsettled_bets(session)
            logger.info("Auto-settlement job complete: %d settled, %d errors", settled, errors)
        except Exception as e:
            logger.exception("Auto-settlement job failed")
            raise


def main() -> None:
    """Entry point for settlement job."""
    asyncio.run(run_settlement_job())


if __name__ == "__main__":
    main()
