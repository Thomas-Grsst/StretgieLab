"use strict";

const LC = window.LightweightCharts;
const state = { symbols: [], strategies: { builtin: [], saved: [], template: "" }, charts: {} };
const COLORS = { accent: "#f0a640", blue: "#58a6ff", up: "#3fb950", down: "#f85149", muted: "#8b949e", purple: "#bc8cff", grid: "#1f2733" };

const $ = (selector) => document.querySelector(selector);
const pct = (v, digits = 1) => (v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(digits)} %`);
const num = (v, digits = 2) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(digits));
const signClass = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, options = {}) {
  const init = { ...options };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(payload.detail) ? payload.detail.map((d) => d.msg).join(", ") : payload.detail;
    throw new Error(detail || `Erreur ${response.status}`);
  }
  return payload;
}

function toast(message, isError = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast${isError ? " error" : ""}`;
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (element.hidden = true), isError ? 7000 : 3500);
}

async function withBusy(button, task) {
  button.disabled = true;
  try {
    return await task();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function makeChart(id, height) {
  if (state.charts[id]) state.charts[id].remove();
  const element = document.getElementById(id);
  const chart = LC.createChart(element, {
    autoSize: true,
    height: height || element.clientHeight,
    layout: { background: { color: "transparent" }, textColor: COLORS.muted, fontSize: 11 },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    rightPriceScale: { borderColor: "#2a3240" },
    timeScale: { borderColor: "#2a3240" },
    crosshair: { mode: 0 },
  });
  state.charts[id] = chart;
  return chart;
}

/* ---------- Onglets ---------- */
document.querySelectorAll(".tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b === button));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${button.dataset.tab}`));
    if (button.dataset.tab === "chart") loadChart();
    if (button.dataset.tab === "portfolio" && !$("#pf-assets").children.length) renderPortfolioAssets();
  });
});

function switchTab(name) {
  document.querySelector(`.tabs button[data-tab="${name}"]`).click();
}

/* ---------- Données ---------- */
async function refreshSymbols() {
  state.symbols = await api("/api/symbols");
  const body = $("#symbols-table tbody");
  body.innerHTML = state.symbols.length
    ? state.symbols.map((s) => `<tr><td><b>${escapeHtml(s.symbol)}</b></td><td>${escapeHtml(s.source)}</td><td class="num">${s.bars}</td><td>${s.first_date || ""}</td><td>${s.last_date || ""}</td>
        <td><button class="icon-btn" data-delete="${escapeHtml(s.symbol)}" title="Supprimer">✕</button></td></tr>`).join("")
    : `<tr><td colspan="6" class="hint">Aucune donnée. Importe un CSV ou régénère les données démo.</td></tr>`;
  document.querySelectorAll(".symbol-select").forEach((select) => {
    const previous = select.value;
    select.innerHTML = state.symbols.map((s) => `<option>${escapeHtml(s.symbol)}</option>`).join("");
    if (state.symbols.some((s) => s.symbol === previous)) select.value = previous;
  });
  renderPortfolioAssets();
}

$("#symbols-table").addEventListener("click", async (event) => {
  const symbol = event.target.dataset.delete;
  if (!symbol || !confirm(`Supprimer ${symbol} et toutes ses données ?`)) return;
  await api(`/api/symbols/${encodeURIComponent(symbol)}`, { method: "DELETE" });
  toast(`${symbol} supprimé`);
  refreshSymbols();
});

$("#csv-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  withBusy(form.querySelector("button"), async () => {
    const result = await api("/api/import/csv", { method: "POST", body: new FormData(form) });
    toast(`${result.symbol} : ${result.bars} barres importées`);
    form.reset();
    refreshSymbols();
  });
});

$("#download-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  withBusy(form.querySelector("button"), async () => {
    const result = await api("/api/import/download", { method: "POST", body: Object.fromEntries(new FormData(form)) });
    toast(`${result.symbol} : ${result.bars} barres enregistrées localement`);
    refreshSymbols();
  });
});

$("#demo-btn").addEventListener("click", (event) =>
  withBusy(event.target, async () => {
    await api("/api/import/demo", { method: "POST" });
    toast("Données démo régénérées");
    refreshSymbols();
  })
);

