"use strict";

const SHORT = {
  "1 jour": "1J", "5 jours": "5J", "1 mois": "1M", "3 mois": "3M",
  "6 mois": "6M", "Depuis le 1er janvier": "YTD", "1 an": "1A",
};
const JOURS = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];

const state = { data: null, period: "1 mois", side: "top", view: "rank", ticker: null, compare: false };
const charts = {};
const $ = (sel) => document.querySelector(sel);

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmtPct = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(2).replace(".", ",")} %`);
const fmtNum = (v, d = 2) =>
  v == null ? "–" : v.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const cls = (v) => (v == null ? "" : v >= 0 ? "up" : "down");
const parseDay = (s) => new Date(`${s}T12:00:00`);
const fmtDay = (s) => {
  const d = parseDay(s);
  return `${JOURS[d.getDay()]} ${d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" })}`;
};

function setPill(el, v) {
  el.textContent = fmtPct(v);
  el.className = `pill ${cls(v)}`;
}

// Même logique que cac40_app/analytics.py:period_start
function periodStart(lastDay, period) {
  const d = parseDay(lastDay);
  const back = { "1 jour": [0, 0, 1], "5 jours": [0, 0, 7], "1 mois": [0, 1, 0], "3 mois": [0, 3, 0],
    "6 mois": [0, 6, 0], "1 an": [1, 0, 0] }[period];
  if (!back) return new Date(d.getFullYear() - 1, 11, 31, 12);
  return new Date(d.getFullYear() - back[0], d.getMonth() - back[1], d.getDate() - back[2], 12);
}

function chartRange(period) {
  const dates = state.data.dates;
  const start = periodStart(state.data.last_session, period);
  let i = dates.findIndex((s) => parseDay(s) > start);
  i = i <= 0 ? 0 : i - 1; // inclure la clôture de base
  return Math.min(i, Math.max(0, dates.length - 6)); // au moins ~5 séances à l'écran
}

// ---------- Rendu ----------

function renderHeader() {
  const d = state.data;
  const upd = new Date(d.updated_at);
  $("#updated").textContent =
    `Séance du ${fmtDay(d.last_session)} · maj ${upd.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`;
  $("#index-level").textContent = fmtNum(d.index.last, 0);
  setPill($("#index-perf"), d.index.perf[state.period]);
}

function renderPeriods() {
  const nav = $("#periods");
  nav.innerHTML = "";
  for (const p of state.data.periods) {
    const b = document.createElement("button");
    b.className = `chip${p === state.period ? " active" : ""}`;
    b.textContent = SHORT[p] || p;
    b.title = p;
    b.onclick = () => { state.period = p; save(); renderAll(); };
    nav.appendChild(b);
  }
}

function ranked() {
  const list = state.data.stocks.filter((s) => s.perf[state.period] != null);
  list.sort((a, b) => b.perf[state.period] - a.perf[state.period]);
  return state.side === "top" ? list.slice(0, 10) : list.slice(-10).reverse();
}

function renderRank() {
  document.querySelectorAll(".seg").forEach((b) => b.classList.toggle("active", b.dataset.side === state.side));
  const rows = ranked();
  const color = state.side === "top" ? css("--up") : css("--down");

  charts.rank?.destroy();
  charts.rank = new Chart($("#rank-chart"), {
    type: "bar",
    data: {
      labels: rows.map((s) => s.name),
      datasets: [{ data: rows.map((s) => s.perf[state.period]), backgroundColor: color, borderRadius: 4 }],
    },
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      animation: { duration: 250 },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmtPct(c.parsed.x) } } },
      scales: {
        x: { ticks: { color: css("--muted"), callback: (v) => `${v} %` }, grid: { color: css("--border") } },
        y: { ticks: { color: css("--text"), font: { size: 12 } }, grid: { display: false } },
      },
      onClick: (_, els) => els.length && openStock(rows[els[0].index].ticker),
    },
  });

  const ul = $("#rank-list");
  ul.innerHTML = "";
  rows.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = "clickable";
    li.innerHTML = `
      <span class="rank">${i + 1}</span>
      <div class="grow"><div class="name">${s.name}</div>
        <div class="muted small">${s.sector}${s.next_earnings ? ` · résultats ${fmtDay(s.next_earnings)}` : ""}</div></div>
      <div class="right"><div>${fmtNum(s.last)} €</div><span class="pill ${cls(s.perf[state.period])}">${fmtPct(s.perf[state.period])}</span></div>`;
    li.onclick = () => openStock(s.ticker);
    ul.appendChild(li);
  });
}

