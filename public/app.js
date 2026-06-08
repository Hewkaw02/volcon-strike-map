const state = {
  payload: null,
  selectedSymbol: null,
};

const els = {
  freshnessBadge: document.querySelector("#freshnessBadge"),
  generatedAt: document.querySelector("#generatedAt"),
  globalNotice: document.querySelector("#globalNotice"),
  tickerTabs: document.querySelector("#tickerTabs"),
  summaryGrid: document.querySelector("#summaryGrid"),
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