/* ---------- Graphique ---------- */
async function loadChart() {
  const symbol = $("#chart-symbol").value;
  if (!symbol) return;
  const data = await api(`/api/bars/${encodeURIComponent(symbol)}`).catch((e) => toast(e.message, true));
  if (!data) return;
  const show = Object.fromEntries([...document.querySelectorAll("[data-ind]")].map((c) => [c.dataset.ind, c.checked]));

  const price = makeChart("price-chart");
  const candles = price.addCandlestickSeries({ upColor: COLORS.up, downColor: COLORS.down, borderVisible: false, wickUpColor: COLORS.up, wickDownColor: COLORS.down });
  candles.setData(data.candles);
  const volume = price.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", color: "#2a3a52" });
  price.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  volume.setData(data.candles.map((c) => ({ time: c.time, value: c.volume, color: c.close >= c.open ? "#1f3d2c" : "#4a2324" })));
  const line = (key, color, style = 0) => price.addLineSeries({ color, lineWidth: 1, lineStyle: style, priceLineVisible: false, lastValueVisible: false }).setData(data.indicators[key]);
  if (show.sma20) line("sma20", COLORS.accent);
  if (show.sma50) line("sma50", COLORS.blue);
  if (show.sma200) line("sma200", COLORS.purple);
  if (show.bb) { line("bb_upper", COLORS.muted, 2); line("bb_lower", COLORS.muted, 2); }

  const rsi = makeChart("rsi-chart");
  const rsiSeries = rsi.addLineSeries({ color: COLORS.purple, lineWidth: 1 });
  rsiSeries.setData(data.indicators.rsi14);
  [30, 70].forEach((level) => rsiSeries.createPriceLine({ price: level, color: COLORS.muted, lineStyle: 2, lineWidth: 1, axisLabelVisible: false }));

  const macd = makeChart("macd-chart");
  macd.addHistogramSeries({ priceLineVisible: false }).setData(data.indicators.macd_hist.map((p) => ({ ...p, color: p.value >= 0 ? "#2f6f45" : "#8a3434" })));
  macd.addLineSeries({ color: COLORS.blue, lineWidth: 1, priceLineVisible: false }).setData(data.indicators.macd);
  macd.addLineSeries({ color: COLORS.accent, lineWidth: 1, priceLineVisible: false }).setData(data.indicators.macd_signal);

  [price, rsi, macd].forEach((c) => c.timeScale().fitContent());
  syncTimeScales([price, rsi, macd]);

  const last = data.candles.at(-1);
  const previous = data.candles.at(-2) || last;
  const change = last.close / previous.close - 1;
  $("#chart-quote").innerHTML = `<b>${escapeHtml(symbol)}</b> ${last.close.toFixed(2)} <span class="${signClass(change)}">${pct(change, 2)}</span> · ${last.time}`;
}

function syncTimeScales(charts) {
  charts.forEach((source) =>
    source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range || syncTimeScales.busy) return;
      syncTimeScales.busy = true;
      charts.filter((c) => c !== source).forEach((c) => c.timeScale().setVisibleLogicalRange(range));
      syncTimeScales.busy = false;
    })
  );
}

$("#chart-symbol").addEventListener("change", loadChart);
document.querySelectorAll("[data-ind]").forEach((c) => c.addEventListener("change", loadChart));

/* ---------- Backtest ---------- */
async function refreshStrategies() {
  state.strategies = await api("/api/strategies");
  const select = $("#bt-strategy");
  const previous = select.value;
  select.innerHTML =
    `<optgroup label="Intégrées">${state.strategies.builtin.map((s) => `<option value="${s.key}">${escapeHtml(s.name)}</option>`).join("")}</optgroup>` +
    (state.strategies.saved.length ? `<optgroup label="Mes stratégies">${state.strategies.saved.map((s) => `<option value="saved:${escapeHtml(s.name)}">${escapeHtml(s.name)}</option>`).join("")}</optgroup>` : "") +
    `<optgroup label="Code"><option value="custom">Code Python personnalisé…</option></optgroup>`;
  if ([...select.options].some((o) => o.value === previous)) select.value = previous;
  renderStrategyForm();
}

