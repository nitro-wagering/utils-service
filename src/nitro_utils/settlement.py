"""Auto-settlement computation logic for user bets.

Pure computation layer — testable with fixtures, no database dependency.
Schema layer (reading race results, updating user_bets) wires in separately.
"""

from decimal import Decimal
from typing import Literal

BetType = Literal["win", "place", "each_way"]


def au_place_terms(field_size: int) -> int:
    """Australian place dividend terms by field size.

    Args:
        field_size: Number of starters (non-scratched)

    Returns:
        Number of place positions paid (2 if ≤7, 3 if ≥8)
    """
    return 2 if field_size <= 7 else 3


def compute_payout(
    bet_type: BetType,
    odds_taken: Decimal,
    stake_aud: Decimal,
    result_position: int | None,
    field_size: int,
    place_odds_taken: Decimal | None = None,
) -> Decimal:
    """Compute payout for a bet given result position.

    Args:
        bet_type: "win", "place", or "each_way"
        odds_taken: Odds user recorded (win odds for win/each_way bets)
        stake_aud: Stake in AUD (e.g. 10.00)
        result_position: Finishing position (1, 2, 3, ...) or None if unresulted
        field_size: Number of starters (non-scratched) for place-terms determination
        place_odds_taken: For bet_type="place", the place odds user recorded (NOT derived)

    Returns:
        Total payout including stake (0 if lost, stake included if won)

    AU place-terms rules (field-size dependent):
    - 1-4 runners: win only (no place market, place bets invalid)
    - 5-7 runners: 1st-2nd pay
    - 8+ runners: 1st-3rd pay

    For bet_type="place": place_odds_taken IS the place price user recorded (not derived).
    For bet_type="each_way": place leg uses quarter-odds formula from win_odds.
    """
    if result_position is None:
        return Decimal(0)

    places_paid = au_place_terms(field_size)

    if bet_type == "win":
        if result_position == 1:
            return stake_aud * odds_taken
        return Decimal(0)

    if bet_type == "place":
        if place_odds_taken is None:
            raise ValueError("place_odds_taken required for bet_type='place'")
        if result_position <= places_paid:
            return stake_aud * place_odds_taken
        return Decimal(0)

    if bet_type == "each_way":
        win_stake = stake_aud / 2
        place_stake = stake_aud / 2

        win_payout = Decimal(0)
        if result_position == 1:
            win_payout = win_stake * odds_taken

        place_odds = _compute_each_way_place_odds(odds_taken)
        place_payout = Decimal(0)
        if result_position <= places_paid:
            place_payout = place_stake * place_odds

        return win_payout + place_payout

    raise ValueError(f"Invalid bet_type: {bet_type}")


def _compute_each_way_place_odds(win_odds: Decimal) -> Decimal:
    """Compute each-way place odds from win odds using AU quarter-odds terms.

    Formula: (win_odds / 4) + 0.75 = ((win_odds - 1) / 4) + 1
    Example: 5.50 win → (5.50 / 4) + 0.75 = 2.125 place

    NOTE: This applies ONLY to each-way bets. For bet_type="place", the user
    records the place odds directly (no derivation).
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
