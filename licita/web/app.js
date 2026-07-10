/* Heraclitus Gov Radar — frontend do Radar (vanilla JS, zero deps).
   Consome a própria API FastAPI: /radar/demo, /forecast/demo, /score, /decide. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const REC = { participar: "go", avaliar: "maybe", ignorar: "no" };
const REC_LABEL = { go: "Participar", maybe: "Avaliar", no: "Ignorar" };

const brl = (v) =>
  v == null ? "—"
  : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// BASE = diretório onde a app está montada (raiz "/" ou subcaminho "/licita/").
// Torna a SPA portável: servida na raiz OU atrás de um proxy de subcaminho,
// os pedidos à API resolvem sempre relativos a esta base.
const BASE = location.pathname.replace(/[^/]*$/, "");

async function api(path, opts) {
  const r = await fetch(BASE + path.replace(/^\//, ""), opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}

/* ── Health ─────────────────────────────────────────────── */
async function pingHealth() {
  const el = $("#apiStatus"), txt = $("#apiStatusText");
  try {
    const h = await api("/health");
    el.className = "status ok"; txt.textContent = `online · v${h.version}`;
  } catch {
    el.className = "status down"; txt.textContent = "offline";
  }
}

/* ── Score gauge ────────────────────────────────────────── */
function gauge(value, cls) {
  const p = Math.max(0, Math.min(100, value)) / 100;
  return `<div class="gauge ${cls}" style="--p:${p.toFixed(3)}">
    <svg width="62" height="62"><circle class="track" cx="31" cy="31" r="26"/><circle class="fill" cx="31" cy="31" r="26"/></svg>
    <b>${Math.round(value)}</b></div>`;
}

