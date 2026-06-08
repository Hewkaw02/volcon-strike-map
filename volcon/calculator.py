from __future__ import annotations

import math
from datetime import date, datetime
from statistics import median

from .models import OptionContract, StrikeLevel, TickerAnalytics, UnderlyingQuote


def _to_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def choose_nearest_expiry(expiries: list[date | str], as_of: date | str) -> date:
    as_of_date = _to_date(as_of)
    normalized = sorted(_to_date(expiry) for expiry in expiries)
    candidates = [expiry for expiry in normalized if expiry >= as_of_date]
    if not candidates:
        raise ValueError("No non-expired option expirations are available")
    return candidates[0]


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def estimate_cdf_below(forward: float, strike: float, iv: float, dte_days: int) -> float:
    if forward <= 0 or strike <= 0:
        return 0.5
    sigma = max(iv, 0.0001)
    years = max(dte_days, 1) / 365.0
    denominator = sigma * math.sqrt(years)
    d2 = (math.log(forward / strike) - 0.5 * sigma * sigma * years) / denominator
    return min(max(normal_cdf(-d2), 0.0), 1.0)


def _sigma_distance(forward: float, strike: float, iv: float, dte_days: int) -> float:
    if forward <= 0 or strike <= 0:
        return 0.0
    years = max(dte_days, 1) / 365.0
    denominator = max(iv, 0.0001) * math.sqrt(years)
    return math.log(strike / forward) / denominator


def _mid_iv(contracts: list[OptionContract]) -> float:
    ivs = [contract.iv for contract in contracts if contract.iv and contract.iv > 0]
    return float(median(ivs)) if ivs else 0.30


def _pair_by_strike(options: list[OptionContract]) -> dict[float, dict[str, OptionContract]]:
    pairs: dict[float, dict[str, OptionContract]] = {}
    for contract in options:
        right = contract.right.lower()
        if right not in {"call", "put"}:
            continue
        pairs.setdefault(float(contract.strike), {})[right] = contract
    return pairs


def _estimate_forward(pairs: dict[float, dict[str, OptionContract]], spot: float) -> float:
    complete = [
        (abs(strike - spot), strike, row["call"].mid, row["put"].mid)
        for strike, row in pairs.items()
        if "call" in row and "put" in row and row["call"].mid > 0 and row["put"].mid > 0
    ]
    if not complete:
        return spot
    _, strike, call_mid, put_mid = min(complete, key=lambda item: item[0])
    forward = strike + call_mid - put_mid
    return forward if forward > 0 else spot


def _gamma_notional(contract: OptionContract | None, spot: float) -> float:
    if contract is None or not contract.gamma or contract.gamma <= 0:
        return 0.0
    return contract.gamma * contract.open_interest * contract.contract_size * spot * spot * 0.01


def _normalize(value: float, max_value: float) -> float:
    return value / max_value if max_value > 0 else 0.0


def _risk_warnings(risk_flags: list[str]) -> list[str]:
    warnings = [
        "Analytics only; not investment advice, trade execution, or risk management for live orders.",
        "Open interest is usually prior clearing data and does not prove fresh opening flow.",
        "Dealer gamma sign is estimated from public chain data and can be wrong.",
        "Earnings, dividends, splits, borrow pressure, macro events, and news can override strike-based mean reversion.",
        "Negative gamma regimes can turn walls into acceleration levels rather than rejection zones.",
    ]
    if "zero_dte" in risk_flags:
        warnings.append("Selected expiry is 0DTE; pinning and breakout behavior can change rapidly intraday.")
    return warnings


