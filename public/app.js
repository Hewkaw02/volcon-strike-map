const state = {
  payload: null,
  selectedSymbol: null,
  chartMode: "daily",
};

const els = {
  freshnessBadge: document.querySelector("#freshnessBadge"),
  generatedAt: document.querySelector("#generatedAt"),
  globalNotice: document.querySelector("#globalNotice"),
  tickerTabs: document.querySelector("#tickerTabs"),
  summaryGrid: document.querySelector("#summaryGrid"),
  chartTabs: document.querySelector("#chartTabs"),
  chartSubtitle: document.querySelector("#chartSubtitle"),
  priceChart: document.querySelector("#priceChart"),
  levelSubtitle: document.querySelector("#levelSubtitle"),
  gammaBadge: document.querySelector("#gammaBadge"),
  levelMap: document.querySelector("#levelMap"),
  riskCount: document.querySelector("#riskCount"),
  riskList: document.querySelector("#riskList"),
  strikeRows: document.querySelector("#strikeRows"),
  methodologyList: document.querySelector("#methodologyList"),
  referenceList: document.querySelector("#referenceList"),
};

function formatNumber(value, maximumFractionDigits = 0) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits }).format(value ?? 0);
}

function formatPrice(value) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: value >= 100 ? 2 : 2,
    maximumFractionDigits: 2,
  }).format(value ?? 0);
}

function formatPercent(value) {
  return `${formatNumber((value ?? 0) * 100, 1)}%`;
}

