# Stock Options VolCon Dashboard Design

## Goal

Build a public GitHub Pages dashboard that updates daily and maps U.S. stock/ETF option concentration into actionable-but-non-advisory zones: put wall, call wall, pin strike, CDF percentile, VolCon score, and gamma regime proxy.

## Scope

The system is a static web app plus a scheduled data updater. GitHub Actions runs after the U.S. cash-market close, fetches the nearest non-expired option expiry for a configured ticker list, computes derived analytics, writes `public/data/latest.json`, archives the derived snapshot, and deploys the static site to GitHub Pages.

The first production data provider is Tradier because its options chain endpoint supports chain lookup by symbol/expiration and optional greeks. The design uses a provider adapter boundary so Polygon, ThetaData, ORATS, or a CSV loader can be added later without rewriting analytics.

## Data Policy

The public site must not expose API keys or raw full option-chain dumps. GitHub Actions reads provider secrets server-side and publishes only derived fields: selected expiry, freshness, top levels, aggregate scores, limited strike summaries, warnings, and risk notes. This reduces redistribution risk but does not replace the user's obligation to follow their market-data provider's terms.

If `TRADIER_TOKEN` is absent, the updater falls back to deterministic sample data. The dashboard must visibly label this state as sample/demo, not live market data.

## Expiry Rule

For each ticker, choose the nearest expiration date that is greater than or equal to the Action run date in the `America/New_York` timezone. The scheduled run is after market close, so same-day expiries may still appear on 0DTE run days; the dashboard labels DTE and warns when DTE is zero.

## Analytics

For each ticker and selected expiry:

- Use quote mark/last price as spot.
- Estimate implied forward from the nearest strike with both call and put mid prices: `F = K + call_mid - put_mid`. If that is unavailable, fall back to spot.
- Build strike rows by pairing calls and puts at each strike.
- Estimate strike CDF with `d2` and the normal CDF: `CDF below K ~= N(-d2)`, using strike-level IV where available and ATM IV fallback otherwise.
- Compute gamma notional as dollars per 1% spot move: `gamma * OI * contract_size * spot^2 * 0.01`.
- Compute VolCon score from normalized total OI, total volume, absolute gamma notional, and call/put imbalance.
- Tag top levels as put wall, call wall, pin strike, support candidate, resistance candidate, or breakout trigger candidate.
- Estimate gamma regime with a transparent proxy: call gamma notional positive, put gamma notional negative. Label the result as `positive`, `negative`, or `mixed`, with uncertainty notes.

## Risk Coverage

The dashboard must include persistent warnings:

- It is an analytics dashboard, not investment advice or an order-generation system.
- OI often reflects prior clearing data and does not prove new opening flow.
- Daily volume does not reveal opening vs closing without next-day OI change.
- Dealer gamma sign is estimated from public chain data and can be wrong.
- Earnings, dividends, splits, borrow pressure, macro events, and news can override strike-based mean reversion.
- Public data may be delayed, stale, partial, or subject to provider limits.
- Negative gamma regimes can turn walls into acceleration levels rather than mean-reversion zones.

## UI

The dashboard first screen is the actual operating surface, not a marketing landing page. It includes:

- Header with data source, latest run time, and freshness status.
- Ticker selector and compact ticker cards.
- Main level map showing spot, implied forward, expected move, put wall, pin strike, and call wall.
- Strike table with CDF, VolCon score, OI, volume, gamma notional, and tags.
- Risk panel explaining current warnings and invalidation logic.
- Methodology section with formulas and references.

The visual style is restrained and operational: high readability, dense but organized data, neutral background, clear semantic colors, no decorative hero page.

## Deployment

GitHub Actions uses a Pages custom workflow with `actions/configure-pages`, `actions/upload-pages-artifact`, and `actions/deploy-pages`. The workflow has `contents: write` permission so it can commit derived `latest.json` and archive snapshots back to the repository for continuity. It has `pages: write` and `id-token: write` for deployment.

## Success Criteria

- `pytest` passes for analytics and provider-normalization behavior.
- `python scripts/update_data.py` produces valid `public/data/latest.json` without secrets by using sample data.
- Static dashboard loads locally from a simple HTTP server and renders the generated data.
- GitHub repository is created, pushed, and Pages workflow is configured.
- The final response reports whether live provider automation is active or waiting for `TRADIER_TOKEN`.

