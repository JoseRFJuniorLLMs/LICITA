/* Heraclitus Gov Radar — frontend do Radar (vanilla JS, zero deps).
   Consome a própria API FastAPI: /radar/live, /forecast/live, /score, /decide,
   /users/register, /participations. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const REC = { participar: "go", avaliar: "maybe", ignorar: "no" };
const REC_LABEL = { go: "Participar", maybe: "Avaliar", no: "Ignorar" };
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

const brl = (v) =>
  v == null ? "—"
  : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// Só http/https chegam a href — bloqueia javascript:/data: vindos da rede.
const safeUrl = (u) => (/^https?:\/\//i.test(String(u ?? "")) ? String(u) : null);

// BASE = diretório onde a app está montada (raiz "/" ou subcaminho "/licita/").
const BASE = location.pathname.replace(/[^/]*$/, "");

async function api(path, opts) {
  const r = await fetch(BASE + path.replace(/^\//, ""), opts);
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try { detail = (await r.json()).detail || detail; } catch { /* corpo não-JSON */ }
    const err = new Error(detail); err.status = r.status; throw err;
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}
const postJson = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/* ── Sessão do utilizador (localStorage) ────────────────── */
let USER = null;
try { USER = JSON.parse(localStorage.getItem("licita-user") || "null"); } catch { USER = null; }
let CLAIMS = new Map(); // bid_id → {user_id, user_name}

function renderUserBox() {
  const box = $("#userBox");
  box.innerHTML = USER
    ? `<span class="user-chip" data-hint="Sessão ativa — as suas participações aparecem primeiro">👤 ${esc(USER.name)}</span>
       <button class="btn btn-ghost" id="logoutBtn">sair</button>`
    : `<button class="btn" id="loginBtn">Entrar</button>`;
  $("#loginBtn")?.addEventListener("click", openLogin);
  $("#logoutBtn")?.addEventListener("click", () => {
    localStorage.removeItem("licita-user"); USER = null; renderUserBox(); renderRadar();
  });
}
let LOGIN_MODE = "login"; // "login" | "register"
function openLogin(afterLogin) {
  $("#loginModal").classList.add("open");
  $("#loginModal").dataset.pending = "";
  if (typeof afterLogin === "string") $("#loginModal").dataset.pending = afterLogin;
  $("#l_user").focus();
}
function setLoginMode(mode) {
  LOGIN_MODE = mode;
  $("#loginTitle").textContent = mode === "login" ? "Entrar" : "Criar conta";
  $("#loginSubmit").textContent = mode === "login" ? "Entrar" : "Criar conta";
  $("#loginToggle").textContent = mode === "login" ? "criar conta nova" : "já tenho conta";
  $("#loginErr").textContent = "";
}
async function doLogin(ev) {
  ev.preventDefault();
  const username = $("#l_user").value.trim(), password = $("#l_pass").value;
  const email = $("#l_email").value.trim();
  const errEl = $("#loginErr"); errEl.textContent = "";
  try {
    USER = await postJson(LOGIN_MODE === "login" ? "/auth/login" : "/auth/register",
      { username, password, email });
    localStorage.setItem("licita-user", JSON.stringify(USER));
    $("#loginModal").classList.remove("open");
    renderUserBox();
    const pending = $("#loginModal").dataset.pending;
    if (pending) await claimBid(pending);
    renderRadar();
  } catch (e) { errEl.textContent = e.message; }
}

/* ── Participações ──────────────────────────────────────── */
async function loadClaims() {
  try {
    const rows = await api("/participations");
    CLAIMS = new Map(rows.map((p) => [p.bid_id, p]));
  } catch { /* radar continua sem claims */ }
}
const authHeaders = () => (USER?.token ? { Authorization: `Bearer ${USER.token}` } : {});
const postAuth = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body) });

