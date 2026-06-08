from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class UnderlyingQuote:
    symbol: str
    spot: float
    mark: float | None
    timestamp: str
    source: str = "unknown"


@dataclass
class OptionContract:
    symbol: str
    underlying: str
    expiration: date
    strike: float
    right: str
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    iv: float | None = None
    contract_size: int = 100

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0 and self.ask >= self.bid:
            return (self.bid + self.ask) / 2
        return max(self.last, self.bid, self.ask, 0.0)


@dataclass
class StrikeLevel:
    strike: float
    cdf_below: float
    sigma_distance: float
    volcon_score: float
    total_oi: int
    total_volume: int
    call_oi: int
    put_oi: int
    call_volume: int
    put_volume: int
    abs_gamma_notional: float
    net_gamma_proxy: float
    iv: float
    tags: list[str] = field(default_factory=list)


@dataclass
class TickerAnalytics:
    symbol: str
    as_of: str
    selected_expiry: str
    dte_days: int
    spot: float
    implied_forward: float
    atm_iv: float
    expected_move: float
    gamma_regime: str
    source_mode: str
    freshness_status: str
    put_wall: StrikeLevel
    pin_strike: StrikeLevel
    call_wall: StrikeLevel
    levels: list[StrikeLevel]
    risk_flags: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

