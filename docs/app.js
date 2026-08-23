/* MessageFunnel frontend — one page, every platform.
   Modes:
   - LIVE: window.MESSAGE_FUNNEL_API (config.js) reachable -> polls the API.
   - DEMO: API unreachable/empty -> bundled demo-data.json, fully interactive locally.
   Override for testing: append ?api=http://localhost:8800 to the URL. */
"use strict";

const qs = new URLSearchParams(location.search);
const API_BASE = ((qs.get("api") || window.MESSAGE_FUNNEL_API || "").replace(/\/+$/, ""));

const PLATFORM_META = {
  messenger: { name: "Messenger", color: "#0084FF", glyph: "M" },
  instagram: { name: "Instagram", color: "#E1306C", glyph: "IG" },
  tiktok:    { name: "TikTok",    color: "#FE2C55", glyph: "TT" },
  whatsapp:  { name: "WhatsApp",  color: "#25D366", glyph: "WA" },
  telegram:  { name: "Telegram",  color: "#229ED9", glyph: "TG" },
  x:         { name: "X / DMs",   color: "#8899A6", glyph: "X" },
};

const state = {
  mode: "connecting",          // "live" | "demo"
  conversations: [],
  messages: {},                // convId -> [msg]
  activeId: null,
  filter: null,                // platform id | "unread" | null(all)
  query: "",
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------- time helpers ----------
   Live API sends epoch seconds; demo-data.json uses "mins_ago". */
function tsToDate(v) {
  if (v == null) return new Date();
  return v > 1e8 ? new Date(v * 1000) : new Date(Date.now() - v * 60000);
}
function fmtTime(v) {
  const d = tsToDate(v), diff = (Date.now() - d.getTime()) / 60000;
  if (diff < 1) return "now";
  if (diff < 60) return `${Math.floor(diff)}m`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/* ---------- data loading ---------- */
async function fetchJSON(url, opts) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 4000);
  try {
    const res = await fetch(url, { ...opts, signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally { clearTimeout(timer); }
}

async function load() {
  if (API_BASE) {
    try {
      await fetchJSON(`${API_BASE}/api/health`);
      state.conversations = await fetchJSON(`${API_BASE}/api/conversations`);
      state.mode = "live";
      setStatus("live");
      if (state.activeId) await loadMessages(state.activeId);
      render();
      return;
    } catch (_) { /* fall through to demo */ }
  }
  const demo = await fetchJSON("demo-data.json");
  state.mode = "demo";
  setStatus("demo");
  // Normalize demo shape -> same shape the API returns.
  const now = Date.now();
  state.conversations = demo.conversations.map((c) => ({
    ...c,
    meta: PLATFORM_META[c.platform] || { name: c.platform, color: "#666", glyph: "??" },
    updated_at: now / 1000 - c.mins_ago * 60,
  })).sort((a, b) => b.updated_at - a.updated_at);
  for (const [cid, msgs] of Object.entries(demo.messages)) {
    state.messages[cid] = msgs.map((m) => ({ ...m, timestamp: now / 1000 - m.mins_ago * 60 }));
  }
  render();
}

async function loadMessages(cid) {
  if (state.mode === "live") {
    state.messages[cid] = await fetchJSON(`${API_BASE}/api/conversations/${cid}/messages`);
  }
  return state.messages[cid] || [];
}

async function openConversation(cid) {
  state.activeId = cid;
  await loadMessages(cid);
  const conv = state.conversations.find((c) => c.id === cid);
  if (conv && conv.unread_count > 0) {
    conv.unread_count = 0;
    if (state.mode === "live") {
      fetchJSON(`${API_BASE}/api/conversations/${cid}/read`, { method: "POST" }).catch(() => {});
    }
  }
  renderList(); renderThread();
}

async function sendMessage(text) {
  const cid = state.activeId;
  if (!cid || !text.trim()) return;
  if (state.mode === "live") {
    const msg = await fetchJSON(`${API_BASE}/api/conversations/${cid}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    state.messages[cid].push(msg);
  } else {
    const conv = state.conversations.find((c) => c.id === cid);
    const msg = {
      id: `local_${Date.now()}`, conversation_id: cid, platform: conv.platform,
      sender_name: "You", text, direction: "out", timestamp: Date.now() / 1000,
    };
    state.messages[cid].push(msg);
    conv.last_message = text;
    conv.updated_at = msg.timestamp;
  }
  renderList(); renderThread(true);
}

function setStatus(mode) {
  const pill = $("status-pill"), label = $("status-label");
  pill.classList.remove("pill-live", "pill-demo", "pill-connecting");
  if (mode === "live") { pill.classList.add("pill-live"); label.textContent = "LIVE"; pill.title = `Connected to ${API_BASE}`; }
  else { pill.classList.add("pill-demo"); label.textContent = "DEMO DATA"; pill.title = "API not reachable — showing bundled sample data"; }
}

/* ---------- rendering ---------- */
function initials(name) {
  return name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}

function visibleConvs() {
  let list = [...state.conversations];
  if (state.filter === "unread") list = list.filter((c) => c.unread_count > 0);
  else if (state.filter) list = list.filter((c) => c.platform === state.filter);
  if (state.query) {
    const q = state.query.toLowerCase();
    list = list.filter((c) =>
      c.title.toLowerCase().includes(q) || String(c.last_message).toLowerCase().includes(q));
  }
  return list.sort((a, b) => b.updated_at - a.updated_at);
}

function renderFilters() {
  const byPlatform = {};
  for (const c of state.conversations) {
    byPlatform[c.platform] = byPlatform[c.platform] ||
      { total: 0, unread: 0 };
    byPlatform[c.platform].total++;
    byPlatform[c.platform].unread += c.unread_count > 0 ? 1 : 0;
  }
  const rows = [{ key: null, label: "All inboxes", swatch: "linear-gradient(135deg,#4f8cff,#9b59ff)", ...{ total: state.conversations.length } },
                { key: "unread", label: "Unread", swatch: "var(--accent)" }];
  let html = "";
  for (const r of rows) {
    html += `<button class="filter-row ${state.filter === r.key ? "active" : ""}" data-filter="${r.key ?? ""}">
      <span class="filter-swatch" style="background:${r.swatch}"></span>${r.label}
      <span class="filter-count">${r.key === "unread"
        ? state.conversations.filter((c) => c.unread_count > 0).length : r.total}</span></button>`;
  }
  for (const [pid, meta] of Object.entries(PLATFORM_META)) {
    const stat = byPlatform[pid];
    if (!stat) continue;
    html += `<button class="filter-row ${state.filter === pid ? "active" : ""}" data-filter="${pid}">
      <span class="filter-swatch" style="background:${meta.color}"></span>${meta.name}
      <span class="filter-count ${stat.unread ? "unread" : ""}">${stat.unread ? `${stat.unread}●` : stat.total}</span></button>`;
  }
  $("platform-filters").innerHTML = html;
  $("platform-filters").querySelectorAll(".filter-row").forEach((btn) =>
    btn.addEventListener("click", () => {
      state.filter = btn.dataset.filter || null;
      renderFilters(); renderList();
    }));

  $("account-list").innerHTML = Object.entries(PLATFORM_META)
    .map(([pid, m]) => `<li><span class="swatch" style="background:${m.color}"></span>
      ${m.name}<span class="handle">@${pid}_biz</span></li>`).join("");

  const unreadTotal = state.conversations.reduce((n, c) => n + (c.unread_count > 0 ? c.unread_count : 0), 0);
  $("stat-line").textContent =
    `${state.conversations.length} conversations · ${unreadTotal} unread · ${state.mode.toUpperCase()} mode`;
}

function renderList() {
  const list = visibleConvs();
  if (!list.length) {
    $("conv-list").innerHTML = `<div class="empty-list">No conversations match.</div>`;
    return;
  }
  $("conv-list").innerHTML = list.map((c) => {
    const meta = c.meta || PLATFORM_META[c.platform] ||
      { name: c.platform, color: "#666", glyph: "??" };
    return `<div class="conv-row ${c.id === state.activeId ? "active" : ""} ${c.unread_count ? "unread" : ""}" data-cid="${esc(c.id)}">
      <div class="avatar" style="background:${meta.color}">${esc(initials(c.title))}</div>
      <div class="conv-main">
        <div class="conv-top">
          <span class="conv-name">${esc(c.title)}</span>
          <span class="platform-chip" style="color:${meta.color};border:1px solid ${meta.color}55">${esc(meta.glyph)}</span>
          <span class="conv-time">${fmtTime(c.updated_at)}</span>
        </div>
        <div class="conv-snippet">${esc(String(c.last_message || "").slice(0, 90))}</div>
      </div>
      ${c.unread_count ? `<span class="badge">${c.unread_count}</span>` : ""}
    </div>`;
  }).join("");
  $("conv-list").querySelectorAll(".conv-row").forEach((row) =>
    row.addEventListener("click", () => openConversation(row.dataset.cid)));
}

function renderThread(scrollToBottom) {
  const conv = state.conversations.find((c) => c.id === state.activeId);
  $("thread-empty").classList.toggle("hidden", !!conv);
  $("thread-active").classList.toggle("hidden", !conv);
  if (!conv) return;
  const meta = conv.meta || PLATFORM_META[conv.platform];
  $("thread-head").innerHTML = `
    <div class="avatar" style="background:${meta.color}">${esc(initials(conv.title))}</div>
    <div><div class="thread-title">${esc(conv.title)}</div>
    <div class="thread-sub">${esc(meta.name)} · via MessageFunnel</div></div>`;

  const msgs = state.messages[state.activeId] || [];
  const scroll = $("thread-scroll");
  scroll.innerHTML = msgs.map((m) => `
    <div class="bubble ${m.direction === "out" ? "out" : "in"}">
      ${m.direction === "in" && m.sender_name ? `<strong>${esc(m.sender_name)}</strong><br>` : ""}
      ${esc(m.text)}
      <span class="meta">${fmtTime(m.timestamp)}${m.direction === "out" ? " · delivered ✓" : ""}</span>
    </div>`).join("");
  if (scrollToBottom !== false) scroll.scrollTop = scroll.scrollHeight;
  const input = $("composer-input");
  input.placeholder = state.mode === "live" ? "Reply…" : "Reply (demo — stored locally)…";
}

function render() { renderFilters(); renderList(); renderThread(); }

/* ---------- wiring ---------- */
$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("composer-input");
  sendMessage(input.value);
  input.value = "";
});
$("refresh-btn").addEventListener("click", () => load().catch(console.error));
$("search").addEventListener("input", (e) => { state.query = e.target.value; renderList(); });

load().catch((err) => {
  console.error(err);
  $("status-label").textContent = "OFFLINE";
});
setInterval(() => { if (state.mode === "live") load().catch(() => {}); }, 20000);
