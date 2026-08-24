/* ============================================================
   MessageFunnel — auth + account connections (live mode only)
   Login/register gate + "Connected accounts" settings panel.
   Demo mode (no ?api= / MF_LIVE_API) never activates this file.
   ============================================================ */

(function () {
  'use strict';

  var API = (function () {
    try {
      var q = new URLSearchParams(window.location.search).get('api');
      return (q || window.MF_LIVE_API || '').replace(/\/+$/, '');
    } catch (e) { return ''; }
  })();

  var TOKEN_KEY = 'mf_token';
  var USER_KEY = 'mf_user';

  function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; } }
  function setSession(token, user) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
    } catch (e) { /* private mode */ }
  }
  function clearSession() {
    try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch (e) {}
  }
  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || '{}'); } catch (e) { return {}; }
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers, { 'Authorization': 'Bearer ' + getToken() });
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    return fetch(API + path, opts).then(function (r) {
      if (r.status === 401) { clearSession(); showAuth('Your session expired — please log in again.'); throw new Error(401); }
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (b) {
        throw new Error((b && b.detail) || ('HTTP ' + r.status));
      });
      return r.json();
    });
  }

  /* ================= auth gate ================= */

  function ensureAuthed() {
    if (!API) return Promise.resolve(true);
    if (!getToken()) { showAuth(); return Promise.resolve(false); }
    return api('/api/auth/me').then(function () { return true; }).catch(function (e) {
      if (e.message !== '401') showAuth(e.message);
      return false;
    });
  }

  function showAuth(message) {
    if (document.getElementById('mf-auth')) return;
    var wrap = document.createElement('div');
    wrap.id = 'mf-auth';
    wrap.innerHTML =
      '<div class="mf-auth-card">' +
      '<div class="brand" style="justify-content:center;margin-bottom:6px"><span class="brand-name">Message<b>Funnel</b></span></div>' +
      '<p class="mf-auth-sub">One inbox for every platform.</p>' +
      (message ? '<div class="mf-auth-msg">' + esc(message) + '</div>' : '') +
      '<div class="mf-tabs"><button type="button" id="mfTabLogin" class="active">Log in</button>' +
      '<button type="button" id="mfTabReg">Create account</button></div>' +
      '<form id="mfLoginForm">' +
      '<input name="email" type="email" placeholder="Email" required autocomplete="email">' +
      '<input name="password" type="password" placeholder="Password" required autocomplete="current-password">' +
      '<button type="submit" class="mf-primary">Log in</button>' +
      '</form>' +
      '<form id="mfRegForm" hidden>' +
      '<input name="display_name" type="text" placeholder="Display name (optional)" autocomplete="name">' +
      '<input name="email" type="email" placeholder="Email" required autocomplete="email">' +
      '<input name="password" type="password" placeholder="Password (min 8 chars)" required minlength="8" autocomplete="new-password">' +
      '<button type="submit" class="mf-primary">Create account</button>' +
      '</form>' +
      '</div>';
    document.body.appendChild(wrap);

    var tabL = document.getElementById('mfTabLogin');
    var tabR = document.getElementById('mfTabReg');
    var formL = document.getElementById('mfLoginForm');
    var formR = document.getElementById('mfRegForm');

    tabL.addEventListener('click', function () {
      tabL.classList.add('active'); tabR.classList.remove('active');
      formL.hidden = false; formR.hidden = true;
    });
    tabR.addEventListener('click', function () {
      tabR.classList.add('active'); tabL.classList.remove('active');
      formR.hidden = false; formL.hidden = true;
    });

    formL.addEventListener('submit', function (e) {
      e.preventDefault();
      submit(formL, '/api/auth/login');
    });
    formR.addEventListener('submit', function (e) {
      e.preventDefault();
      submit(formR, '/api/auth/register');
    });

    function submit(form, path) {
      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true; btn.textContent = '…';
      fetch(API + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email.value.trim(),
          password: form.password.value,
          display_name: (form.display_name && form.display_name.value.trim()) || ''
        })
      }).then(function (r) {
        return r.json().then(function (b) { return { ok: r.ok, body: b }; });
      }).then(function (res) {
        if (!res.ok) throw new Error(res.body.detail || 'Request failed');
        setSession(res.body.token, res.body.user);
        window.location.reload();
      }).catch(function (err) {
        btn.disabled = false; btn.textContent = path.indexOf('register') !== -1 ? 'Create account' : 'Log in';
        var msg = document.querySelector('.mf-auth-msg') || wrap.querySelector('.mf-auth-card');
        var div = document.createElement('div');
        div.className = 'mf-auth-msg';
        div.textContent = err.message;
        msg.parentNode.insertBefore(div, msg);
      });
    }
  }

  /* ================= connections settings panel ================= */

  var PLATFORM_GLYPH = {
    messenger: 'M', instagram: 'IG', tiktok: 'TT', whatsapp: 'WA', telegram: 'TG', x: 'X'
  };

  function openSettings() {
    closeSettings();
    var panel = document.createElement('div');
    panel.id = 'mf-settings';
    panel.innerHTML =
      '<div class="mf-settings-card" role="dialog" aria-label="Connected accounts">' +
      '<header><h2>Connected accounts</h2>' +
      '<span class="mf-settings-user">' + esc(getUser().display_name || getUser().email || '') + '</span>' +
      '<button type="button" class="icon-btn" id="mfSettingsClose" aria-label="Close">✕</button></header>' +
      '<p class="mf-settings-sub">All your platform credentials, in one place. ' +
      'Stored encrypted on the server; shown masked after saving.</p>' +
      '<div id="mfConnList" class="mf-conn-list"><p class="mf-loading">Loading…</p></div>' +
      '<footer><button type="button" class="mf-danger" id="mfLogout">Log out</button></footer>' +
      '</div>';
    document.body.appendChild(panel);

    document.getElementById('mfSettingsClose').addEventListener('click', closeSettings);
    document.getElementById('mfLogout').addEventListener('click', function () {
      clearSession(); window.location.reload();
    });
    panel.addEventListener('click', function (e) { if (e.target === panel) closeSettings(); });

    Promise.all([api('/api/platforms'), api('/api/connections')])
      .then(function (results) { renderConnections(panel, results[0], results[1]); })
      .catch(function (e) {
        var list = document.getElementById('mfConnList');
        if (list) list.innerHTML = '<p class="mf-error">' + esc(e.message) + '</p>';
      });
  }

  function closeSettings() {
    var old = document.getElementById('mf-settings');
    if (old) old.parentNode.removeChild(old);
  }

  function renderConnections(panel, platforms, connections) {
    var byPlatform = {};
    connections.forEach(function (c) { byPlatform[c.platform] = c; });

    var list = document.getElementById('mfConnList');
    list.innerHTML = platforms.map(function (p) {
      var conn = byPlatform[p.id];
      var maskedHTML = '';
      if (conn && conn.masked && Object.keys(conn.masked).length) {
        maskedHTML = '<div class="mf-masked">' + Object.keys(conn.masked).map(function (k) {
          return '<code>' + esc(k) + '</code><span>' + esc(conn.masked[k]) + '</span>';
        }).join('') + '</div>';
      }
      var fields = p.credential_fields.map(function (f) {
        return '<label>' + esc(f.replace(/_/g, ' ')) +
          '<input name="' + esc(f) + '" type="password" placeholder="' +
          (conn && conn.masked && conn.masked[f] ? esc(conn.masked[f]) : 'paste value') +
          '" autocomplete="off"></label>';
      }).join('');
      return (
        '<section class="mf-conn' + (conn ? ' connected' : '') + '" data-platform="' + esc(p.id) + '">' +
        '<header>' +
        '<span class="p-icon" style="background:' + esc(p.color) + '">' + (PLATFORM_GLYPH[p.id] || '?') + '</span>' +
        '<strong>' + esc(p.name) + '</strong>' +
        '<span class="mf-status">' + (conn ? '● connected' : '○ not connected') + '</span>' +
        '</header>' +
        '<form class="mf-conn-form">' +
        '<label>handle / page name<input name="__handle" type="text" value="' +
        esc(conn ? conn.handle : '') + '" placeholder="@yourbusiness"></label>' +
        fields +
        '<div class="mf-conn-actions">' +
        '<button type="submit" class="mf-primary">' + (conn ? 'Update' : 'Connect') + '</button>' +
        (conn ? '<button type="button" class="mf-test">Test</button>' +
                '<button type="button" class="mf-danger mf-disconnect">Disconnect</button>' : '') +
        '</div>' +
        '<p class="mf-result" hidden></p>' +
        '</form>' +
        '</section>'
      );
    }).join('');

    list.querySelectorAll('.mf-conn').forEach(function (sec) {
      var platformId = sec.getAttribute('data-platform');
      var form = sec.querySelector('.mf-conn-form');
      var result = sec.querySelector('.mf-result');

      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var creds = {};
        var empty = true;
        p_fields(platforms, platformId).forEach(function (f) {
          var v = form.elements[f].value.trim();
          if (v) { creds[f] = v; empty = false; }
        });
        // Updating an existing connection with all-empty fields keeps old creds.
        if (empty && !byPlatform[platformId]) {
          result.textContent = 'Enter at least one credential value.';
          result.hidden = false;
          return;
        }
        save(platformId, form.elements['__handle'].value.trim(), creds, result);
      });

      var testBtn = sec.querySelector('.mf-test');
      if (testBtn) testBtn.addEventListener('click', function () {
        api('/api/connections/' + byPlatform[platformId].id + '/test', { method: 'POST' })
          .then(function (b) {
            result.textContent = (b.ok ? '✓ ' : '✗ ') + b.reason;
            result.hidden = false;
          }).catch(function (err) {
            result.textContent = '✗ ' + err.message; result.hidden = false;
          });
      });

      var discBtn = sec.querySelector('.mf-disconnect');
      if (discBtn) discBtn.addEventListener('click', function () {
        api('/api/connections/' + byPlatform[platformId].id, { method: 'DELETE' })
          .then(function () { openSettings(); })  // re-render
          .catch(function (err) {
            result.textContent = '✗ ' + err.message; result.hidden = false;
          });
      });
    });

    function p_fields(platforms_, pid) {
      for (var i = 0; i < platforms_.length; i++) {
        if (platforms_[i].id === pid) return platforms_[i].credential_fields;
      }
      return [];
    }

    function save(pid, handle, creds, resultEl) {
      api('/api/connections/' + pid, { method: 'PUT', body: { handle: handle, credentials: creds } })
        .then(function () {
          resultEl.textContent = '✓ Saved (encrypted).';
          resultEl.hidden = false;
          setTimeout(function () { openSettings(); }, 700);  // refresh masked view
        })
        .catch(function (err) {
          resultEl.textContent = '✗ ' + err.message;
          resultEl.hidden = false;
        });
    }
  }

  /* ================= wiring into the shell ================= */

  window.MF_AUTH = {
    getToken: getToken,
    api: api,
    openSettings: openSettings,
    isActive: function () { return !!API; },
    /** Called by app.js on any 401 from its own fetches. */
    handleUnauthorized: function () {
      clearSession();
      showAuth('Your session expired — please log in again.');
    }
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (!API) return;  // demo mode — nothing to wire

    // Gear button in the topbar
    var bar = document.querySelector('.topbar-right');
    if (bar) {
      var gear = document.createElement('button');
      gear.className = 'icon-btn';
      gear.type = 'button';
      gear.setAttribute('aria-label', 'Connected accounts');
      gear.title = 'Connected accounts';
      gear.textContent = '⚙';
      gear.addEventListener('click', openSettings);
      bar.insertBefore(gear, bar.firstChild);

      var pill = bar.querySelector('.status-pill');
      if (pill) {
        var u = getUser();
        if (u.display_name || u.email) {
          pill.title = 'Logged in as ' + (u.display_name || u.email);
        }
      }
    }

    ensureAuthed().then(function (ok) {
      if (ok && window.MF_AUTH._resolveAuthed) window.MF_AUTH._resolveAuthed();
    });
  });
})();