async function claimBid(bidId) {
  if (!USER) { openLogin(bidId); return; }
  const o = RADAR_CACHE.find((x) => x.bid_id === bidId);
  try {
    const r = await postAuth("/participations", { bid_id: bidId, edital: o || {} });
    await loadClaims(); renderRadar();
    toast(r.email === "queued"
      ? `Você está participando — dossiê enviado para ${USER.email}`
      : "Você está participando — adicione um email no login para receber o dossiê");
  } catch (e) {
    if (e.status === 401) { USER = null; localStorage.removeItem("licita-user"); renderUserBox(); openLogin(bidId); return; }
    toast(e.status === 409 ? `⚠ ${e.message}` : `Falha: ${e.message}`, true);
    await loadClaims(); renderRadar();
  }
}
async function releaseBid(bidId) {
  if (!USER) return;
  try {
    await postAuth("/participations/release", { bid_id: bidId });
    await loadClaims(); renderRadar();
  } catch (e) {
    if (e.status === 401) { USER = null; localStorage.removeItem("licita-user"); renderUserBox(); openLogin(); return; }
    toast(`Falha: ${e.message}`, true);
  }
}
function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = `toast show${isErr ? " err" : ""}`;
  clearTimeout(t._h); t._h = setTimeout(() => (t.className = "toast"), 4200);
}

/* ── Health ─────────────────────────────────────────────── */
async function pingHealth() {
  const el = $("#apiStatus"), txt = $("#apiStatusText");
  try {
    const h = await api("/health");
    el.className = "status ok"; txt.textContent = `online · v${h.version}`;
  } catch { el.className = "status down"; txt.textContent = "offline"; }
}

/* ── Score gauge ────────────────────────────────────────── */
function gauge(value, cls) {
  const p = Math.max(0, Math.min(100, value)) / 100;
  return `<div class="gauge ${cls}" style="--p:${p.toFixed(3)}" data-hint="Score de compatibilidade técnica (0–100): quanto do edital casa com o perfil de produto — determinístico e explicável">
    <svg width="62" height="62"><circle class="track" cx="31" cy="31" r="26"/><circle class="fill" cx="31" cy="31" r="26"/></svg>
    <b>${Math.round(value)}</b></div>`;
}

/* ── Estado dos filtros / ordenação ─────────────────────── */
let RADAR_CACHE = [];
const FILTER = { minScore: 0, valor: "any", categoria: "all", sort: "score" };
const VALOR_RANGES = {
  any: [0, Infinity], "lt100k": [0, 100_000], "100k-1m": [100_000, 1_000_000],
  "1m-10m": [1_000_000, 10_000_000], "gt10m": [10_000_000, Infinity],
};

function esferaClass(o) {
  const bid = o.bid_id;
  if (CLAIMS.has(bid)) return "participada";
  if (isNova(o)) return "nova";
  return { federal: "esf-federal", estadual: "esf-estadual", municipal: "esf-municipal", distrital: "esf-federal" }[o.esfera] || "esf-outros";
}
function isNova(o) {
  if (!o.data_publicacao) return false;
  const t = Date.parse(o.data_publicacao);
  return Number.isFinite(t) && Date.now() - t < 48 * 3600 * 1000;
}

/* ── Radar ──────────────────────────────────────────────── */
async function loadRadar() {
  const grid = $("#radarGrid");
  grid.innerHTML = Array(6).fill('<div class="skeleton"></div>').join("");
  try {
    const [res] = await Promise.all([api("/radar/live?min_score=0&dias=7"), loadClaims()]);
    RADAR_CACHE = res.items || [];
    buildCategoriaOptions();
    buildTimelineRail();
    renderRadar(res.meta);
  } catch (e) {
    grid.innerHTML = `<div class="empty">Falha ao carregar o radar: ${esc(e.message)}</div>`;
  }
}

function buildCategoriaOptions() {
  const cats = new Set();
  RADAR_CACHE.forEach((o) => (o.score.matched || []).forEach((c) => cats.add(c)));
  const sel = $("#fCategoria");
  const cur = FILTER.categoria;
  sel.innerHTML = `<option value="all">todas</option>` +
    [...cats].sort().map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  sel.value = cats.has(cur) || cur === "all" ? cur : "all";
}