function renderStrategyForm() {
  const key = $("#bt-strategy").value;
  const builtin = state.strategies.builtin.find((s) => s.key === key);
  const saved = key.startsWith("saved:") ? state.strategies.saved.find((s) => `saved:${s.name}` === key) : null;
  $("#bt-description").textContent = builtin ? builtin.description : saved ? saved.description || "Stratégie sauvegardée." : "Écris une fonction generate_signals(df, params).";
  $("#bt-params").innerHTML = builtin
    ? builtin.parameters.map((p) => `<label>${escapeHtml(p.label)}<div class="param-row"><input type="range" data-param="${p.name}" min="${p.minimum}" max="${p.maximum}" step="${p.step}" value="${p.default}"><output>${p.default}</output></div></label>`).join("")
    : "";
  $("#bt-params").querySelectorAll("input").forEach((input) => input.addEventListener("input", () => (input.nextElementSibling.value = input.value)));
  const showCode = !builtin;
  $("#bt-code-wrap").hidden = !showCode;
  if (saved) { $("#bt-code").value = saved.code; $("#bt-save-name").value = saved.name; }
  else if (key === "custom" && !$("#bt-code").value) $("#bt-code").value = state.strategies.template;
}

$("#bt-strategy").addEventListener("change", renderStrategyForm);

$("#bt-save").addEventListener("click", (event) =>
  withBusy(event.target, async () => {
    const name = $("#bt-save-name").value.trim();
    if (!name) throw new Error("Donne un nom à la stratégie");
    await api("/api/strategies", { method: "POST", body: { name, code: $("#bt-code").value, description: "" } });
    await refreshStrategies();
    $("#bt-strategy").value = `saved:${name}`;
    renderStrategyForm();
    toast(`Stratégie « ${name} » sauvegardée`);
  })
);

$("#bt-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const params = Object.fromEntries([...document.querySelectorAll("[data-param]")].map((i) => [i.dataset.param, Number(i.value)]));
  const strategy = form.get("strategy");
  const body = {
    symbol: form.get("symbol"),
    strategy: strategy.startsWith("saved:") ? "custom" : strategy,
    params,
    code: $("#bt-code-wrap").hidden ? null : $("#bt-code").value,
    start: form.get("start") || null,
    end: form.get("end") || null,
    fee_bps: Number(form.get("fee_bps")),
    slippage_bps: Number(form.get("slippage_bps")),
    initial_capital: Number(form.get("initial_capital")),
    allow_short: form.get("allow_short") === "on",
  };
  withBusy($("#bt-run"), async () => renderBacktest(await api("/api/backtest", { method: "POST", body })));
});

function kpi(label, value, sub = "", cls = "") {
  return `<div class="kpi"><div class="label">${label}</div><div class="value ${cls}">${value}</div><div class="sub">${sub}</div></div>`;
}

function renderBacktest(result) {
  const m = result.metrics;
  const b = result.benchmark;
  $("#bt-kpis").innerHTML = [
    kpi("Rendement total", pct(m.total_return), `B&H ${pct(b.total_return)}`, signClass(m.total_return)),
    kpi("CAGR", pct(m.cagr), `B&H ${pct(b.cagr)}`, signClass(m.cagr)),
    kpi("Sharpe", num(m.sharpe), `B&H ${num(b.sharpe)}`),
    kpi("Sortino", num(m.sortino), `Calmar ${num(m.calmar)}`),
    kpi("Drawdown max", pct(m.max_drawdown), `${m.max_drawdown_days} j sous l'eau`, "neg"),
    kpi("Volatilité", pct(m.volatility), `VaR 95 % jour ${pct(m.var_95, 2)}`),
    kpi("Transactions", m.trades, `Gagnantes ${pct(m.win_rate, 0)}`),
    kpi("Profit factor", num(m.profit_factor), `Exposition ${pct(m.exposure, 0)}`),
  ].join("");

  const equity = makeChart("equity-chart");
  equity.addLineSeries({ color: COLORS.blue, lineWidth: 1, priceLineVisible: false }).setData(result.benchmark_equity);
  equity.addLineSeries({ color: COLORS.accent, lineWidth: 2 }).setData(result.equity);
  equity.timeScale().fitContent();
  const dd = makeChart("dd-chart");
  dd.addAreaSeries({ lineColor: COLORS.down, topColor: "rgba(248,81,73,.05)", bottomColor: "rgba(248,81,73,.35)", lineWidth: 1, invertFilledArea: true, priceFormat: { type: "percent" } })
    .setData(result.drawdown.map((p) => ({ time: p.time, value: p.value * 100 })));
  dd.timeScale().fitContent();
  syncTimeScales([equity, dd]);

  renderMonthly(result.monthly_returns);
  const trades = result.trades.slice().reverse();
  $("#bt-trades").innerHTML = trades.length
    ? `<table class="table"><thead><tr><th>Sens</th><th>Entrée</th><th>Sortie</th><th class="num">Jours</th><th class="num">Résultat</th></tr></thead><tbody>${trades
        .map((t) => `<tr><td>${t.side === "long" ? "Achat" : "Vente"}${t.open ? " (ouverte)" : ""}</td><td>${t.entry_date}</td><td>${t.exit_date}</td><td class="num">${t.bars}</td><td class="num ${signClass(t.return)}">${pct(t.return, 2)}</td></tr>`)
        .join("")}</tbody></table>`
    : `<p class="hint">Aucune transaction.</p>`;
}

