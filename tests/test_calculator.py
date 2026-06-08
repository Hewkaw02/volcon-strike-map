from datetime import date

import pytest

from volcon.calculator import analyze_ticker, choose_nearest_expiry, estimate_cdf_below
from volcon.models import OptionContract, UnderlyingQuote


def contract(
    strike,
    right,
    *,
    oi,
    volume,
    gamma,
    iv=0.24,
    bid=1.0,
    ask=1.2,
):
    return OptionContract(
        symbol=f"XYZ260612{right[0].upper()}{int(strike * 1000):08d}",
        underlying="XYZ",
        expiration=date(2026, 6, 12),
        strike=float(strike),
        right=right,
        bid=bid,
        ask=ask,
        last=(bid + ask) / 2,
        volume=volume,
        open_interest=oi,
        delta=0.2 if right == "call" else -0.2,
        gamma=gamma,
        iv=iv,
    )


def test_choose_nearest_expiry_includes_same_day_expiry():
    expiries = [date(2026, 6, 7), date(2026, 6, 12), date(2026, 6, 8)]

    selected = choose_nearest_expiry(expiries, date(2026, 6, 8))

    assert selected == date(2026, 6, 8)


def test_estimate_cdf_below_is_near_half_for_atm_forward():
    cdf = estimate_cdf_below(forward=100, strike=100, iv=0.20, dte_days=30)

    assert 0.50 <= cdf <= 0.53


def test_analyze_ticker_finds_put_wall_pin_and_call_wall():
    quote = UnderlyingQuote(symbol="XYZ", spot=100.0, mark=100.0, timestamp="2026-06-08T22:30:00Z")
    options = [
        contract(95, "put", oi=4200, volume=900, gamma=0.07),
        contract(95, "call", oi=400, volume=80, gamma=0.02),
        contract(100, "put", oi=3600, volume=400, gamma=0.10, bid=2.0, ask=2.2),
        contract(100, "call", oi=3600, volume=450, gamma=0.10, bid=2.1, ask=2.3),
        contract(105, "put", oi=350, volume=90, gamma=0.02),
        contract(105, "call", oi=3900, volume=850, gamma=0.07),
    ]

    result = analyze_ticker("XYZ", quote, date(2026, 6, 12), options, as_of=date(2026, 6, 8))

    assert result.selected_expiry == "2026-06-12"
    assert result.dte_days == 4
    assert result.put_wall.strike == 95
    assert result.pin_strike.strike == 100
    assert result.call_wall.strike == 105
    assert result.levels[0].volcon_score >= result.levels[-1].volcon_score
    assert all(0 <= level.cdf_below <= 1 for level in result.levels)
    assert result.gamma_regime in {"positive", "negative", "mixed"}


def test_analyze_ticker_flags_zero_dte_risk():
    quote = UnderlyingQuote(symbol="XYZ", spot=100.0, mark=100.0, timestamp="2026-06-12T22:30:00Z")
    options = [
        contract(100, "put", oi=1000, volume=100, gamma=0.10),
        contract(100, "call", oi=1000, volume=100, gamma=0.10),
    ]

    result = analyze_ticker("XYZ", quote, date(2026, 6, 12), options, as_of=date(2026, 6, 12))

    assert result.dte_days == 0
    assert "zero_dte" in result.risk_flags


def test_analyze_ticker_requires_options_for_selected_expiry():
    quote = UnderlyingQuote(symbol="XYZ", spot=100.0, mark=100.0, timestamp="2026-06-08T22:30:00Z")

    with pytest.raises(ValueError, match="No option contracts"):
        analyze_ticker("XYZ", quote, date(2026, 6, 12), [], as_of=date(2026, 6, 8))