function applyFilters(items) {
  const [vMin, vMax] = VALOR_RANGES[FILTER.valor] || VALOR_RANGES.any;
  return items.filter((o) => {
    if (o.score.value < FILTER.minScore) return false;
    if (FILTER.valor !== "any") {
      const v = o.valor_estimado;
      if (v == null || v < vMin || v >= vMax) return false;
    }
    if (FILTER.categoria !== "all" && !(o.score.matched || []).includes(FILTER.categoria)) return false;
    return true;
  });
}

function sortItems(items) {
  const mineFirst = (a, b) => {
    if (USER) {
      const am = CLAIMS.get(a.bid_id)?.user_id === USER.user_id ? 1 : 0;
      const bm = CLAIMS.get(b.bid_id)?.user_id === USER.user_id ? 1 : 0;
      if (am !== bm) return bm - am; // as minhas primeiro
    }
    return 0;
  };
  const byScore = (a, b) => b.score.value - a.score.value;
  const byDate = (a, b) => (Date.parse(b.data_abertura || b.data_publicacao || 0) || 0) - (Date.parse(a.data_abertura || a.data_publicacao || 0) || 0);
  return [...items].sort((a, b) => mineFirst(a, b) || (FILTER.sort === "data" ? byDate(a, b) : byScore(a, b)) || byScore(a, b));
}

function cardHtml(o) {
  const cls = REC[o.score.recommendation] || "maybe";
  const eCls = esferaClass(o);
  const claim = CLAIMS.get(o.bid_id);
  const mine = USER && claim?.user_id === USER.user_id;
  const tags = (o.score.matched || []).slice(0, 5).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
  const url = safeUrl(o.url);
  const dt = o.data_abertura ? new Date(o.data_abertura) : null;
  const esfLabel = o.esfera ? o.esfera[0].toUpperCase() + o.esfera.slice(1) : null;
  return `<article class="card ${cls} ${eCls}" data-bid="${esc(o.bid_id)}" data-month="${dt && !isNaN(dt) ? `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}` : ""}">
    ${isNova(o) && !claim ? `<span class="flag-nova" data-hint="Publicada no PNCP há menos de 48 horas">NOVA</span>` : ""}
    <div class="card-head">
      <div>
        <div class="card-org" data-hint="Órgão público que publicou a licitação">${esc(o.orgao || o.fonte)}</div>
        <h3 class="card-obj">${esc(o.objeto)}</h3>
      </div>
      ${gauge(o.score.value, cls)}
    </div>
    <div class="card-meta">
      ${o.bid_id ? `<span class="chip bid" data-hint="Nº de controle do edital no PNCP — identificador único nacional">${esc(o.bid_id)}</span>` : ""}
      ${esfLabel ? `<span class="chip esf ${eCls}" data-hint="Esfera administrativa: Federal (União), Estadual ou Municipal — define o órgão comprador">${esc(esfLabel)}</span>` : ""}
      ${o.uf ? `<span class="chip uf" data-hint="Estado (UF) do órgão comprador">${esc(o.uf)}</span>` : ""}
      ${dt && !isNaN(dt) ? `<span class="chip date" data-hint="Data de abertura das propostas">${dt.toLocaleDateString("pt-BR")}</span>` : ""}
      <span class="chip val" data-hint="Valor total estimado da contratação">${brl(o.valor_estimado)}</span>
      ${url ? `<a class="chip" href="${esc(url)}" target="_blank" rel="noopener" data-hint="Abrir o edital no portal de origem">edital ↗</a>` : ""}
    </div>
    ${tags ? `<div class="tags">${tags}</div>` : ""}
    <div class="card-actions">
      <span class="rec ${cls}" data-hint="Recomendação do radar a partir do score">${REC_LABEL[cls]}</span>
      ${claim
        ? `<span class="owner" data-hint="Esta licitação já está sendo estudada — evita trabalho duplicado">👤 ${esc(claim.user_name)}${mine ? " (você)" : ""}</span>
           ${mine ? `<button class="btn btn-leave" data-release="${esc(o.bid_id)}">sair</button>` : ""}`
        : `<button class="btn btn-join" data-claim="${esc(o.bid_id)}" data-hint="Marcar que VOCÊ vai estudar esta licitação — recebe o dossiê por email e ela fica reservada em seu nome">Participar</button>`}
    </div>
  </article>`;
}

