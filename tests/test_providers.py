from datetime import date, datetime, timezone

from volcon.providers import SampleProvider, TradierProvider


def test_sample_provider_returns_quote_expiries_and_chain():
    provider = SampleProvider()

    quote = provider.get_quote("SPY")
    expiries = provider.get_expirations("SPY", as_of=date(2026, 6, 8))
    chain = provider.get_chain("SPY", expiries[0])

    assert quote.symbol == "SPY"
    assert quote.spot > 0
    assert expiries[0] >= date(2026, 6, 8)
    assert {contract.right for contract in chain} == {"call", "put"}
    assert all(contract.open_interest >= 0 for contract in chain)


def test_tradier_provider_normalizes_option_payload_with_greeks():
    raw = {
        "symbol": "SPY260612C00600000",
        "root_symbol": "SPY",
        "expiration_date": "2026-06-12",
        "strike": 600,
        "option_type": "call",
        "bid": 1.25,
        "ask": 1.35,
        "last": 1.30,
        "volume": 120,
        "open_interest": 2400,
        "greeks": {
            "delta": 0.32,
            "gamma": 0.041,
            "theta": -0.10,
            "vega": 0.08,
            "mid_iv": 0.19,
        },
    }

    contract = TradierProvider.normalize_option(raw, "SPY", date(2026, 6, 12))

    assert contract.underlying == "SPY"
    assert contract.right == "call"
    assert contract.strike == 600
    assert contract.gamma == 0.041
    assert contract.iv == 0.19


def test_sample_provider_returns_daily_and_intraday_price_bars():
    provider = SampleProvider()

    daily = provider.get_daily_history("SPY", days=20)
    intraday = provider.get_intraday_history("SPY", interval="5min")

    assert len(daily) == 20
    assert len(intraday) >= 20
    assert daily[-1].close == provider.get_quote("SPY").spot
    assert intraday[-1].close == provider.get_quote("SPY").spot
    assert all(bar.high >= bar.low for bar in daily + intraday)


def test_tradier_provider_normalizes_daily_history_payload():
    payload = {
        "history": {
            "day": [
                {
                    "date": "2026-06-05",
                    "open": 590.0,
                    "high": 602.0,
                    "low": 588.0,
                    "close": 600.0,
                    "volume": 123456,
                }
            ]
        }
    }

    bars = TradierProvider.normalize_history_payload(payload, "SPY")

    assert bars[0].time == "2026-06-05"
    assert bars[0].close == 600.0
    assert bars[0].volume == 123456


def test_tradier_provider_normalizes_timesales_payload():
    payload = {
        "series": {
            "data": [
                {
                    "time": "2026-06-08 09:30:00",
                    "open": 599.0,
                    "high": 601.0,
                    "low": 598.5,
                    "close": 600.5,
                    "volume": 4567,
                }
            ],
            "symbol": "SPY",
        }
    }

    bars = TradierProvider.normalize_timesales_payload(payload, "SPY")

    assert bars[0].time == "2026-06-08 09:30:00"
    assert bars[0].close == 600.5
    assert bars[0].volume == 4567


def test_tradier_intraday_request_uses_new_york_session_time():
    class RecordingProvider(TradierProvider):
        def __init__(self):
            super().__init__(token="test-token", base_url="https://example.test")
            self.request = None

        def _get_json(self, path, params):
            self.request = (path, params)
            return {"series": {"data": []}}

    provider = RecordingProvider()

    provider.get_intraday_history("SPY", as_of=datetime(2026, 6, 8, 14, 45, tzinfo=timezone.utc))

    path, params = provider.request
    assert path == "/v1/markets/timesales"
    assert params["start"] == "2026-06-08 09:30"
    assert params["end"] == "2026-06-08 10:45"