function heatColor(value, scale = 0.08) {
  const intensity = Math.min(Math.abs(value) / scale, 1);
  return value >= 0 ? `rgba(63,185,80,${0.12 + intensity * 0.6})` : `rgba(248,81,73,${0.12 + intensity * 0.6})`;
}

function renderMonthly(rows) {
  const years = [...new Set(rows.map((r) => r.year))].sort((a, b) => b - a);
  const months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
  const byKey = Object.fromEntries(rows.map((r) => [`${r.year}-${r.month}`, r.return]));
  $("#bt-monthly").innerHTML = `<table class="table heat"><thead><tr><th>Année</th>${months.map((m) => `<th>${m}</th>`).join("")}<th>Année</th></tr></thead><tbody>${years
    .map((year) => {
      const values = months.map((_, i) => byKey[`${year}-${i + 1}`]);
      const total = values.filter((v) => v !== undefined).reduce((acc, v) => acc * (1 + v), 1) - 1;
      return `<tr><td><b>${year}</b></td>${values.map((v) => (v === undefined ? "<td></td>" : `<td style="background:${heatColor(v)}">${(v * 100).toFixed(1)}</td>`)).join("")}<td style="background:${heatColor(total, 0.3)}"><b>${(total * 100).toFixed(1)}</b></td></tr>`;
    })
    .join("")}</tbody></table>`;
}

/* ---------- Portefeuille ---------- */
function renderPortfolioAssets() {
  const container = $("#pf-assets");
  const previous = Object.fromEntries([...container.querySelectorAll("[data-pf]")].map((i) => [i.dataset.pf, { checked: i.checked, weight: i.closest(".param-row").querySelector("input[type=number]").value }]));
  container.innerHTML = state.symbols
    .map((s) => {
      const prev = previous[s.symbol];
      const checked = prev ? prev.checked : s.symbol.startsWith("DEMO-");
      return `<div class="param-row"><label class="check"><input type="checkbox" data-pf="${escapeHtml(s.symbol)}" ${checked ? "checked" : ""}> ${escapeHtml(s.symbol)}</label><input type="number" min="0" step="1" value="${prev ? prev.weight : 20}" title="Poids"></div>`;
    })
    .join("");
}

function selectedWeights() {
  return Object.fromEntries(
    [...document.querySelectorAll("[data-pf]")].filter((i) => i.checked).map((i) => [i.dataset.pf, Number(i.closest(".param-row").querySelector("input[type=number]").value)])
  );
}

$("#pf-run").addEventListener("click", (event) =>
  withBusy(event.target, async () => {
    const weights = selectedWeights();
    const body = { symbols: Object.keys(weights), weights, start: $("#pf-start").value || null, end: $("#pf-end").value || null };
    if (body.symbols.length < 2) throw new Error("Sélectionne au moins deux actifs");
    renderPortfolio(await api("/api/portfolio", { method: "POST", body }));
  })
);