function renderRadar(meta) {
  FILTER.minScore = +$("#minScore").value;
  const items = sortItems(applyFilters(RADAR_CACHE));
  renderStats(RADAR_CACHE, meta);
  const grid = $("#radarGrid");
  grid.innerHTML = items.length
    ? items.map(cardHtml).join("")
    : `<div class="empty">Nenhuma oportunidade com estes filtros.</div>`;
  $$("[data-claim]", grid).forEach((b) => b.addEventListener("click", () => claimBid(b.dataset.claim)));
  $$("[data-release]", grid).forEach((b) => b.addEventListener("click", () => releaseBid(b.dataset.release)));
}

function renderStats(items, meta) {
  const by = (r) => items.filter((o) => o.score.recommendation === r).length;
  const total = items.reduce((s, o) => s + (o.valor_estimado || 0), 0);
  const janela = meta?.janela ? `${meta.janela[0].slice(8)}/${meta.janela[0].slice(5, 7)} – ${meta.janela[1].slice(8)}/${meta.janela[1].slice(5, 7)}` : "";
  $("#statStrip").innerHTML = [
    ["total", "Editais", items.length],
    ["go", "Participar", by("participar")],
    ["maybe", "Avaliar", by("avaliar")],
    ["no", "Ignorar", by("ignorar")],
  ].map(([c, k, v]) => `<div class="stat ${c}"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")
   + `<div class="stat total" style="grid-column:1/-1"><div class="k">Valor total mapeado ${janela ? `· ${janela}` : ""} ${meta?.fonte === "pncp-live" ? "· PNCP ao vivo" : ""}</div><div class="v">${brl(total)}</div></div>`;
}

/* ── Rail temporal (estilo Google Fotos) ────────────────── */
function monthKey(o) {
  const d = new Date(o.data_abertura || o.data_publicacao || NaN);
  return isNaN(d) ? null : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function buildTimelineRail() {
  const rail = $("#timeRail");
  const counts = new Map();
  RADAR_CACHE.forEach((o) => { const k = monthKey(o); if (k) counts.set(k, (counts.get(k) || 0) + 1); });
  const keys = [...counts.keys()].sort().reverse(); // mais recente no topo
  if (!keys.length) { rail.innerHTML = ""; rail.hidden = true; return; }
  rail.hidden = false;
  let lastYear = null;
  rail.innerHTML = keys.map((k) => {
    const [y, m] = k.split("-");
    const yearMark = y !== lastYear ? `<div class="rail-year">${y}</div>` : "";
    lastYear = y;
    return `${yearMark}<button class="rail-tick" data-month="${k}" data-hint="${MESES[+m - 1]} ${y} · ${counts.get(k)} editais"><span></span></button>`;
  }).join("");
  $$(".rail-tick", rail).forEach((t) =>
    t.addEventListener("click", () => {
      if (FILTER.sort !== "data") { FILTER.sort = "data"; $("#fSort").value = "data"; renderRadar(); }
      const el = $(`#radarGrid .card[data-month="${t.dataset.month}"]`);
      if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); el.classList.add("pulse"); setTimeout(() => el.classList.remove("pulse"), 1600); }
    })
  );
}
// Bolha flutuante com o mês/ano do primeiro card visível durante o scroll.
let scrollT = null;
window.addEventListener("scroll", () => {
  const hint = $("#scrollHint");
  if (!hint || !RADAR_CACHE.length || !$("#tab-radar").classList.contains("is-active")) return;
  const cards = $$("#radarGrid .card[data-month]");
  const top = cards.find((c) => c.getBoundingClientRect().bottom > 90);
  if (top && top.dataset.month) {
    const [y, m] = top.dataset.month.split("-");
    hint.textContent = `${MESES[+m - 1]} ${y}`;
    hint.classList.add("show");
    clearTimeout(scrollT); scrollT = setTimeout(() => hint.classList.remove("show"), 900);
  }
}, { passive: true });

