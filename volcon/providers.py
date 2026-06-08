from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import OptionContract, UnderlyingQuote


def _num(value, default=0.0) -> float:
    if value in (None, ""):
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0) -> int:
    return int(round(_num(value, default)))


def _date(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


class ProviderError(RuntimeError):
    pass


class SampleProvider:
    source_mode = "sample_fallback"

    _spots = {
        "SPY": 600.0,
        "QQQ": 530.0,
        "IWM": 210.0,
        "AAPL": 200.0,
        "MSFT": 480.0,
        "NVDA": 145.0,
        "TSLA": 340.0,
    }

    def get_quote(self, symbol: str) -> UnderlyingQuote:
        spot = self._spots.get(symbol.upper(), 100.0)
        return UnderlyingQuote(
            symbol=symbol.upper(),
            spot=spot,
            mark=spot,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=self.source_mode,
        )

    def get_expirations(self, symbol: str, *, as_of: date | None = None) -> list[date]:
        start = as_of or datetime.now(timezone.utc).date()
        days_until_friday = (4 - start.weekday()) % 7
        first = start + timedelta(days=days_until_friday)
        return [first, first + timedelta(days=7), first + timedelta(days=14)]

    def get_chain(self, symbol: str, expiration: date) -> list[OptionContract]:
        quote = self.get_quote(symbol)
        spot = quote.spot
        step = self._strike_step(spot)
        center = round(spot / step) * step
        strikes = [center + step * offset for offset in range(-3, 4)]
        contracts: list[OptionContract] = []
        for strike in strikes:
            distance = abs(strike - center) / step
            base_oi = max(500, int(4200 - distance * 750))
            base_volume = max(80, int(900 - distance * 140))
            gamma = max(0.012, 0.10 - distance * 0.018)
            put_boost = 1.8 if strike < center else 0.55
            call_boost = 1.8 if strike > center else 0.55
            if strike == center:
                put_boost = call_boost = 1.25
            contracts.append(
                self._sample_contract(symbol, expiration, strike, "put", base_oi, base_volume, gamma, put_boost)
            )
            contracts.append(
                self._sample_contract(symbol, expiration, strike, "call", base_oi, base_volume, gamma, call_boost)
            )
        return contracts

    def _strike_step(self, spot: float) -> float:
        if spot >= 400:
            return 5.0
        if spot >= 100:
            return 2.5
        return 1.0

    def _sample_contract(
        self,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        base_oi: int,
        base_volume: int,
        gamma: float,
        boost: float,
    ) -> OptionContract:
        bid = max(0.05, abs(strike - self._spots.get(symbol.upper(), 100.0)) * 0.03 + 0.65)
        ask = bid + 0.12
        return OptionContract(
            symbol=f"{symbol.upper()}{expiration.strftime('%y%m%d')}{right[0].upper()}{int(strike * 1000):08d}",
            underlying=symbol.upper(),
            expiration=expiration,
            strike=float(strike),
            right=right,
            bid=round(bid, 2),
            ask=round(ask, 2),
            last=round((bid + ask) / 2, 2),
            volume=max(0, int(base_volume * boost)),
            open_interest=max(0, int(base_oi * boost)),
            delta=0.30 if right == "call" else -0.30,
            gamma=round(gamma, 5),
            theta=-0.05,
            vega=0.08,
            iv=0.24 + abs(strike - self._spots.get(symbol.upper(), 100.0)) / self._spots.get(symbol.upper(), 100.0) * 0.18,
        )


class TradierProvider:
    source_mode = "tradier"

    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        self.token = token or os.environ.get("TRADIER_TOKEN")
        self.base_url = (base_url or os.environ.get("TRADIER_BASE_URL") or "https://api.tradier.com").rstrip("/")
        if not self.token:
            raise ProviderError("TRADIER_TOKEN is required for TradierProvider")

    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"Tradier HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise ProviderError(f"Tradier request failed: {exc}") from exc

    def get_quote(self, symbol: str) -> UnderlyingQuote:
        payload = self._get_json("/v1/markets/quotes", {"symbols": symbol.upper()})
        quote = payload.get("quotes", {}).get("quote")
        if isinstance(quote, list):
            quote = quote[0] if quote else None
        if not quote:
            raise ProviderError(f"Tradier returned no quote for {symbol}")
        spot = _num(quote.get("mark"), _num(quote.get("last"), _num(quote.get("close"))))
        if spot <= 0:
            raise ProviderError(f"Tradier quote for {symbol} has no usable spot price")
        timestamp = quote.get("trade_date") or quote.get("quote_date") or datetime.now(timezone.utc).isoformat()
        return UnderlyingQuote(symbol=symbol.upper(), spot=spot, mark=spot, timestamp=str(timestamp), source=self.source_mode)

    def get_expirations(self, symbol: str, *, as_of: date | None = None) -> list[date]:
        payload = self._get_json(
            "/v1/markets/options/expirations",
            {"symbol": symbol.upper(), "includeAllRoots": "false", "strikes": "false"},
        )
        raw_dates = payload.get("expirations", {}).get("date", [])
        if isinstance(raw_dates, str):
            raw_dates = [raw_dates]
        expiries = sorted(_date(value) for value in raw_dates)
        if as_of:
            expiries = [expiry for expiry in expiries if expiry >= as_of]
        if not expiries:
            raise ProviderError(f"Tradier returned no non-expired expirations for {symbol}")
        return expiries

    def get_chain(self, symbol: str, expiration: date) -> list[OptionContract]:
        payload = self._get_json(
            "/v1/markets/options/chains",
            {"symbol": symbol.upper(), "expiration": expiration.isoformat(), "greeks": "true"},
        )
        raw_options = payload.get("options", {}).get("option", [])
        if isinstance(raw_options, dict):
            raw_options = [raw_options]
        return [self.normalize_option(raw, symbol.upper(), expiration) for raw in raw_options]

    @staticmethod
    def normalize_option(raw: dict, underlying: str, expiration: date) -> OptionContract:
        greeks = raw.get("greeks") or {}
        right = (raw.get("option_type") or raw.get("type") or "").lower()
        if right in {"c", "call"}:
            right = "call"
        elif right in {"p", "put"}:
            right = "put"
        else:
            symbol = str(raw.get("symbol", ""))
            right = "call" if "C" in symbol[-9:-8] else "put"
        iv = _num(
            greeks.get("mid_iv"),
            _num(greeks.get("smv_vol"), _num(greeks.get("iv"), _num(raw.get("iv"), 0.0))),
        )
        return OptionContract(
            symbol=str(raw.get("symbol", "")),
            underlying=str(raw.get("root_symbol") or underlying).upper(),
            expiration=_date(raw.get("expiration_date") or expiration),
            strike=_num(raw.get("strike")),
            right=right,
            bid=_num(raw.get("bid")),
            ask=_num(raw.get("ask")),
            last=_num(raw.get("last")),
            volume=_int(raw.get("volume")),
            open_interest=_int(raw.get("open_interest")),
            delta=_num(greeks.get("delta"), None),
            gamma=_num(greeks.get("gamma"), None),
            theta=_num(greeks.get("theta"), None),
            vega=_num(greeks.get("vega"), None),
            iv=iv if iv > 0 else None,
        )

