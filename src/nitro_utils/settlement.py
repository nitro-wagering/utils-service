"""Auto-settlement computation logic for user bets.

Pure computation layer — testable with fixtures, no database dependency.
Schema layer (reading race results, updating user_bets) wires in separately.
"""

from decimal import Decimal
from typing import Literal

BetType = Literal["win", "place", "each_way"]


def compute_payout(
    bet_type: BetType,
    odds_taken: Decimal,
    stake_aud: Decimal,
    result_position: int | None,
) -> Decimal:
    """Compute payout for a bet given result position.

    Args:
        bet_type: "win", "place", or "each_way"
        odds_taken: Odds user recorded (e.g. 5.50)
        stake_aud: Stake in AUD (e.g. 10.00)
        result_position: Finishing position (1, 2, 3, ...) or None if unresulted

    Returns:
        Total payout including stake (0 if lost, stake included if won)

    AU place-terms rules (standard):
    - 1-4 runners: win only (no place market)
    - 5-7 runners: 1st-2nd pay, place odds = (win_odds / 4) + 0.75
    - 8+ runners: 1st-3rd pay, place odds = (win_odds / 4) + 0.75
    """
    if result_position is None:
        return Decimal(0)

    if bet_type == "win":
        if result_position == 1:
            return stake_aud * odds_taken
        return Decimal(0)

    if bet_type == "place":
        place_odds = _compute_place_odds(odds_taken)
        if result_position <= 3:
            return stake_aud * place_odds
        return Decimal(0)

    if bet_type == "each_way":
        win_stake = stake_aud / 2
        place_stake = stake_aud / 2

        win_payout = Decimal(0)
        if result_position == 1:
            win_payout = win_stake * odds_taken

        place_odds = _compute_place_odds(odds_taken)
        place_payout = Decimal(0)
        if result_position <= 3:
            place_payout = place_stake * place_odds

        return win_payout + place_payout

    raise ValueError(f"Invalid bet_type: {bet_type}")


def _compute_place_odds(win_odds: Decimal) -> Decimal:
    """Compute place odds from win odds using AU standard terms.

    Formula: (win_odds / 4) + 0.75
    Example: 5.50 win → (5.50 / 4) + 0.75 = 2.125 place
    """
    return (win_odds / Decimal(4)) + Decimal("0.75")


def compute_profit(payout_aud: Decimal, stake_aud: Decimal) -> Decimal:
    """Compute profit (can be negative for losses)."""
    return payout_aud - stake_aud


def compute_roi_pct(profit_aud: Decimal, stake_aud: Decimal) -> Decimal:
    """Compute ROI percentage."""
    if stake_aud == 0:
        return Decimal(0)
    return (profit_aud / stake_aud) * Decimal(100)


class BetSummary:
    """Summary aggregations for a collection of bets."""

    def __init__(self) -> None:
        self.total_bets = 0
        self.total_stake_aud = Decimal(0)
        self.total_payout_aud = Decimal(0)
        self.total_profit_aud = Decimal(0)

    def add_bet(self, stake_aud: Decimal, payout_aud: Decimal) -> None:
        """Add a bet to the summary."""
        self.total_bets += 1
        self.total_stake_aud += stake_aud
        self.total_payout_aud += payout_aud
        self.total_profit_aud += payout_aud - stake_aud

    @property
    def roi_pct(self) -> Decimal:
        """Overall ROI percentage."""
        if self.total_stake_aud == 0:
            return Decimal(0)
        return (self.total_profit_aud / self.total_stake_aud) * Decimal(100)

    def to_dict(self) -> dict:
        """Export as dict for JSON response."""
        return {
            "total_bets": self.total_bets,
            "total_stake_aud": float(self.total_stake_aud),
            "total_payout_aud": float(self.total_payout_aud),
            "total_profit_aud": float(self.total_profit_aud),
            "roi_pct": float(self.roi_pct),
        }