/* ── Radar ──────────────────────────────────────────────── */
let RADAR_CACHE = [];
async function loadRadar() {
  const grid = $("#radarGrid");
  grid.innerHTML = Array(3).fill('<div class="skeleton"></div>').join("");
  try {
    RADAR_CACHE = await api("/radar/demo?min_score=0");
    renderRadar();
  } catch (e) {
    grid.innerHTML = `<div class="empty">Falha ao carregar o radar: ${esc(e.message)}</div>`;
  }
}
function renderRadar() {
  const min = +$("#minScore").value;
  const items = RADAR_CACHE.filter((o) => o.score.value >= min);
  renderStats(RADAR_CACHE);
  const grid = $("#radarGrid");
  if (!items.length) { grid.innerHTML = `<div class="empty">Nenhuma oportunidade ≥ ${min}%.</div>`; return; }
  grid.innerHTML = items
    .sort((a, b) => b.score.value - a.score.value)
    .map((o) => {
      const cls = REC[o.score.recommendation] || "maybe";
      const tags = o.score.matched.slice(0, 5).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
      const link = o.url ? `<a class="chip" href="${esc(o.url)}" target="_blank" rel="noopener">edital ↗</a>` : "";
      return `<article class="card ${cls}">
        <div class="card-head">
          <div>
            <div class="card-org">${esc(o.orgao || o.fonte)}</div>
            <h3 class="card-obj">${esc(o.objeto)}</h3>
          </div>
          ${gauge(o.score.value, cls)}
        </div>

      </article>`;
    })
    .join("");
}
function renderStats(items) {
  const by = (r) => items.filter((o) => o.score.recommendation === r).length;
  const total = items.reduce((s, o) => s + (o.valor_estimado || 0), 0);
  $("#statStrip").innerHTML = [
    ["total", "Editais", items.length],
    ["go", "Participar", by("participar")],
    ["maybe", "Avaliar", by("avaliar")],
    ["no", "Ignorar", by("ignorar")],
  ].map(([c, k, v]) => `<div class="stat ${c}"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")
   + `<div class="stat total" style="grid-column:1/-1"><div class="k">Valor total mapeado</div><div class="v">${brl(total)}</div></div>`;
}

/* ── Forecast ───────────────────────────────────────────── */
// Janelas na ordem temporal, com rótulo. As chaves batem o enum ForecastWindow
// (minúsculas): iminente ≤2m · proximo 3-6m · futuro >6m · sem_data.
const WINDOWS = [
  ["iminente", "Iminente · ≤2 meses"],
  ["proximo", "Próximo · 3-6 meses"],
  ["futuro", "Futuro · >6 meses"],
  ["sem_data", "Sem data"],
];
async function loadForecast() {
  const grid = $("#forecastGrid");
  grid.innerHTML = '<div class="empty">A carregar forecast…</div>';
  try {
    const items = await api("/forecast/demo?min_score=0");
    const groups = {};
    items.forEach((o) => (groups[o.window] ||= []).push(o));
    grid.innerHTML = WINDOWS.filter(([k]) => groups[k]?.length).map(([win, label]) => {
      const list = groups[win];
      const cls = win === "sem_data" ? "futuro" : win;
      const cards = list.sort((a, b) => a.months_ahead - b.months_ahead).map((o) => {
        const rc = REC[o.score.recommendation] || "maybe";
        return `<article class="card ${rc}">
          <div class="card-head">
            <div><div class="card-org">${esc(o.orgao)}</div><h3 class="card-obj">${esc(o.objeto)}</h3></div>
            ${gauge(o.score.value, rc)}
          </div>
          <div class="card-meta">
            ${o.uf ? `<span class="chip uf">${esc(o.uf)}</span>` : ""}
            <span class="chip val">${brl(o.valor_estimado)}</span>
            <span class="chip"><span class="ahead">${o.months_ahead}</span> meses</span>
          </div>
          <div class="prep"><b>Preparar:</b> ${esc(o.prepare_action)}</div>
        </article>`;
      }).join("");
      return `<div class="tl-window"><div class="tl-head"><span class="tl-badge ${cls}">${label}</span><span class="tl-line"></span></div><div class="tl-cards">${cards}</div></div>`;
    }).join("") || '<div class="empty">Sem itens de PCA.</div>';
  } catch (e) {
    grid.innerHTML = `<div class="empty">Falha no forecast: ${esc(e.message)}</div>`;
  }
}

/* ── Simulador ──────────────────────────────────────────── */
async function runSim(ev) {
  ev.preventDefault();
  const out = $("#simResult");
  out.innerHTML = '<div class="skeleton" style="height:220px"></div>';
  const edital = {
    objeto: $("#f_objeto").value, orgao: $("#f_orgao").value,
    uf: $("#f_uf").value || null, texto: $("#f_texto").value,
  };
  const profile = {
    capital_social: +$("#p_capital").value || 0,
    volumetria_max_tb_dia: +$("#p_vol").value || 0,
  };
  try {
    const [score, decision] = await Promise.all([
      api("/score", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(edital) }),
      api("/decide", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ edital, profile }) }),
    ]);
    const cls = REC[score.recommendation] || "maybe";
    const dcls = decision.decision === "participar" ? "go" : decision.decision === "avaliar" ? "maybe" : "no";
    const blockers = (decision.blockers || []).map((b) =>
      `<div class="blocker ${b.hard ? "hard" : "soft"}"><span class="sev">${b.hard ? "HARD" : "SOFT"}</span> ${esc(b.detail || b.code)}</div>`).join("")
      || `<div class="muted">Nenhum bloqueio de habilitação detectado.</div>`;
    const tags = score.matched.map((t) => `<span class="tag">${esc(t)}</span>`).join("");
    out.innerHTML = `<article class="card ${cls}">
      <div class="verdict">
        ${gauge(score.value, cls)}
        <div>
          <div class="verdict-label rec ${dcls}" style="margin:0">${esc(decision.decision).toUpperCase()}</div>
          <div class="prob">Probabilidade de sucesso: <b>${(decision.probability * 100).toFixed(1)}%</b> · compat técnica ${score.value}%</div>
        </div>
      </div>
      ${tags ? `<div class="tags" style="margin-top:16px">${tags}</div>` : ""}
      <div class="blockers">${blockers}</div>
    </article>`;
  } catch (e) {
    out.innerHTML = `<div class="empty">Falha na avaliação: ${esc(e.message)}</div>`;
  }
}

/* ── Tabs, tema, boot ───────────────────────────────────── */
function initTabs() {
  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("is-active"));
    $$(".panel").forEach((x) => x.classList.remove("is-active"));
    t.classList.add("is-active");
    $(`#tab-${t.dataset.tab}`).classList.add("is-active");
    if (t.dataset.tab === "forecast" && !$("#forecastGrid").dataset.loaded) {
      $("#forecastGrid").dataset.loaded = "1"; loadForecast();
    }
  }));
}
function initTheme() {
  const saved = localStorage.getItem("licita-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  $("#themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("licita-theme", next);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTabs(); initTheme();
  $("#minScore").addEventListener("input", (e) => { $("#minScoreOut").textContent = e.target.value; renderRadar(); });
  $("#reloadRadar").addEventListener("click", loadRadar);
  $("#reloadForecast").addEventListener("click", loadForecast);
  $("#simForm").addEventListener("submit", runSim);
  pingHealth(); loadRadar();
});
