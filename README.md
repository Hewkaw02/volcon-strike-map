# VolCon Strike Map

Daily GitHub Pages dashboard for nearest-expiry stock and ETF options concentration. It computes option-derived strike zones from volume, open interest, CDF percentile, and a transparent gamma-regime proxy.

## What It Builds

- Static dashboard in `public/`
- Python analytics engine in `volcon/`
- Hybrid daily/intraday updater in `scripts/update_data.py`
- GitHub Actions workflow in `.github/workflows/pages.yml`
- Public derived JSON in `public/data/latest.json`
- Price overlay chart comparing bars with put wall, pin strike, call wall, spot, and expected-move band

The dashboard publishes derived analytics only. It does not expose API keys and does not dump full raw option-chain data.

## Data Source

Production mode uses Tradier when the repository secret `TRADIER_TOKEN` is configured. Without that secret, the updater uses deterministic sample data and the dashboard displays a visible sample-mode warning.

Set the secret after pushing the repo:

```text
Repository Settings -> Secrets and variables -> Actions -> New repository secret
Name: TRADIER_TOKEN
Value: your Tradier API token
```

The workflow can then be triggered manually from the Actions tab or left to run on schedule.

## Hybrid Update Rule

The workflow runs every 15 minutes during the broad U.S. cash-market window, plus a `22:30 UTC` Monday-Friday after-close snapshot. GitHub Actions schedules are not guaranteed to fire at the exact minute, so this is near-live public publishing, not tick-by-tick streaming.

For each ticker it chooses the nearest expiration date that is not earlier than the run date in `America/New_York`. The price overlay uses 20 daily bars and current-session 5-minute bars when the provider returns them.

Default universe:

```json
["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA"]
```

Edit `config/tickers.json` to change the universe.

## Methodology

- Forward proxy: `F = K + call_mid - put_mid` at the nearest strike with both call and put mids.
- CDF proxy: Black-Scholes `d2`, reported as `CDF below strike ~= N(-d2)`.
- Gamma notional: `gamma * open_interest * contract_size * spot^2 * 0.01`.
- VolCon score: normalized open interest, volume, absolute gamma notional, and side imbalance.
- Gamma regime: proxy only, with call gamma treated as positive and put gamma treated as negative.
- Price overlay: daily 20D and intraday 5-minute bars plotted against put wall, pin strike, call wall, current spot, and expected-move band.

## Risks

This is an analytics dashboard, not investment advice or an order-generation system.

- Open interest is usually prior clearing data and does not prove fresh opening flow.
- Volume alone does not reveal opening versus closing flow.
- Dealer gamma sign is estimated from public chain data and can be wrong.
- Earnings, dividends, splits, borrow pressure, macro events, and news can override strike-based mean reversion.
- Negative gamma regimes can turn walls into acceleration levels rather than support/resistance.
- Market data may be delayed, stale, partial, or subject to provider license restrictions.
- Near-live GitHub Pages output can lag provider data because Actions schedules queue and the static site must redeploy.
- Public redistribution rights depend on the provider contract; confirm your provider terms before publishing live data.

## Local Development

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\update_data.py
```

Serve the dashboard locally:

```powershell
.venv\Scripts\python.exe -m http.server 8000 --directory public
```

Open `http://localhost:8000`.
