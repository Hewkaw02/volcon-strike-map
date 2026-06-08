from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from volcon.calculator import analyze_ticker, choose_nearest_expiry
from volcon.providers import ProviderError, SampleProvider, TradierProvider


RISK_DISCLOSURES = [
    "This dashboard is analytics only and is not investment advice.",
    "Open interest is usually prior clearing data and does not prove fresh opening flow.",
    "Volume does not reveal opening versus closing flow without later OI comparison.",
    "Dealer gamma regime is a proxy estimated from public chain data, not an observed dealer book.",
    "Earnings, dividends, splits, borrow pressure, macro events, and breaking news can invalidate strike-based mean reversion.",
    "Market data may be delayed, stale, partial, or subject to provider license restrictions.",
    "Price overlay bars are near-live snapshots from scheduled updates, not tick-by-tick streaming data.",
    "Negative gamma regimes can turn walls into acceleration levels instead of support/resistance.",
]


REFERENCES = [
    {
        "label": "Tradier options chain endpoint",
        "url": "https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains",
    },
    {
        "label": "GitHub Pages custom workflows",
        "url": "https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages",
    },
    {
        "label": "Breeden-Litzenberger option-implied distribution",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2642349",
    },
]


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def select_provider():
    if os.environ.get("TRADIER_TOKEN"):
        return TradierProvider(), "tradier"
    return SampleProvider(), "sample_fallback"


def _chart_from_bars(label: str, interval: str, bars: list, source_mode: str) -> dict:
    freshness_status = "failed" if not bars else "sample" if source_mode == "sample_fallback" else "fresh"
    return {
        "label": label,
        "interval": interval,
        "source_mode": source_mode,
        "freshness_status": freshness_status,
        "latest_bar_time": bars[-1].time if bars else None,
        "bars": [asdict(bar) for bar in bars],
    }


def _empty_chart(label: str, interval: str, source_mode: str) -> dict:
    return {
        "label": label,
        "interval": interval,
        "source_mode": source_mode,
        "freshness_status": "failed",
        "latest_bar_time": None,
        "bars": [],
    }


def build_price_charts(provider, symbol: str, source_mode: str) -> dict:
    daily = provider.get_daily_history(symbol, days=20)
    intraday = provider.get_intraday_history(symbol, interval="5min")
    return {
        "daily": _chart_from_bars("Daily 20D", "daily", daily, source_mode),
        "intraday": _chart_from_bars("Intraday 5m", "5min", intraday, source_mode),
    }


def build_payload(config: dict) -> dict:
    timezone_name = config.get("timezone", "America/New_York")
    now = datetime.now(ZoneInfo(timezone_name))
    as_of = now.date()
    provider, source_mode = select_provider()
    tickers = []
    failures = []

    for symbol in config["tickers"]:
        try:
            quote = provider.get_quote(symbol)
            expiries = provider.get_expirations(symbol, as_of=as_of)
            expiry = choose_nearest_expiry(expiries, as_of)
            chain = provider.get_chain(symbol, expiry)
            analysis = analyze_ticker(
                symbol,
                quote,
                expiry,
                chain,
                as_of=as_of,
                source_mode=source_mode,
                freshness_status="fresh" if source_mode != "sample_fallback" else "sample",
                max_levels=int(config.get("max_levels_per_ticker", 15)),
            )
            if source_mode == "sample_fallback":
                analysis.risk_flags.append("sample_data")
                analysis.warnings.append("No TRADIER_TOKEN secret is configured; this ticker uses deterministic sample data.")
            try:
                analysis.price_charts = build_price_charts(provider, symbol, source_mode)
            except (ProviderError, ValueError, OSError) as exc:
                analysis.price_charts = {
                    "daily": _empty_chart("Daily 20D", "daily", source_mode),
                    "intraday": _empty_chart("Intraday 5m", "5min", source_mode),
                }
                analysis.risk_flags.append("price_chart_failed")
                analysis.warnings.append(f"Price chart data failed for {symbol}: {exc}")
            tickers.append(analysis.to_dict())
        except (ProviderError, ValueError, OSError) as exc:
            failures.append(
                {
                    "symbol": symbol,
                    "freshness_status": "failed",
                    "error": str(exc),
                }
            )

    freshness = "fresh" if source_mode != "sample_fallback" and not failures else "partial" if tickers else "sample"
    if source_mode == "sample_fallback":
        freshness = "sample"

    return {
        "schema_version": "1.0.0",
        "generated_at": now.isoformat(),
        "as_of": as_of.isoformat(),
        "timezone": timezone_name,
        "source_mode": source_mode,
        "freshness_status": freshness,
        "expiry_rule": config.get("expiry_rule", "nearest_non_expired"),
        "universe": config["tickers"],
        "tickers": tickers,
        "failures": failures,
        "methodology": {
            "forward": "ATM put-call parity proxy: F = K + call_mid - put_mid; falls back to spot if unavailable.",
            "cdf": "CDF below strike is estimated from Black-Scholes d2 under the option-implied distribution proxy.",
            "volcon_score": "Weighted score from normalized OI, volume, absolute gamma notional, and side imbalance.",
            "gamma_regime": "Proxy only: call gamma notional positive, put gamma notional negative.",
            "price_overlay": "Daily 20D and intraday 5-minute bars are overlaid with put wall, pin strike, call wall, spot, and expected-move band.",
            "publishing_policy": "Public output contains derived analytics, not full raw option-chain dumps.",
        },
        "risk_disclosures": RISK_DISCLOSURES,
        "references": REFERENCES,
    }


def write_payload(payload: dict, output: Path, archive_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")

    if archive_dir is not None:
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{payload['as_of']}.json"
        with archive_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate stock option VolCon analytics JSON.")
    parser.add_argument("--config", type=Path, default=Path("config/tickers.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/latest.json"))
    parser.add_argument("--archive-dir", type=Path, default=Path("public/data/history"))
    args = parser.parse_args()

    payload = build_payload(load_config(args.config))
    write_payload(payload, args.output, args.archive_dir)
    print(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "source_mode": payload["source_mode"],
                "freshness_status": payload["freshness_status"],
                "ticker_count": len(payload["tickers"]),
                "failure_count": len(payload["failures"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