function renderStockSelect() {
  const sel = $("#stock-select");
  if (sel.options.length) return;
  [...state.data.stocks].sort((a, b) => a.name.localeCompare(b.name, "fr")).forEach((s) => {
    sel.add(new Option(s.name, s.ticker));
  });
  sel.onchange = () => { state.ticker = sel.value; save(); renderChart(); };
}

function renderChart() {
  const d = state.data;
  const s = d.stocks.find((x) => x.ticker === state.ticker) || d.stocks[0];
  state.ticker = s.ticker;
  $("#stock-select").value = s.ticker;
  $("#stock-name").textContent = s.name;
  $("#stock-meta").textContent =
    `${s.ticker} · ${s.sector}${s.next_earnings ? ` · prochains résultats ${fmtDay(s.next_earnings)}` : ""}`;
  $("#stock-last").textContent = `${fmtNum(s.last)} €`;
  setPill($("#stock-perf"), s.perf[state.period]);
  $("#compare").checked = state.compare;

  const from = chartRange(state.period);
  const labels = d.dates.slice(from);
  let prices = s.closes.slice(from);
  let index = d.index.closes.slice(from);
  const rebase = (arr) => {
    const base = arr.find((v) => v != null);
    return arr.map((v) => (v == null || !base ? null : (v / base) * 100));
  };
  if (state.compare) { prices = rebase(prices); index = rebase(index); }

  // Points de publication visibles sur la période
  const pos = new Map(labels.map((l, i) => [l, i]));
  const marks = labels.map(() => null);
  const markColors = labels.map(() => "transparent");
  const markInfo = {};
  for (const e of s.events) {
    const i = pos.get(e.reaction_date);
    if (i == null) continue;
    marks[i] = prices[i];
    markColors[i] = e.reaction >= 0 ? css("--up") : css("--down");
    markInfo[i] = e;
  }

  const datasets = [
    { label: s.name, data: prices, borderColor: css("--accent"), backgroundColor: "transparent",
      borderWidth: 2, pointRadius: 0, tension: 0.15, spanGaps: true },
    { label: "Résultats", data: marks, showLine: false, pointStyle: "rectRot", pointRadius: 7,
      pointHoverRadius: 9, pointBackgroundColor: markColors, pointBorderColor: markColors },
  ];
  if (state.compare) {
    datasets.push({ label: "CAC 40", data: index, borderColor: css("--muted"), borderDash: [5, 4],
      borderWidth: 1.5, pointRadius: 0, tension: 0.15, spanGaps: true });
  }

  charts.price?.destroy();
  charts.price = new Chart($("#price-chart"), {
    type: "line",
    data: { labels, datasets },
    options: {
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: state.compare, labels: { color: css("--text"), filter: (i) => i.text !== "Résultats" } },
        tooltip: {
          filter: (item) => item.raw != null,
          callbacks: {
            title: (items) => fmtDay(items[0].label),
            label: (c) => {
              if (c.dataset.label === "Résultats") {
                const e = markInfo[c.dataIndex];
                return `Résultats : ${fmtPct(e.reaction)} le jour J`;
              }
              return `${c.dataset.label} : ${state.compare ? fmtNum(c.parsed.y, 1) : `${fmtNum(c.parsed.y)} €`}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: css("--muted"), maxRotation: 0, autoSkip: true, maxTicksLimit: 5,
            callback: function (v) {
              const l = this.getLabelForValue(v);
              return parseDay(l).toLocaleDateString("fr-FR", labels.length > 70 ? { month: "short", year: "2-digit" } : { day: "2-digit", month: "short" });
            },
          },
          grid: { display: false },
        },
        y: { position: "right", ticks: { color: css("--muted") }, grid: { color: css("--border") } },
      },
    },
  });

  const st = s.stats;
  $("#stats").innerHTML = st
    ? `<div class="stat"><div class="label">Mouvement moyen jour J</div><div class="value">± ${fmtNum(st.avg_abs)} %</div></div>
       <div class="stat"><div class="label">Réactions positives</div><div class="value">${fmtNum(st.up_share, 0)} %</div></div>
       <div class="stat"><div class="label">Plus forte hausse</div><div class="value" style="color:var(--up)">${fmtPct(st.max)}</div></div>
       <div class="stat"><div class="label">Plus forte baisse</div><div class="value" style="color:var(--down)">${fmtPct(st.min)}</div></div>`
    : "";

  const ul = $("#events");
  ul.innerHTML = "";
  const evs = [...s.events].reverse();
  if (!evs.length) ul.innerHTML = `<li class="empty">Aucune publication passée trouvée.</li>`;
  for (const e of evs) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="grow"><div class="name">${fmtDay(e.date)}</div>
        <div class="muted small">vs CAC ${fmtPct(e.excess)} · 5 séances ${fmtPct(e.drift)}${e.surprise != null ? ` · surprise BPA ${fmtPct(e.surprise)}` : ""}</div></div>
      <span class="pill ${cls(e.reaction)}">${fmtPct(e.reaction)}</span>`;
    ul.appendChild(li);
  }
}

function renderAgenda() {
  const box = $("#agenda");
  box.innerHTML = "";
  const byTicker = new Map(state.data.stocks.map((s) => [s.ticker, s]));
  const items = state.data.upcoming;
  if (!items.length) {
    box.innerHTML = `<div class="empty card">Aucune date de résultats connue pour le moment.</div>`;
    return;
  }
  let current = null;
  let ul = null;
  for (const it of items) {
    if (it.date !== current) {
      current = it.date;
      const h = document.createElement("div");
      h.className = "day-title";
      h.textContent = parseDay(it.date).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
      box.appendChild(h);
      ul = document.createElement("ul");
      ul.className = "list";
      box.appendChild(ul);
    }
    const s = byTicker.get(it.ticker);
    const p = s?.perf[state.period];
    const li = document.createElement("li");
    li.className = "clickable";
    li.innerHTML = `
      <div class="grow"><div class="name">${it.name}</div>
        <div class="muted small">${it.avg_abs != null ? `réaction moyenne ± ${fmtNum(it.avg_abs)} %` : "pas d'historique"}${it.eps_estimate != null ? ` · BPA estimé ${fmtNum(it.eps_estimate)}` : ""}</div></div>
      <div class="right"><div class="muted small">${SHORT[state.period]}</div><span class="pill ${cls(p)}">${fmtPct(p)}</span></div>`;
    li.onclick = () => openStock(it.ticker);
    ul.appendChild(li);
  }
}

// ---------- Navigation ----------

function show(view) {
  state.view = view;
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
  save();
  renderView();
  window.scrollTo({ top: 0 });
}

function openStock(ticker) {
  state.ticker = ticker;
  show("chart");
}

function renderView() {
  if (state.view === "rank") renderRank();
  else if (state.view === "chart") renderChart();
  else renderAgenda();
}

function renderAll() {
  renderHeader();
  renderPeriods();
  renderStockSelect();
  renderView();
}

function save() {
  try {
    localStorage.setItem("cac40-prefs", JSON.stringify({
      period: state.period, side: state.side, view: state.view, ticker: state.ticker, compare: state.compare,
    }));
  } catch (_) { /* stockage indisponible : on ignore */ }
}

function restore() {
  try {
    Object.assign(state, JSON.parse(localStorage.getItem("cac40-prefs") || "{}"));
  } catch (_) { /* idem */ }
}

async function init() {
  restore();
  document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => show(t.dataset.view)));
  document.querySelectorAll(".seg").forEach((b) => (b.onclick = () => { state.side = b.dataset.side; save(); renderRank(); }));
  $("#compare").onchange = (e) => { state.compare = e.target.checked; save(); renderChart(); };

  try {
    const res = await fetch(`data.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    state.data = await res.json();
  } catch (err) {
    $("#updated").textContent = "Données indisponibles. Vérifiez la connexion.";
    return;
  }
  if (!state.data.periods.includes(state.period)) state.period = "1 mois";
  renderHeader();
  renderPeriods();
  renderStockSelect();
  show(["rank", "chart", "agenda"].includes(state.view) ? state.view : "rank");

  // Les couleurs suivent le thème clair/sombre du téléphone
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", renderView);
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}

init();