def analyze_ticker(
    symbol: str,
    quote: UnderlyingQuote,
    expiry: date | str,
    options: list[OptionContract],
    *,
    as_of: date | str,
    source_mode: str = "calculated",
    freshness_status: str = "fresh",
    max_levels: int = 15,
) -> TickerAnalytics:
    expiry_date = _to_date(expiry)
    as_of_date = _to_date(as_of)
    selected = [contract for contract in options if contract.expiration == expiry_date]
    if not selected:
        raise ValueError(f"No option contracts for {symbol} {expiry_date.isoformat()}")

    spot = float(quote.mark or quote.spot)
    dte_days = max((expiry_date - as_of_date).days, 0)
    pairs = _pair_by_strike(selected)
    if not pairs:
        raise ValueError(f"No call/put contracts for {symbol} {expiry_date.isoformat()}")

    implied_forward = _estimate_forward(pairs, spot)
    atm_iv = _mid_iv(selected)
    expected_move = implied_forward * atm_iv * math.sqrt(max(dte_days, 1) / 365.0)
    raw_levels = []

    for strike, row in pairs.items():
        call = row.get("call")
        put = row.get("put")
        contracts = [contract for contract in (call, put) if contract is not None]
        iv = _mid_iv(contracts) if contracts else atm_iv
        call_oi = call.open_interest if call else 0
        put_oi = put.open_interest if put else 0
        call_volume = call.volume if call else 0
        put_volume = put.volume if put else 0
        call_gamma = _gamma_notional(call, spot)
        put_gamma = _gamma_notional(put, spot)
        total_oi = call_oi + put_oi
        total_volume = call_volume + put_volume
        raw_levels.append(
            {
                "strike": strike,
                "cdf_below": estimate_cdf_below(implied_forward, strike, iv, dte_days),
                "sigma_distance": _sigma_distance(implied_forward, strike, iv, dte_days),
                "total_oi": total_oi,
                "total_volume": total_volume,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "call_volume": call_volume,
                "put_volume": put_volume,
                "call_gamma": call_gamma,
                "put_gamma": put_gamma,
                "abs_gamma_notional": abs(call_gamma) + abs(put_gamma),
                "net_gamma_proxy": call_gamma - put_gamma,
                "iv": iv,
            }
        )

    max_oi = max(level["total_oi"] for level in raw_levels)
    max_volume = max(level["total_volume"] for level in raw_levels)
    max_abs_gamma = max(level["abs_gamma_notional"] for level in raw_levels)

    levels: list[StrikeLevel] = []
    for level in raw_levels:
        side_oi_imbalance = abs(level["call_oi"] - level["put_oi"]) / max(level["total_oi"], 1)
        side_volume_imbalance = abs(level["call_volume"] - level["put_volume"]) / max(level["total_volume"], 1)
        score = 100.0 * (
            0.30 * _normalize(level["total_oi"], max_oi)
            + 0.15 * _normalize(level["total_volume"], max_volume)
            + 0.35 * _normalize(level["abs_gamma_notional"], max_abs_gamma)
            + 0.10 * side_oi_imbalance
            + 0.10 * side_volume_imbalance
        )
        tags: list[str] = []
        if level["cdf_below"] <= 0.25:
            tags.append("lower_tail")
        if level["cdf_below"] >= 0.75:
            tags.append("upper_tail")
        levels.append(
            StrikeLevel(
                strike=level["strike"],
                cdf_below=round(level["cdf_below"], 4),
                sigma_distance=round(level["sigma_distance"], 3),
                volcon_score=round(score, 2),
                total_oi=level["total_oi"],
                total_volume=level["total_volume"],
                call_oi=level["call_oi"],
                put_oi=level["put_oi"],
                call_volume=level["call_volume"],
                put_volume=level["put_volume"],
                abs_gamma_notional=round(level["abs_gamma_notional"], 2),
                net_gamma_proxy=round(level["net_gamma_proxy"], 2),
                iv=round(level["iv"], 4),
                tags=tags,
            )
        )

    levels_by_strike = {level.strike: level for level in levels}
    put_candidates = [level for level in raw_levels if level["strike"] < spot and level["put_oi"] > 0]
    call_candidates = [level for level in raw_levels if level["strike"] > spot and level["call_oi"] > 0]
    if not put_candidates:
        put_candidates = [level for level in raw_levels if level["strike"] <= spot and level["put_oi"] > 0]
    if not call_candidates:
        call_candidates = [level for level in raw_levels if level["strike"] >= spot and level["call_oi"] > 0]
    put_source = max(put_candidates or raw_levels, key=lambda level: (level["put_gamma"], level["put_oi"]))
    call_source = max(call_candidates or raw_levels, key=lambda level: (level["call_gamma"], level["call_oi"]))
    pin_source = max(raw_levels, key=lambda level: level["abs_gamma_notional"])

    put_wall = levels_by_strike[put_source["strike"]]
    call_wall = levels_by_strike[call_source["strike"]]
    pin_strike = levels_by_strike[pin_source["strike"]]
    put_wall.tags = sorted(set(put_wall.tags + ["put_wall", "support_candidate"]))
    call_wall.tags = sorted(set(call_wall.tags + ["call_wall", "resistance_candidate"]))
    pin_strike.tags = sorted(set(pin_strike.tags + ["pin_strike"]))

    net_gamma = sum(level.net_gamma_proxy for level in levels)
    abs_gamma = sum(level.abs_gamma_notional for level in levels)
    ratio = net_gamma / abs_gamma if abs_gamma else 0.0
    if ratio > 0.15:
        gamma_regime = "positive"
    elif ratio < -0.15:
        gamma_regime = "negative"
    else:
        gamma_regime = "mixed"

    risk_flags = ["dealer_gamma_proxy", "oi_lag"]
    if dte_days == 0:
        risk_flags.append("zero_dte")
    if gamma_regime == "negative":
        risk_flags.append("breakout_acceleration_risk")

    ordered_levels = sorted(levels, key=lambda level: level.volcon_score, reverse=True)[:max_levels]
    return TickerAnalytics(
        symbol=symbol,
        as_of=as_of_date.isoformat(),
        selected_expiry=expiry_date.isoformat(),
        dte_days=dte_days,
        spot=round(spot, 4),
        implied_forward=round(implied_forward, 4),
        atm_iv=round(atm_iv, 4),
        expected_move=round(expected_move, 4),
        gamma_regime=gamma_regime,
        source_mode=source_mode,
        freshness_status=freshness_status,
        put_wall=put_wall,
        pin_strike=pin_strike,
        call_wall=call_wall,
        levels=ordered_levels,
        risk_flags=risk_flags,
        warnings=_risk_warnings(risk_flags),
    )
