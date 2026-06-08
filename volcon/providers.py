from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import OptionContract, PriceBar, UnderlyingQuote


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


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


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

    def get_daily_history(self, symbol: str, *, days: int = 20, end: date | None = None) -> list[PriceBar]:
        quote = self.get_quote(symbol)
        end_date = end or datetime.now(timezone.utc).date()
        bars: list[PriceBar] = []
        start_close = quote.spot * 0.965
        for index in range(days):
            day = end_date - timedelta(days=days - index - 1)
            trend = (quote.spot - start_close) * (index / max(days - 1, 1))
            wave = quote.spot * 0.006 * math.sin(index * 0.8)
            close = start_close + trend + wave
            if index == days - 1:
                close = quote.spot
            open_price = close * (1 - 0.002 * math.cos(index))
            high = max(open_price, close) * 1.006
            low = min(open_price, close) * 0.994
            bars.append(
                PriceBar(
                    symbol=symbol.upper(),
                    time=day.isoformat(),
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    volume=1_000_000 + index * 15_000,
                )
            )
        return bars

    def get_intraday_history(
        self,
        symbol: str,
        *,
        interval: str = "5min",
        as_of: datetime | None = None,
    ) -> list[PriceBar]:
        quote = self.get_quote(symbol)
        now = as_of or datetime.now(timezone.utc)
        bar_count = 78 if interval == "5min" else 26
        minutes = 5 if interval == "5min" else 15
        session_start = datetime.combine(now.date(), time(9, 30), tzinfo=now.tzinfo)
        bars: list[PriceBar] = []
        start_close = quote.spot * 0.985
        for index in range(bar_count):
            stamp = session_start + timedelta(minutes=index * minutes)
            trend = (quote.spot - start_close) * (index / max(bar_count - 1, 1))
            wave = quote.spot * 0.0025 * math.sin(index * 0.45)
            close = start_close + trend + wave
            if index == bar_count - 1:
                close = quote.spot
            open_price = close * (1 - 0.0008 * math.cos(index))
            high = max(open_price, close) * 1.0015
            low = min(open_price, close) * 0.9985
            bars.append(
                PriceBar(
                    symbol=symbol.upper(),
                    time=stamp.strftime("%Y-%m-%d %H:%M:%S"),
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    volume=100_000 + index * 1_250,
                )
            )
        return bars

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

    def get_daily_history(self, symbol: str, *, days: int = 20, end: date | None = None) -> list[PriceBar]:
        end_date = end or datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=max(days * 2, days + 10))
        payload = self._get_json(
            "/v1/markets/history",
            {
                "symbol": symbol.upper(),
                "interval": "daily",
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
        )
        return self.normalize_history_payload(payload, symbol.upper())[-days:]

    def get_intraday_history(
        self,
        symbol: str,
        *,
        interval: str = "5min",
        as_of: datetime | None = None,
    ) -> list[PriceBar]:
        now = as_of or datetime.now(timezone.utc)
        ny_now = now.astimezone(ZoneInfo("America/New_York")) if now.tzinfo else now.replace(tzinfo=ZoneInfo("America/New_York"))
        session_start = datetime.combine(ny_now.date(), time(9, 30))
        session_end = datetime.combine(ny_now.date(), time(16, 0))
        end_time = min(ny_now.replace(tzinfo=None), session_end)
        if end_time < session_start:
            end_time = session_start + timedelta(minutes=5)
        payload = self._get_json(
            "/v1/markets/timesales",
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "start": session_start.strftime("%Y-%m-%d %H:%M"),
                "end": end_time.strftime("%Y-%m-%d %H:%M"),
                "session_filter": "open",
            },
        )
        return self.normalize_timesales_payload(payload, symbol.upper())

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

    @staticmethod
    def normalize_history_payload(payload: dict, symbol: str) -> list[PriceBar]:
        days = _as_list(payload.get("history", {}).get("day"))
        return [
            PriceBar(
                symbol=symbol.upper(),
                time=str(raw.get("date")),
                open=_num(raw.get("open")),
                high=_num(raw.get("high")),
                low=_num(raw.get("low")),
                close=_num(raw.get("close")),
                volume=_int(raw.get("volume")),
            )
            for raw in days
        ]

    @staticmethod
    def normalize_timesales_payload(payload: dict, symbol: str) -> list[PriceBar]:
        rows = _as_list(payload.get("series", {}).get("data"))
        bars: list[PriceBar] = []
        for raw in rows:
            close = _num(raw.get("close"), _num(raw.get("price")))
            open_price = _num(raw.get("open"), close)
            high = _num(raw.get("high"), max(open_price, close))
            low = _num(raw.get("low"), min(open_price, close))
            bars.append(
                PriceBar(
                    symbol=symbol.upper(),
                    time=str(raw.get("time")),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=_int(raw.get("volume")),
                )
            )
        return bars
