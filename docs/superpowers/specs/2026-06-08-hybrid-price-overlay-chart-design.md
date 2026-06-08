# Hybrid Price Overlay Chart Design

## Goal

Add a chart that compares the current price path directly against option-derived put wall, pin strike, call wall, and expected-move levels.

## Data Design

Each ticker analytics object will include `price_charts`:

- `daily`: 20 trading-day daily OHLC bars from Tradier `/v1/markets/history`, or deterministic sample bars when no `TRADIER_TOKEN` exists.
- `intraday`: current-session 5-minute OHLC bars from Tradier `/v1/markets/timesales`, or deterministic sample bars when no `TRADIER_TOKEN` exists.

The dashboard is still static GitHub Pages, so it is not true tick streaming. GitHub Actions refreshes the JSON periodically and the UI labels `latest_bar_time`, `generated_at`, and `freshness_status`.

## UI Design

Add a `Price Overlay Chart` panel above the existing strike level map. It has a segmented control for `Daily 20D` and `Intraday 5m`. The SVG chart renders:

- OHLC close path
- put wall, pin, and call wall horizontal lines
- current spot marker
- implied-forward expected-move band
- latest bar timestamp and freshness label

The chart must remain readable on mobile and must not expose provider tokens.

## Risk Notes

The UI must label the chart as near-live, not streaming. Intraday bars are only as fresh as the latest GitHub Actions/API update. Provider rate limits, market hours, delayed data, and stale bars must be visible in the chart metadata.