/* ── Forecast ───────────────────────────────────────────── */
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
    const res = await api("/forecast/live?min_score=0");
    const items = res.items || [];
    const groups = {};
    items.forEach((o) => (groups[o.window] ||= []).push(o));
    grid.innerHTML = WINDOWS.filter(([k]) => groups[k]?.length).map(([win, label]) => {
      const list = groups[win];
      const cls = win === "sem_data" ? "futuro" : win;
      const cards = list.sort((a, b) => (a.months_ahead ?? 99) - (b.months_ahead ?? 99)).map((o) => {
        const rc = REC[o.score.recommendation] || "maybe";
        const ahead = o.months_ahead == null ? "sem data" : `<span class="ahead">${o.months_ahead}</span> meses`;
        return `<article class="card ${rc}">
          <div class="card-head">
            <div><div class="card-org">${esc(o.orgao)}</div><h3 class="card-obj">${esc(o.objeto)}</h3></div>
            ${gauge(o.score.value, rc)}
          </div>
          <div class="card-meta">
            ${o.uf ? `<span class="chip uf" data-hint="Estado (UF) do órgão">${esc(o.uf)}</span>` : ""}
            <span class="chip val" data-hint="Valor total estimado no plano de contratação">${brl(o.valor_estimado)}</span>
            <span class="chip" data-hint="Quantos meses faltam para a compra planeada">${ahead}</span>
          </div>
          <div class="prep"><b>Preparar:</b> ${esc(o.prepare_action)}</div>
        </article>`;
      }).join("");
      return `<div class="tl-window"><div class="tl-head"><span class="tl-badge ${cls}">${label}</span><span class="tl-line"></span></div><div class="tl-cards">${cards}</div></div>`;
    }).join("") || '<div class="empty">Sem itens de PCA na amostra.</div>';
    if (res.meta?.amostra) {
      grid.insertAdjacentHTML("afterbegin",
        `<div class="muted" style="margin-bottom:6px">Amostra de ${res.meta.total_analisado} itens de PCA ${res.meta.ano} (o universo completo é >1M itens/ano).</div>`);
    }
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
      postJson("/score", edital),
      postJson("/decide", { edital, profile }),
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
  initTabs(); initTheme(); renderUserBox();
  $("#minScore").addEventListener("input", (e) => { $("#minScoreOut").textContent = e.target.value; renderRadar(); });
  $("#fValor").addEventListener("change", (e) => { FILTER.valor = e.target.value; renderRadar(); });
  $("#fCategoria").addEventListener("change", (e) => { FILTER.categoria = e.target.value; renderRadar(); });
  $("#fSort").addEventListener("change", (e) => { FILTER.sort = e.target.value; renderRadar(); });
  $("#reloadRadar").addEventListener("click", loadRadar);
  $("#reloadForecast").addEventListener("click", loadForecast);
  $("#simForm").addEventListener("submit", runSim);
  $("#loginForm").addEventListener("submit", doLogin);
  $("#loginToggle").addEventListener("click", () => setLoginMode(LOGIN_MODE === "login" ? "register" : "login"));
  $("#loginClose").addEventListener("click", () => $("#loginModal").classList.remove("open"));
  pingHealth(); loadRadar();
  setInterval(async () => { await loadClaims(); if ($("#tab-radar").classList.contains("is-active")) renderRadar(); }, 60_000);
});