function renderPortfolio(result) {
  const m = result.metrics;
  const r = result.risk;
  $("#pf-kpis").innerHTML = [
    kpi("CAGR", pct(m.cagr), `${result.start} → ${result.end}`, signClass(m.cagr)),
    kpi("Volatilité", pct(m.volatility)),
    kpi("Sharpe", num(m.sharpe), `Sortino ${num(m.sortino)}`),
    kpi("Drawdown max", pct(m.max_drawdown), "", "neg"),
    kpi("VaR 95 % (1 j)", pct(r.var_95_historical, 2), `paramétrique ${pct(r.var_95_parametric, 2)}`),
    kpi("CVaR 95 % (1 j)", pct(r.cvar_95, 2), `VaR 99 % ${pct(r.var_99_historical, 2)}`),
  ].join("");

  const chart = makeChart("pf-chart");
  chart.addAreaSeries({ lineColor: COLORS.accent, topColor: "rgba(240,166,64,.3)", bottomColor: "rgba(240,166,64,0)", lineWidth: 2 }).setData(result.equity);
  chart.timeScale().fitContent();

  const symbols = result.symbols;
  $("#pf-corr").innerHTML = `<table class="table heat"><thead><tr><th></th>${symbols.map((s) => `<th>${escapeHtml(s.replace("DEMO-", ""))}</th>`).join("")}</tr></thead><tbody>${result.correlation
    .map((row, i) => `<tr><td><b>${escapeHtml(symbols[i].replace("DEMO-", ""))}</b></td>${row.map((v) => `<td style="background:${heatColor(v, 1)}">${v.toFixed(2)}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;

  $("#pf-assets-table").innerHTML = `<table class="table"><thead><tr><th>Actif</th><th class="num">Poids</th><th class="num">Contrib. risque</th><th class="num">CAGR</th><th class="num">Vol.</th><th class="num">Sharpe</th></tr></thead><tbody>${symbols
    .map((s) => {
      const a = result.assets[s];
      return `<tr><td>${escapeHtml(s)}</td><td class="num">${pct(result.weights[s])}</td><td class="num">${pct(r.risk_contribution[s])}</td><td class="num ${signClass(a.cagr)}">${pct(a.cagr)}</td><td class="num">${pct(a.volatility)}</td><td class="num">${num(a.sharpe)}</td></tr>`;
    })
    .join("")}</tbody></table>`;

  const optimal = (title, portfolio) => `<div class="optimal"><h4>${title}</h4><div class="hint">Rendement ${pct(portfolio.return)} · Vol. ${pct(portfolio.volatility)} · Sharpe ${num(portfolio.sharpe)}</div>
    <div class="hint">${Object.entries(portfolio.weights).filter(([, w]) => w > 0.005).map(([s, w]) => `${escapeHtml(s)} ${pct(w, 0)}`).join(" · ")}</div>
    <button data-weights='${escapeHtml(JSON.stringify(portfolio.weights))}'>Appliquer ces poids</button></div>`;
  $("#pf-optimal").innerHTML = optimal("Sharpe maximal", result.frontier.max_sharpe) + optimal("Volatilité minimale", result.frontier.min_volatility);
  drawFrontier(result);
}

$("#pf-optimal").addEventListener("click", (event) => {
  if (!event.target.dataset.weights) return;
  const weights = JSON.parse(event.target.dataset.weights);
  document.querySelectorAll("[data-pf]").forEach((input) => {
    const weight = weights[input.dataset.pf];
    input.checked = weight !== undefined && weight > 0.005;
    input.closest(".param-row").querySelector("input[type=number]").value = weight !== undefined ? Math.round(weight * 100) : 0;
  });
  $("#pf-run").click();
});

function drawFrontier(result) {
  const canvas = $("#frontier");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);

  const { points, assets, max_sharpe: best, min_volatility: safest } = result.frontier;
  const current = { volatility: result.metrics.volatility, return: result.metrics.cagr };
  const all = [...points, ...assets];
  const pad = { left: 46, right: 12, top: 10, bottom: 28 };
  const xs = all.map((p) => p.volatility);
  const ys = all.map((p) => p.return);
  const [x0, x1] = [Math.min(...xs) * 0.9, Math.max(...xs) * 1.05];
  const [y0, y1] = [Math.min(...ys, 0) - 0.01, Math.max(...ys) + 0.01];
  const sx = (v) => pad.left + ((v - x0) / (x1 - x0)) * (width - pad.left - pad.right);
  const sy = (v) => height - pad.bottom - ((v - y0) / (y1 - y0)) * (height - pad.top - pad.bottom);

  ctx.strokeStyle = COLORS.grid;
  ctx.fillStyle = COLORS.muted;
  ctx.font = "11px sans-serif";
  for (let i = 0; i <= 4; i++) {
    const vx = x0 + ((x1 - x0) * i) / 4;
    const vy = y0 + ((y1 - y0) * i) / 4;
    ctx.beginPath(); ctx.moveTo(sx(vx), pad.top); ctx.lineTo(sx(vx), height - pad.bottom); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pad.left, sy(vy)); ctx.lineTo(width - pad.right, sy(vy)); ctx.stroke();
    ctx.fillText(`${(vx * 100).toFixed(0)}%`, sx(vx) - 10, height - 10);
    ctx.fillText(`${(vy * 100).toFixed(0)}%`, 6, sy(vy) + 4);
  }
  const sharpes = points.map((p) => p.sharpe);
  const [s0, s1] = [Math.min(...sharpes), Math.max(...sharpes)];
  points.forEach((p) => {
    const t = (p.sharpe - s0) / (s1 - s0 || 1);
    ctx.fillStyle = `hsla(${210 - t * 170}, 80%, 60%, .55)`;
    ctx.fillRect(sx(p.volatility) - 1.5, sy(p.return) - 1.5, 3, 3);
  });
  const marker = (p, color, label, size, dy) => {
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(sx(p.volatility), sy(p.return), size, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = size > 3 ? color : COLORS.muted;
    ctx.fillText(label, sx(p.volatility) + size + 3, sy(p.return) + dy);
  };
  assets.forEach((a) => marker(a, "#e6edf3", a.symbol.replace("DEMO-", ""), 3, 12));
  marker(safest, COLORS.blue, "Vol. min", 6, -6);
  marker(best, COLORS.up, "Sharpe max", 6, -6);
  marker(current, COLORS.accent, "Actuel", 6, -6);
}

/* ---------- Assistant IA ---------- */
async function refreshAssistant() {
  const status = await api("/api/assistant/status").catch(() => ({ available: false, models: [] }));
  const badge = $("#ai-status");
  badge.textContent = status.available ? `IA locale : ${status.models.length} modèle(s)` : "IA locale : non détectée";
  badge.classList.toggle("on", status.available);
  $("#ai-model").innerHTML = status.models.map((m) => `<option>${escapeHtml(m)}</option>`).join("") || "<option value=''>Aucun modèle</option>";
  $("#ai-run").disabled = !status.available || !status.models.length;
  if (!status.available) {
    $("#ai-help").innerHTML = `Ollama n'est pas détecté (${escapeHtml(status.url || "localhost:11434")}). Le reste de l'application fonctionne normalement.<br>
      Pour activer l'assistant : installe <a href="https://ollama.com" target="_blank" rel="noopener">Ollama</a>, puis <code>ollama pull qwen2.5-coder:7b</code> et recharge la page.`;
  }
}

$("#ai-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const answer = $("#ai-answer");
  withBusy($("#ai-run"), async () => {
    answer.className = "answer";
    answer.textContent = "Génération en cours (modèle local)…";
    try {
      const result = await api("/api/assistant/strategy", {
        method: "POST",
        body: { prompt: $("#ai-prompt").value, model: $("#ai-model").value, previous_code: $("#ai-iterate").checked ? $("#ai-code").value : null },
      });
      answer.textContent = result.answer.replace(/```[\s\S]*?```/g, "").trim();
      if (result.code) $("#ai-code").value = result.code;
      if (result.validation_error) { answer.classList.add("error"); answer.textContent += `\n\n⚠ Code refusé par le bac à sable : ${result.validation_error}`; }
      else if (!result.code) { answer.classList.add("error"); answer.textContent += "\n\n⚠ Aucun code exploitable dans la réponse, reformule la demande."; }
    } catch (error) {
      answer.className = "answer error";
      answer.textContent = error.message;
    }
  });
});

$("#ai-to-backtest").addEventListener("click", () => {
  $("#bt-strategy").value = "custom";
  renderStrategyForm();
  $("#bt-code").value = $("#ai-code").value;
  switchTab("backtest");
});

/* ---------- Démarrage ---------- */
(async function init() {
  try {
    await refreshSymbols();
    await refreshStrategies();
    $("#ai-code").value = state.strategies.template;
  } catch (error) {
    toast(error.message, true);
  }
  refreshAssistant();
  window.addEventListener("resize", () => { if (document.querySelector("#tab-portfolio.active") && $("#pf-kpis .kpi")) $("#pf-run").click(); });
})();
