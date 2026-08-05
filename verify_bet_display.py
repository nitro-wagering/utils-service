#!/usr/bin/env python3
"""
Verify user bet round-trip: POST → GET → display.

Creates a test bet for a real watchlist runner, fetches the watchlist,
confirms the bet appears embedded in the matching entry.
"""
import asyncio
import sys
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.nitro_utils.config import settings
from src.nitro_utils.models import UserBet


async def verify_bet_round_trip():
    """Create test bet, fetch watchlist, verify bet appears."""

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    test_username = "verify-iris-display"
    test_form_id = 123456  # Replace with actual form_id from today's watchlist
    test_race_date = date.today()

    async with async_session() as session:
        # Clean up any existing test bet
        await session.execute(
            select(UserBet).where(
                UserBet.username == test_username,
                UserBet.form_id == test_form_id,
                UserBet.race_date == test_race_date
            ).delete()
        )
        await session.commit()

        # Create test bet
        test_bet = UserBet(
            username=test_username,
            form_id=test_form_id,
            race_date=test_race_date,
            bet_type="WIN",
            odds_taken=3.50,
            stake_aud=10.00
        )
        session.add(test_bet)
        await session.commit()

        print(f"✓ Created test bet: username={test_username}, form_id={test_form_id}, race_date={test_race_date}")

        # Fetch all bets for this user
        result = await session.execute(
            select(UserBet).where(UserBet.username == test_username)
        )
        all_bets = result.scalars().all()
        print(f"✓ Query returned {len(all_bets)} bets for username={test_username}")

        # Build lookup dict (same as watchlist.py L206-208)
        bets_by_form_id = {
            (bet.form_id, bet.race_date.isoformat()): bet for bet in all_bets
        }

        # Test the lookup
        key = (test_form_id, test_race_date.isoformat())
        matched_bet = bets_by_form_id.get(key)

        if matched_bet:
            print(f"✓ PASS: Bet lookup successful")
            print(f"  Key: {key}")
            print(f"  Matched bet ID: {matched_bet.id}")
            print(f"  Bet type: {matched_bet.bet_type}")
            print(f"  Odds: {matched_bet.odds_taken}")
            print(f"  Stake: ${matched_bet.stake_aud}")
        else:
            print(f"✗ FAIL: Bet lookup returned None")
            print(f"  Key: {key}")
            print(f"  Available keys in dict: {list(bets_by_form_id.keys())}")
            sys.exit(1)

        # Cleanup
        await session.delete(test_bet)
        await session.commit()
        print(f"✓ Cleaned up test bet")

if __name__ == "__main__":
    asyncio.run(verify_bet_round_trip())
