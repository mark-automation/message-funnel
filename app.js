/* ============================================================
   MessageFunnel — app logic (vanilla JS, no dependencies)
   State lives in memory; sent messages + read receipts persist
   to localStorage. Demo replies are clearly simulated.
   ============================================================ */

(function () {
  'use strict';

  var LS_SENT = 'mf_sent_v1';
  var LS_READ = 'mf_read_v1';

  var state = {
    convos: [],          // normalized: {id, platformId, name, color, icon, messages:[{from,text,ts}], lastTs}
    readSet: {},         // convo id -> true (opened at least once)
    activeId: null,
    platformFilter: 'all',
    query: ''
  };

  /* ---------- helpers ---------- */

  function $(sel) { return document.querySelector(sel); }

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function loadJSON(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }

  function saveJSON(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* private mode */ }
  }

  function initials(name) {
    var parts = name.replace(/^@/, '').split(/[\s._-]+/).filter(Boolean);
    var a = (parts[0] || '?').charAt(0);
    var b = parts.length > 1 ? parts[parts.length - 1].charAt(0) : '';
    return (a + b).toUpperCase();
  }

  function hue(name) {
    var h = 0;
    for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
    return h;
  }

  function fmtTime(ts) {
    return new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }

  function dayKey(ts) {
    var d = new Date(ts);
    return d.getFullYear() + '-' + d.getMonth() + '-' + d.getDate();
  }

  function dayLabel(ts) {
    var today = dayKey(Date.now());
    var yesterday = dayKey(Date.now() - 86400000);
    var k = dayKey(ts);
    if (k === today) return 'Today';
    if (k === yesterday) return 'Yesterday';
    return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function relTime(ts) {
    var diff = Math.floor((Date.now() - ts) / 60000);
    if (diff < 1) return 'now';
    if (diff < 60) return diff + 'm';
    if (diff < 1440) return Math.floor(diff / 60) + 'h';
    var days = Math.floor(diff / 1440);
    if (days === 1) return '1d';
    if (days < 7) return days + 'd';
    return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function avatarHTML(convo, size) {
    var h = hue(convo.name);
    var bg = 'background:linear-gradient(135deg,hsl(' + h + ',62%,52%),hsl(' + ((h + 40) % 360) + ',62%,44%))';
    var badge =
      '<span class="p-badge" style="background:' + convo.color + '">' + convo.icon + '</span>';
    return '<span class="avatar" style="' + bg + '" aria-hidden="true">' +
      esc(initials(convo.name)) +
      (size !== 'plain' ? badge : '') +
      '</span>';
  }

  function unreadCount(convo) {
    if (state.readSet[convo.id]) return 0;
    return convo.unreadSeed || 0;
  }

  function totalUnread() {
    return state.convos.reduce(function (n, c) { return n + unreadCount(c); }, 0);
  }

  /* ---------- build state from connectors ---------- */

  function loadConversations() {
    var convos = [];
    window.MF_CONNECTORS.forEach(function (conn) {
      conn.fetchConversations().forEach(function (c) {
        var messages = c.messages.map(function (m) {
          return { from: m.from, text: m.text, ts: Date.now() - m.minutesAgo * 60000 };
        });
        // merge locally-sent messages from a previous visit
        var savedSent = loadJSON(LS_SENT, {})[c.id];
        if (savedSent) savedSent.forEach(function (m) { messages.push(m); });
        messages.sort(function (a, b) { return a.ts - b.ts; });

        convos.push({
          id: c.id,
          platformId: conn.id,
          name: c.contact.name,
          color: conn.color,
          icon: conn.icon,
          unreadSeed: c.unreadCount || 0,
          messages: messages,
          lastTs: messages.length ? messages[messages.length - 1].ts : 0
        });
      });
    });
    convos.sort(function (a, b) { return b.lastTs - a.lastTs; });
    state.convos = convos;
    state.readSet = loadJSON(LS_READ, {});
  }

  function persistRead() {
    saveJSON(LS_READ, state.readSet);
  }

  function persistSent(convo, msg) {
    var all = loadJSON(LS_SENT, {});
    if (!all[convo.id]) all[convo.id] = [];
    all[convo.id].push(msg);
    saveJSON(LS_SENT, all);
  }

  function findConvo(id) {
    for (var i = 0; i < state.convos.length; i++) {
      if (state.convos[i].id === id) return state.convos[i];
    }
    return null;
  }

  /* ---------- rendering: rail ---------- */

  function renderRail() {
    var counts = {};
    state.convos.forEach(function (c) {
      counts[c.platformId] = (counts[c.platformId] || 0) + unreadCount(c);
    });

    var html = '';
    var total = totalUnread();

    html += '<button class="rail-item all' + (state.platformFilter === 'all' ? ' active' : '') +
      '" data-platform="all" type="button">' +
      '<span class="p-icon"><svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">' +
      '<path d="M3 4h18l-7 8v6l-4 2v-8L3 4z"/></svg></span>' +
      '<span class="rail-label">All</span>' +
      (total ? '<span class="rail-count">' + total + '</span>' : '') +
      '</button>';

    window.MF_CONNECTORS.forEach(function (conn) {
      html += '<button class="rail-item' + (state.platformFilter === conn.id ? ' active' : '') +
        '" data-platform="' + conn.id + '" type="button" title="' + esc(conn.name) + '">' +
        '<span class="p-icon" style="background:' + conn.color + '">' + conn.icon + '</span>' +
        '<span class="rail-label">' + esc(conn.name) + '</span>' +
        (counts[conn.id] ? '<span class="rail-count">' + counts[conn.id] + '</span>' : '') +
        '</button>';
    });

    $('#rail').innerHTML = html;
  }

  /* ---------- rendering: conversation list ---------- */

  function visibleConvos() {
    return state.convos.filter(function (c) {
      if (state.platformFilter !== 'all' && c.platformId !== state.platformFilter) return false;
      if (!state.query) return true;
      var q = state.query.toLowerCase();
      if (c.name.toLowerCase().indexOf(q) !== -1) return true;
      return c.messages.some(function (m) { return m.text.toLowerCase().indexOf(q) !== -1; });
    }).sort(function (a, b) { return b.lastTs - a.lastTs; });
  }

  function renderList() {
    var list = visibleConvos();
    var ul = $('#convoList');

    if (!list.length) {
      ul.innerHTML = '<li class="empty-results">No conversations match your search.</li>';
      return;
    }

    ul.innerHTML = list.map(function (c) {
      var unread = unreadCount(c);
      var last = c.messages[c.messages.length - 1];
      var snippet = last ? (last.from === 'me' ? 'You: ' : '') + last.text : '';
      return '<li><button class="convo-item' +
        (unread ? ' unread' : '') +
        (state.activeId === c.id ? ' active' : '') +
        '" data-id="' + esc(c.id) + '" type="button">' +
        avatarHTML(c) +
        '<span class="convo-main">' +
        '<span class="convo-row1"><span class="convo-name">' + esc(c.name) + '</span>' +
        '<span class="convo-time">' + (last ? relTime(last.ts) : '') + '</span></span>' +
        '<span class="convo-preview"><span class="convo-snippet">' + esc(snippet) + '</span>' +
        (unread ? '<span class="unread-dot">' + unread + '</span>' : '') +
        '</span>' +
        '</span>' +
        '</button></li>';
    }).join('');
  }

  /* ---------- rendering: thread ---------- */

  function renderThread() {
    var pane = $('#threadPane');
    var convo = state.activeId ? findConvo(state.activeId) : null;

    if (!convo) {
      pane.innerHTML =
        '<div class="empty-state" id="emptyState">' +
        '<div class="empty-art" aria-hidden="true">📬</div>' +
        '<p>Select a conversation to read it here.</p>' +
        '<p class="empty-sub">All your platforms, funneled into one inbox.</p>' +
        '</div>';
      return;
    }

    var msgsHTML = '';
    var prevDay = null;
    convo.messages.forEach(function (m) {
      var k = dayKey(m.ts);
      if (k !== prevDay) {
        msgsHTML += '<div class="day-sep">' + esc(dayLabel(m.ts)) + '</div>';
        prevDay = k;
      }
      msgsHTML += '<div class="msg ' + (m.from === 'me' ? 'me' : 'them') + '">' + esc(m.text) + '</div>';
      msgsHTML += '<div class="msg-time">' + esc(fmtTime(m.ts)) + '</div>';
    });

    var conn = window.MF_CONNECTORS.filter(function (x) { return x.id === convo.platformId; })[0];

    pane.innerHTML =
      '<div class="thread">' +
      '<header class="thread-head">' +
      '<button class="back-btn" id="backBtn" type="button" aria-label="Back to conversations">←</button>' +
      '<span class="thread-who">' + avatarHTML(convo, 'plain') +
      '<span><span class="thread-name">' + esc(convo.name) + '</span><br>' +
      '<span class="thread-platform"><span style="color:' + conn.color + ';display:inline-flex">' + conn.icon + '</span> via ' + esc(conn.name) + '</span>' +
      '</span></span>' +
      '</header>' +
      '<div class="messages" id="messages" aria-live="polite">' + msgsHTML + '</div>' +
      '<form class="composer" id="composer">' +
      '<input id="composerInput" type="text" placeholder="Message ' + esc(convo.name) + '…" autocomplete="off" aria-label="Message text">' +
      '<button class="send-btn" type="submit" aria-label="Send message">➤</button>' +
      '</form>' +
      '</div>';

    var box = $('#messages');
    box.scrollTop = box.scrollHeight;

    $('#backBtn').addEventListener('click', closeThreadMobile);

    $('#composer').addEventListener('submit', function (e) {
      e.preventDefault();
      sendCurrent();
    });
  }

  function refreshAll() {
    renderRail();
    renderList();
    updateTitle();
  }

  function updateTitle() {
    var n = totalUnread();
    document.title = n
      ? '(' + n + ') MessageFunnel — Unified Inbox'
      : 'MessageFunnel — Unified Inbox';
  }

  /* ---------- actions ---------- */

  function openConvo(id) {
    state.activeId = id;
    if (!state.readSet[id]) {
      state.readSet[id] = true;
      persistRead();
    }
    renderThread();
    refreshAll();
    if (window.matchMedia('(max-width: 640px)').matches) {
      document.body.classList.add('thread-open');
    }
    var input = $('#composerInput');
    if (input && window.matchMedia('(min-width: 641px)').matches) input.focus();
  }

  function closeThreadMobile() {
    document.body.classList.remove('thread-open');
    state.activeId = null;
    renderThread();
    refreshAll();
  }

  function sendCurrent() {
    var input = $('#composerInput');
    var convo = findConvo(state.activeId);
    if (!input || !convo) return;
    var text = input.value.trim();
    if (!text) return;

    var msg = { from: 'me', text: text, ts: Date.now() };
    convo.messages.push({ from: 'me', text: msg.text, ts: msg.ts });
    convo.lastTs = msg.ts;
    persistSent(convo, msg);
    input.value = '';
    renderThread();
    refreshAll();

    simulateReply(convo);
  }

  function simulateReply(convo) {
    var pool = window.MF_DEMO_REPLIES[convo.platformId] || ['👍'];
    var reply = pool[Math.floor(Math.random() * pool.length)];
    var box = $('#messages');
    if (!box) return;

    setTimeout(function () {
      if (state.activeId !== convo.id) return;
      var t = document.createElement('div');
      t.className = 'typing';
      t.setAttribute('aria-label', 'Typing…');
      t.innerHTML = '<span></span><span></span><span></span>';
      box.appendChild(t);
      box.scrollTop = box.scrollHeight;

      setTimeout(function () {
        if (t.parentNode) t.parentNode.removeChild(t);
        if (state.activeId !== convo.id) return;
        var now = Date.now();
        convo.messages.push({ from: 'them', text: reply, ts: now });
        convo.lastTs = now;
        renderThread();
        refreshAll();
      }, 1100 + Math.random() * 900);
    }, 500);
  }

  function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    saveJSON('mf_theme', t);
  }

  /* ---------- events ---------- */

  function bindEvents() {
    $('#rail').addEventListener('click', function (e) {
      var btn = e.target.closest('.rail-item');
      if (!btn) return;
      state.platformFilter = btn.getAttribute('data-platform');
      renderRail();
      renderList();
    });

    $('#convoList').addEventListener('click', function (e) {
      var item = e.target.closest('.convo-item');
      if (!item) return;
      openConvo(item.getAttribute('data-id'));
    });

    $('#searchBox').addEventListener('input', function () {
      state.query = this.value.trim();
      renderList();
    });

    $('#themeToggle').addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      setTheme(cur === 'dark' ? 'light' : 'dark');
    });

    window.addEventListener('resize', function () {
      if (!window.matchMedia('(max-width: 640px)').matches) {
        document.body.classList.remove('thread-open');
      }
    });
  }

  /* ---------- boot ---------- */

  loadConversations();
  renderRail();
  renderList();
  renderThread();
  bindEvents();
  updateTitle();
})();
