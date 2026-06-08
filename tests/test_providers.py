from datetime import date

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