function formatGamma(value) {
  const abs = Math.abs(value ?? 0);
  if (abs >= 1_000_000_000) return `$${formatNumber(value / 1_000_000_000, 2)}B`;
  if (abs >= 1_000_000) return `$${formatNumber(value / 1_000_000, 1)}M`;
  if (abs >= 1_000) return `$${formatNumber(value / 1_000, 1)}K`;
  return `$${formatNumber(value, 0)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function classForFreshness(status) {
  if (status === "fresh") return "badge badge-positive";
  if (status === "sample" || status === "partial") return "badge badge-warning";
  return "badge badge-negative";
}

function classForGamma(regime) {
  if (regime === "positive") return "badge badge-positive";
  if (regime === "negative") return "badge badge-negative";
  return "badge badge-neutral";
}

function selectedTicker() {
  return state.payload?.tickers.find((ticker) => ticker.symbol === state.selectedSymbol) ?? state.payload?.tickers[0];
}

function render() {
  const payload = state.payload;
  if (!payload) return;

  const ticker = selectedTicker();
  if (!state.selectedSymbol && ticker) state.selectedSymbol = ticker.symbol;

  els.freshnessBadge.textContent = payload.freshness_status.toUpperCase();
  els.freshnessBadge.className = classForFreshness(payload.freshness_status);
  els.generatedAt.textContent = `Generated ${new Date(payload.generated_at).toLocaleString()}`;

  if (payload.source_mode === "sample_fallback") {
    els.globalNotice.hidden = false;
    els.globalNotice.textContent =
      "Sample mode: TRADIER_TOKEN is not configured yet. GitHub Actions will switch to live provider data once the secret is added.";
  } else if (payload.failures?.length) {
    els.globalNotice.hidden = false;
    els.globalNotice.textContent = `${payload.failures.length} ticker(s) failed during the latest run. Review freshness before using these levels.`;
  } else {
    els.globalNotice.hidden = true;
  }

  renderTickerTabs(payload);
  renderTicker(ticker, payload);
  renderChartTabs();
  renderMethodology(payload);
}

function renderTickerTabs(payload) {
  els.tickerTabs.innerHTML = "";
  payload.tickers.forEach((ticker) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `ticker-tab${ticker.symbol === state.selectedSymbol ? " active" : ""}`;
    button.textContent = ticker.symbol;
    button.addEventListener("click", () => {
      state.selectedSymbol = ticker.symbol;
      render();
    });
    els.tickerTabs.appendChild(button);
  });
}

function renderTicker(ticker, payload) {
  if (!ticker) {
    els.summaryGrid.innerHTML = '<div class="empty-state">No ticker analytics are available.</div>';
    return;
  }

  els.summaryGrid.innerHTML = [
    metric("Spot", formatPrice(ticker.spot), "Current underlying mark"),
    metric("Forward", formatPrice(ticker.implied_forward), "Put-call parity proxy"),
    metric("Expiry", ticker.selected_expiry, `${ticker.dte_days} DTE`),
    metric("Expected Move", formatPrice(ticker.expected_move), `ATM IV ${formatPercent(ticker.atm_iv)}`),
    metric("Gamma", ticker.gamma_regime.toUpperCase(), "Dealer-book proxy"),
  ].join("");

  els.levelSubtitle.textContent = `${ticker.symbol} nearest expiry ${ticker.selected_expiry} | source ${payload.source_mode}`;
  els.gammaBadge.textContent = `${ticker.gamma_regime.toUpperCase()} GAMMA`;
  els.gammaBadge.className = classForGamma(ticker.gamma_regime);

  renderLevelMap(ticker);
  renderPriceChart(ticker);
  renderRisks(ticker, payload);
  renderRows(ticker);
}

function metric(label, value, detail) {
  return `
    <article class="metric">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${detail}</small>
    </article>
  `;
}

function renderLevelMap(ticker) {
  const strikes = ticker.levels.map((level) => level.strike);
  const minStrike = Math.min(...strikes, ticker.put_wall.strike, ticker.spot);
  const maxStrike = Math.max(...strikes, ticker.call_wall.strike, ticker.spot);
  const padding = Math.max((maxStrike - minStrike) * 0.08, 1);
  const min = minStrike - padding;
  const max = maxStrike + padding;
  const pct = (value) => {
    const ratio = (value - min) / Math.max(max - min, 1);
    return `${4 + Math.min(Math.max(ratio, 0), 1) * 92}%`;
  };

  els.levelMap.innerHTML = `
    <div class="axis"></div>
    <div class="range-fill" style="left:${pct(ticker.put_wall.strike)};width:calc(${pct(ticker.call_wall.strike)} - ${pct(ticker.put_wall.strike)})"></div>
    ${marker("support", "Put Wall", ticker.put_wall, pct(ticker.put_wall.strike))}
    ${marker("pin", "Pin", ticker.pin_strike, pct(ticker.pin_strike.strike))}
    ${marker("resistance", "Call Wall", ticker.call_wall, pct(ticker.call_wall.strike))}
    <div class="spot-marker" style="left:${pct(ticker.spot)}">Spot ${formatPrice(ticker.spot)}</div>
  `;
}

function marker(kind, label, level, left) {
  return `
    <div class="marker ${kind} marker-${kind}" style="left:${left}">
      <div class="marker-card">
        <span>${label}</span>
        <strong>${formatPrice(level.strike)}</strong>
        <small>CDF ${formatPercent(level.cdf_below)}</small>
        <small>Score ${formatNumber(level.volcon_score, 1)}</small>
      </div>
    </div>
  `;
}

function renderChartTabs() {
  els.chartTabs.querySelectorAll(".chart-tab").forEach((button) => {
    const active = button.dataset.chartMode === state.chartMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function renderPriceChart(ticker) {
  const chart = ticker.price_charts?.[state.chartMode] ?? ticker.price_charts?.daily;
  const bars = (chart?.bars ?? []).filter((bar) => Number.isFinite(Number(bar.close)));

  if (!bars.length) {
    els.chartSubtitle.textContent = `${ticker.symbol} ${state.chartMode} price bars unavailable`;
    els.priceChart.innerHTML = '<div class="empty-state">No price bars are available for this ticker.</div>';
    return;
  }

  const width = 900;
  const height = 420;
  const margin = { top: 24, right: 24, bottom: 42, left: 62 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const expectedLow = ticker.implied_forward - ticker.expected_move;
  const expectedHigh = ticker.implied_forward + ticker.expected_move;
  const priceValues = bars.flatMap((bar) => [
    Number(bar.low ?? bar.close),
    Number(bar.high ?? bar.close),
    Number(bar.close),
  ]);
  const overlayValues = [
    ticker.spot,
    ticker.put_wall.strike,
    ticker.pin_strike.strike,
    ticker.call_wall.strike,
    expectedLow,
    expectedHigh,
  ];
  const minValue = Math.min(...priceValues, ...overlayValues);
  const maxValue = Math.max(...priceValues, ...overlayValues);
  const padding = Math.max((maxValue - minValue) * 0.08, ticker.spot * 0.005, 0.5);
  const yMin = minValue - padding;
  const yMax = maxValue + padding;
  const x = (index) => margin.left + (bars.length === 1 ? innerWidth / 2 : (index / (bars.length - 1)) * innerWidth);
  const y = (value) => margin.top + ((yMax - value) / Math.max(yMax - yMin, 0.0001)) * innerHeight;
  const linePath = bars
    .map((bar, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(2)} ${y(Number(bar.close)).toFixed(2)}`)
    .join(" ");
  const gridValues = [yMin, (yMin + yMax) / 2, yMax];
  const startLabel = bars[0]?.time ?? "";
  const endLabel = bars[bars.length - 1]?.time ?? "";
  const closeX = x(bars.length - 1);
  const spotY = y(ticker.spot);
  const whiskerEvery = state.chartMode === "intraday" ? 3 : 1;

  const grid = gridValues
    .map(
      (value) => `
        <g class="chart-grid">
          <line x1="${margin.left}" y1="${y(value).toFixed(2)}" x2="${width - margin.right}" y2="${y(value).toFixed(2)}"></line>
          <text x="${margin.left - 10}" y="${(y(value) + 4).toFixed(2)}">${formatPrice(value)}</text>
        </g>
      `
    )
    .join("");

  const candles = bars
    .map((bar, index) => {
      if (index % whiskerEvery !== 0 && index !== bars.length - 1) return "";
      const xValue = x(index);
      const highY = y(Number(bar.high ?? bar.close));
      const lowY = y(Number(bar.low ?? bar.close));
      const closeYValue = y(Number(bar.close));
      return `
        <g class="chart-candle">
          <line x1="${xValue.toFixed(2)}" y1="${highY.toFixed(2)}" x2="${xValue.toFixed(2)}" y2="${lowY.toFixed(2)}"></line>
          <line x1="${(xValue - 3).toFixed(2)}" y1="${closeYValue.toFixed(2)}" x2="${(xValue + 3).toFixed(2)}" y2="${closeYValue.toFixed(2)}"></line>
        </g>
      `;
    })
    .join("");

  els.chartSubtitle.textContent = `${ticker.symbol} ${chart.label ?? state.chartMode} | latest ${chart.latest_bar_time ?? endLabel} | ${chart.freshness_status ?? ticker.freshness_status}`;
  els.priceChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(ticker.symbol)} price overlay chart">
      ${grid}
      <rect
        class="expected-band"
        x="${margin.left}"
        y="${y(expectedHigh).toFixed(2)}"
        width="${innerWidth}"
        height="${Math.max(y(expectedLow) - y(expectedHigh), 2).toFixed(2)}"
      ></rect>
      ${levelLine("support", "Put Wall", ticker.put_wall.strike, y, margin, width)}
      ${levelLine("pin", "Pin", ticker.pin_strike.strike, y, margin, width)}
      ${levelLine("resistance", "Call Wall", ticker.call_wall.strike, y, margin, width)}
      ${candles}
      <path class="chart-price-line" d="${linePath}"></path>
      <g class="chart-spot">
        <line x1="${margin.left}" y1="${spotY.toFixed(2)}" x2="${width - margin.right}" y2="${spotY.toFixed(2)}"></line>
        <circle cx="${closeX.toFixed(2)}" cy="${spotY.toFixed(2)}" r="5"></circle>
        <text x="${Math.max(margin.left + 86, closeX - 8).toFixed(2)}" y="${(spotY - 12).toFixed(2)}" text-anchor="end">Spot ${formatPrice(ticker.spot)}</text>
      </g>
      <g class="chart-axis-labels">
        <text x="${margin.left}" y="${height - 12}">${escapeHtml(compactTimeLabel(startLabel))}</text>
        <text x="${width - margin.right}" y="${height - 12}" text-anchor="end">${escapeHtml(compactTimeLabel(endLabel))}</text>
      </g>
    </svg>
  `;
}

function levelLine(kind, label, value, y, margin, width) {
  const yValue = y(value);
  return `
    <g class="chart-level chart-${kind}">
      <line x1="${margin.left}" y1="${yValue.toFixed(2)}" x2="${width - margin.right}" y2="${yValue.toFixed(2)}"></line>
      <text x="${width - margin.right - 6}" y="${(yValue - 6).toFixed(2)}" text-anchor="end">${label} ${formatPrice(value)}</text>
    </g>
  `;
}

function compactTimeLabel(value) {
  if (!value) return "";
  if (state.chartMode === "daily") return String(value).slice(0, 10);
  return String(value).replace("T", " ").slice(11, 16) || String(value);
}

function renderRisks(ticker, payload) {
  const warnings = [...new Set([...(ticker.warnings ?? []), ...(payload.risk_disclosures ?? [])])].slice(0, 9);
  els.riskCount.textContent = `${ticker.risk_flags.length} flags`;
  els.riskList.innerHTML = warnings.map((warning) => `<li>${warning}</li>`).join("");
}

function renderRows(ticker) {
  els.strikeRows.innerHTML = ticker.levels
    .map(
      (level) => `
        <tr>
          <td><strong>${formatPrice(level.strike)}</strong></td>
          <td>${formatPercent(level.cdf_below)}</td>
          <td>
            <div class="score-cell">
              <span>${formatNumber(level.volcon_score, 1)}</span>
              <div class="score-bar"><span style="width:${Math.min(level.volcon_score, 100)}%"></span></div>
            </div>
          </td>
          <td>${formatNumber(level.total_oi)}</td>
          <td>${formatNumber(level.total_volume)}</td>
          <td>${formatGamma(level.abs_gamma_notional)}</td>
          <td><div class="tag-list">${renderTags(level.tags)}</div></td>
        </tr>
      `
    )
    .join("");
}

function renderTags(tags) {
  if (!tags?.length) return '<span class="tag">neutral</span>';
  return tags.map((tag) => `<span class="tag ${tag}">${tag.replaceAll("_", " ")}</span>`).join("");
}

function renderMethodology(payload) {
  els.methodologyList.innerHTML = Object.entries(payload.methodology ?? {})
    .map(([key, value]) => `<div><dt>${key.replaceAll("_", " ")}</dt><dd>${value}</dd></div>`)
    .join("");
  els.referenceList.innerHTML = (payload.references ?? [])
    .map((reference) => `<li><a href="${reference.url}" target="_blank" rel="noreferrer">${reference.label}</a></li>`)
    .join("");
}

async function init() {
  els.chartTabs.querySelectorAll(".chart-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.chartMode = button.dataset.chartMode;
      render();
    });
  });

  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.payload = await response.json();
    state.selectedSymbol = state.payload.tickers[0]?.symbol ?? null;
    render();
  } catch (error) {
    els.globalNotice.hidden = false;
    els.globalNotice.textContent = `Data load failed: ${error.message}`;
    els.freshnessBadge.textContent = "FAILED";
    els.freshnessBadge.className = "badge badge-negative";
  }
}

init();
