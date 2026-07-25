"""Tests for settlement computation logic."""

from decimal import Decimal

import pytest

from nitro_utils.settlement import (
    BetSummary,
    au_place_terms,
    compute_payout,
    compute_profit,
    compute_roi_pct,
)


class TestAuPlaceTerms:
    def test_small_field_no_place(self) -> None:
        assert au_place_terms(4) == 2  # ≤7 → 2 places

    def test_medium_field_two_places(self) -> None:
        assert au_place_terms(6) == 2
        assert au_place_terms(7) == 2

    def test_large_field_three_places(self) -> None:
        assert au_place_terms(8) == 3
        assert au_place_terms(12) == 3


class TestComputePayout:
    def test_win_bet_first_place(self) -> None:
        payout = compute_payout("win", Decimal("5.50"), Decimal("10.00"), 1, field_size=10)
        assert payout == Decimal("55.00")

    def test_win_bet_second_place(self) -> None:
        payout = compute_payout("win", Decimal("5.50"), Decimal("10.00"), 2, field_size=10)
        assert payout == Decimal("0")

    def test_win_bet_unresulted(self) -> None:
        payout = compute_payout("win", Decimal("5.50"), Decimal("10.00"), None, field_size=10)
        assert payout == Decimal("0")

    def test_place_bet_first_place_large_field(self) -> None:
        payout = compute_payout(
            "place",
            Decimal("5.50"),
            Decimal("10.00"),
            1,
            field_size=10,
            place_odds_taken=Decimal("2.20"),
        )
        assert payout == Decimal("22.00")

    def test_place_bet_third_place_large_field(self) -> None:
        payout = compute_payout(
            "place",
            Decimal("5.50"),
            Decimal("10.00"),
            3,
            field_size=10,
            place_odds_taken=Decimal("2.20"),
        )
        assert payout == Decimal("22.00")

    def test_place_bet_third_place_small_field_loses(self) -> None:
        payout = compute_payout(
            "place",
            Decimal("5.50"),
            Decimal("10.00"),
            3,
            field_size=6,
            place_odds_taken=Decimal("2.20"),
        )
        assert payout == Decimal("0")

    def test_place_bet_fourth_place(self) -> None:
        payout = compute_payout(
            "place",
            Decimal("5.50"),
            Decimal("10.00"),
            4,
            field_size=10,
            place_odds_taken=Decimal("2.20"),
        )
        assert payout == Decimal("0")

    def test_place_bet_requires_place_odds(self) -> None:
        with pytest.raises(ValueError, match="place_odds_taken required"):
            compute_payout("place", Decimal("5.50"), Decimal("10.00"), 1, field_size=10)

    def test_each_way_bet_first_place_large_field(self) -> None:
        payout = compute_payout("each_way", Decimal("5.50"), Decimal("20.00"), 1, field_size=10)
        win_stake = Decimal("10.00")
        place_stake = Decimal("10.00")
        win_payout = win_stake * Decimal("5.50")
        place_odds = (Decimal("5.50") / 4) + Decimal("0.75")
        place_payout = place_stake * place_odds
        assert payout == win_payout + place_payout

    def test_each_way_bet_third_place_large_field(self) -> None:
        payout = compute_payout("each_way", Decimal("5.50"), Decimal("20.00"), 3, field_size=10)
        place_stake = Decimal("10.00")
        place_odds = (Decimal("5.50") / 4) + Decimal("0.75")
        place_payout = place_stake * place_odds
        assert payout == place_payout

    def test_each_way_bet_third_place_small_field_loses(self) -> None:
        payout = compute_payout("each_way", Decimal("5.50"), Decimal("20.00"), 3, field_size=6)
        assert payout == Decimal("0")

    def test_each_way_bet_fourth_place(self) -> None:
        payout = compute_payout("each_way", Decimal("5.50"), Decimal("20.00"), 4, field_size=10)
        assert payout == Decimal("0")


def test_compute_each_way_place_odds() -> None:
    from nitro_utils.settlement import _compute_each_way_place_odds

    assert _compute_each_way_place_odds(Decimal("5.50")) == Decimal("2.125")
    assert _compute_each_way_place_odds(Decimal("10.00")) == Decimal("3.25")


def test_compute_profit() -> None:
    assert compute_profit(Decimal("55.00"), Decimal("10.00")) == Decimal("45.00")
    assert compute_profit(Decimal("0"), Decimal("10.00")) == Decimal("-10.00")


def test_compute_roi_pct() -> None:
    assert compute_roi_pct(Decimal("45.00"), Decimal("10.00")) == Decimal("450.00")
    assert compute_roi_pct(Decimal("-10.00"), Decimal("10.00")) == Decimal("-100.00")
    assert compute_roi_pct(Decimal("0"), Decimal("0")) == Decimal("0")


class TestBetSummary:
    def test_empty_summary(self) -> None:
        summary = BetSummary()
        assert summary.total_bets == 0
        assert summary.total_stake_aud == Decimal(0)
        assert summary.total_payout_aud == Decimal(0)
        assert summary.total_profit_aud == Decimal(0)
        assert summary.roi_pct == Decimal(0)

    def test_add_winning_bet(self) -> None:
        summary = BetSummary()
        summary.add_bet(Decimal("10.00"), Decimal("55.00"))
        assert summary.total_bets == 1
        assert summary.total_stake_aud == Decimal("10.00")
        assert summary.total_payout_aud == Decimal("55.00")
        assert summary.total_profit_aud == Decimal("45.00")
        assert summary.roi_pct == Decimal("450.00")

    def test_add_losing_bet(self) -> None:
        summary = BetSummary()
        summary.add_bet(Decimal("10.00"), Decimal("0"))
        assert summary.total_bets == 1
        assert summary.total_stake_aud == Decimal("10.00")
        assert summary.total_payout_aud == Decimal("0")
        assert summary.total_profit_aud == Decimal("-10.00")
        assert summary.roi_pct == Decimal("-100.00")

    def test_multiple_bets(self) -> None:
        summary = BetSummary()
        summary.add_bet(Decimal("10.00"), Decimal("55.00"))
        summary.add_bet(Decimal("10.00"), Decimal("0"))
        summary.add_bet(Decimal("20.00"), Decimal("40.00"))

        assert summary.total_bets == 3
        assert summary.total_stake_aud == Decimal("40.00")
        assert summary.total_payout_aud == Decimal("95.00")
        assert summary.total_profit_aud == Decimal("55.00")
        assert summary.roi_pct == Decimal("137.50")

    def test_to_dict(self) -> None:
        summary = BetSummary()
        summary.add_bet(Decimal("10.00"), Decimal("55.00"))
        result = summary.to_dict()

        assert result == {
            "total_bets": 1,
            "total_stake_aud": 10.0,
            "total_payout_aud": 55.0,
            "total_profit_aud": 45.0,
            "roi_pct": 450.0,
        }
