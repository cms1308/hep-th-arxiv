/* 별표 기기 간 동기화 — GitHub Gist 하나를 공용 저장소로 쓴다.
 *
 * stars.js 다음에 로드해야 한다 (window.StarStore 가 있어야 한다).
 * 설정하지 않으면 아무 일도 하지 않고, 별표는 그 브라우저에만 남는다.
 *
 * 설정값 (hepth:sync): { token, gistId } — 기기마다 한 번 넣는다.
 * gist 파일 hep-th-stars.json 에 stars.js 와 같은 모양의 상태를 통째로 둔다.
 *
 * 합치기 규칙: 별표한 시각과 해제한 시각을 비교해 나중 것이 이긴다. 두 기기에서
 * 서로 다른 논문을 별표하면 둘 다 남는다(합집합). 오래된 삭제 표시는 정리한다.
 */
(function () {
  'use strict';

  var CONFIG_KEY = 'hepth:sync';
  var STATUS_KEY = 'hepth:sync-status';
  var GIST_FILE = 'hep-th-stars.json';
  var API = 'https://api.github.com';
  var PUSH_DELAY_MS = 2500;
  var TOMBSTONE_TTL_MS = 90 * 24 * 60 * 60 * 1000;   // 90일

  if (!window.StarStore) {
    console.warn('[sync] stars.js 가 먼저 로드되어야 합니다.');
    return;
  }
  var Store = window.StarStore;

  /* ---------- 설정 ---------- */

  var readJson = function (key) {
    try {
      var raw = window.localStorage.getItem(key);
      var parsed = raw ? JSON.parse(raw) : null;
      return (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : null;
    } catch (err) {
      console.warn('[sync] ' + key + ' 을 읽지 못했습니다:', err);
      return null;
    }
  };

  var writeJson = function (key, value) {
    try {
      if (value === null) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (err) {
      console.warn('[sync] ' + key + ' 을 저장하지 못했습니다:', err);
      return false;
    }
  };

  var readConfig = function () {
    var c = readJson(CONFIG_KEY);
    if (!c || typeof c.token !== 'string' || !c.token) return null;
    if (typeof c.gistId !== 'string' || !c.gistId) return null;
    return { token: c.token, gistId: c.gistId };
  };

  /* ---------- 합치기 (순수 함수) ---------- */

  var ts = function (v) { return typeof v === 'number' && isFinite(v) ? v : 0; };

  var mergeStates = function (a, b, now) {
    var sides = [a || {}, b || {}];
    var cutoff = (now || Date.now()) - TOMBSTONE_TTL_MS;

    var removed = {};
    sides.forEach(function (s) {
      Object.keys(s.removed || {}).forEach(function (id) {
        removed[id] = Math.max(ts(removed[id]), ts(s.removed[id]));
      });
    });

    var papers = {};
    sides.forEach(function (s) {
      Object.keys(s.papers || {}).forEach(function (id) {
        var entry = s.papers[id];
        if (!entry || typeof entry !== 'object') return;
        if (!papers[id] || ts(entry.ts) > ts(papers[id].ts)) papers[id] = entry;
      });
    });

    /* 해제가 별표보다 나중이면 (같은 시각이면 해제가) 이긴다. */
    Object.keys(removed).forEach(function (id) {
      if (papers[id] && ts(papers[id].ts) <= removed[id]) delete papers[id];
    });

    /* 다시 별표됐거나 충분히 오래된 삭제 표시는 들고 다닐 필요가 없다. */
    var keptRemoved = {};
    Object.keys(removed).forEach(function (id) {
      if (!papers[id] && removed[id] >= cutoff) keptRemoved[id] = removed[id];
    });

    return { version: 1, papers: papers, removed: keptRemoved };
  };

  /* ---------- GitHub Gist ---------- */

  var apiFetch = function (path, token, options) {
    var opts = Object.assign({}, options, {
      headers: Object.assign({
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      }, (options || {}).headers)
    });
    return window.fetch(API + path, opts).then(function (res) {
      if (res.ok) return res.json();
      var reason = { 401: '토큰이 잘못되었거나 만료되었습니다.',
                     403: '토큰 권한이 모자라거나 요청 한도를 넘었습니다.',
                     404: 'gist 를 찾을 수 없습니다. 주소나 토큰 권한을 확인하세요.',
                     422: 'GitHub 가 요청을 거부했습니다.' }[res.status];
      throw new Error(reason || ('GitHub 응답 ' + res.status));
    });
  };

  var parseGist = function (gist) {
    var file = gist && gist.files && gist.files[GIST_FILE];
    if (!file) return { version: 1, papers: {}, removed: {} };
    /* 1MB 를 넘으면 content 가 잘려 오므로 원본을 따로 받는다. */
    var content = file.truncated
      ? window.fetch(file.raw_url).then(function (r) { return r.text(); })
      : Promise.resolve(file.content);
    return Promise.resolve(content).then(function (text) {
      try {
        return JSON.parse(text);
      } catch (err) {
        throw new Error('gist 의 내용을 읽을 수 없습니다 (JSON 이 아닙니다).');
      }
    });
  };

  var pull = function (cfg) {
    return apiFetch('/gists/' + cfg.gistId, cfg.token).then(parseGist);
  };

  var push = function (cfg, state) {
    var files = {};
    files[GIST_FILE] = { content: JSON.stringify(state, null, 1) };
    return apiFetch('/gists/' + cfg.gistId, cfg.token, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: files })
    });
  };

  var createGist = function (token, state) {
    var files = {};
    files[GIST_FILE] = { content: JSON.stringify(state, null, 1) };
    return apiFetch('/gists', token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        public: false,
        description: 'arXiv hep-th 데일리 브리핑 — 별표 목록',
        files: files
      })
    });
  };

  /* ---------- 동기화 ---------- */

  var statusListeners = [];
  var onStatus = function (fn) { statusListeners.push(fn); };
  var setStatus = function (status) {
    writeJson(STATUS_KEY, status);
    statusListeners.forEach(function (fn) {
      try { fn(status); } catch (err) { console.warn('[sync] 상태 표시 실패:', err); }
    });
  };
  var readStatus = function () { return readJson(STATUS_KEY); };

  var inFlight = null;

  var syncNow = function () {
    var cfg = readConfig();
    if (!cfg) return Promise.resolve(null);
    if (inFlight) return inFlight;

    setStatus({ state: 'syncing' });
    inFlight = pull(cfg).then(function (remote) {
      var merged = mergeStates(Store.state(), remote);
      Store.replaceState(merged, 'remote');
      return push(cfg, merged).then(function () {
        setStatus({ state: 'ok', at: Date.now(), count: Object.keys(merged.papers).length });
        return merged;
      });
    }).catch(function (err) {
      console.warn('[sync] 동기화 실패:', err);
      setStatus({ state: 'error', at: Date.now(), message: err.message || String(err) });
      return null;
    }).then(function (result) {
      inFlight = null;
      return result;
    });

    return inFlight;
  };

  var pushTimer = null;
  var schedulePush = function () {
    if (!readConfig()) return;
    if (pushTimer) window.clearTimeout(pushTimer);
    pushTimer = window.setTimeout(function () { pushTimer = null; syncNow(); }, PUSH_DELAY_MS);
  };

  Store.onChange(function (origin) { if (origin === 'local') schedulePush(); });

  /* 탭을 닫거나 숨기기 전에 미뤄둔 밀어올리기를 흘려보낸다. */
  window.addEventListener('pagehide', function () {
    if (!pushTimer) return;
    window.clearTimeout(pushTimer);
    pushTimer = null;
    syncNow();
  });

  /* ---------- 설정 화면 (모아보기 페이지에만 있다) ---------- */

  var PANEL_CSS = [
    '#sync-panel{background:var(--card);border:1px solid var(--line);border-radius:12px;',
    ' padding:16px 18px;margin-bottom:18px;box-shadow:var(--shadow);font-size:13.5px}',
    '#sync-panel h3{margin:0 0 4px;font-size:14px;font-weight:640;letter-spacing:-.01em}',
    '#sync-panel .hint{color:var(--muted);font-size:12.5px;line-height:1.7;margin:0 0 12px}',
    '#sync-panel .hint a{color:var(--accent)}',
    '#sync-panel .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:9px}',
    '#sync-panel input{flex:1 1 260px;min-width:0;padding:7px 10px;border:1px solid var(--line);',
    ' border-radius:8px;background:var(--bg);color:var(--ink);font:inherit;font-size:12.5px}',
    '#sync-panel .stat{color:var(--muted);font-size:12.5px}',
    '#sync-panel .stat.err{color:#c2410c}',
    '@media (prefers-color-scheme:dark){#sync-panel .stat.err{color:#fb923c}}',
    '#sync-panel details{margin-top:10px}',
    '#sync-panel summary{cursor:pointer;color:var(--muted);font-size:12.5px}',
    '#sync-panel ol{margin:8px 0 0;padding-left:20px;color:var(--muted);',
    ' font-size:12.5px;line-height:1.85}'
  ].join('\n');

  var el = function (tag, cls, txt) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (txt !== undefined) node.textContent = txt;
    return node;
  };

  var button = function (label, onClick) {
    var b = el('button', 'tbtn', label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  };

  var statusText = function (status) {
    if (!status) return '아직 동기화한 적이 없습니다.';
    if (status.state === 'syncing') return '동기화 중…';
    if (status.state === 'error') return '동기화 실패 — ' + status.message;
    if (status.state === 'ok') {
      var when = new Date(status.at).toLocaleString('ko-KR');
      return when + ' 에 동기화됨 · ' + status.count + '편';
    }
    return '';
  };

  var initPanel = function (panel) {
    var style = document.createElement('style');
    style.textContent = PANEL_CSS;
    document.head.appendChild(style);

    var render = function () {
      var cfg = readConfig();
      panel.textContent = '';
      panel.appendChild(el('h3', null, '기기 간 동기화'));

      var stat = el('div', 'stat', statusText(readStatus()));
      if (cfg) {
        var hint = el('p', 'hint');
        hint.appendChild(document.createTextNode('별표를 비공개 gist 에 보관합니다 · '));
        var link = el('a', null, 'gist 열기');
        link.href = 'https://gist.github.com/' + cfg.gistId;
        link.target = '_blank';
        link.rel = 'noopener';
        hint.appendChild(link);
        panel.appendChild(hint);
        panel.appendChild(stat);

        var row = el('div', 'row');
        row.appendChild(button('지금 동기화', function () { syncNow(); }));
        row.appendChild(button('연결 해제', function () {
          if (!window.confirm('이 기기에서 동기화를 끊습니다. 별표 자체는 남습니다.')) return;
          writeJson(CONFIG_KEY, null);
          writeJson(STATUS_KEY, null);
          render();
        }));
        panel.appendChild(row);
        return;
      }

      var hint = el('p', 'hint');
      hint.appendChild(document.createTextNode(
        '지금은 별표가 이 브라우저에만 저장됩니다. 아래에 토큰을 넣으면 비공개 gist 를 ' +
        '통해 다른 기기와 같은 목록을 봅니다. 기기마다 한 번씩 넣으면 됩니다.'));
      panel.appendChild(hint);

      var tokenInput = el('input');
      tokenInput.type = 'password';
      tokenInput.placeholder = 'GitHub 토큰 (gist 권한)';
      tokenInput.autocomplete = 'off';
      var tokenRow = el('div', 'row');
      tokenRow.appendChild(tokenInput);
      panel.appendChild(tokenRow);

      var gistInput = el('input');
      gistInput.type = 'text';
      gistInput.placeholder = 'gist 주소 또는 ID (두 번째 기기부터. 비우면 새로 만듭니다)';
      gistInput.autocomplete = 'off';
      var gistRow = el('div', 'row');
      gistRow.appendChild(gistInput);
      panel.appendChild(gistRow);

      panel.appendChild(stat);

      var connect = function () {
        var token = tokenInput.value.trim();
        if (!token) { setStatus({ state: 'error', at: Date.now(), message: '토큰을 넣어 주세요.' }); return; }
        /* 주소를 통째로 붙여넣어도 되게 마지막 조각만 쓴다. */
        var gistId = gistInput.value.trim().replace(/[/?#].*$/, '').split('/').pop();
        setStatus({ state: 'syncing' });

        var ready = gistId
          ? Promise.resolve(gistId)
          : createGist(token, Store.state()).then(function (g) { return g.id; });

        ready.then(function (id) {
          writeJson(CONFIG_KEY, { token: token, gistId: id });
          return syncNow();
        }).then(function () {
          render();
        }).catch(function (err) {
          console.warn('[sync] 연결 실패:', err);
          writeJson(CONFIG_KEY, null);
          setStatus({ state: 'error', at: Date.now(), message: err.message || String(err) });
        });
      };

      var row = el('div', 'row');
      row.appendChild(button('연결', connect));
      panel.appendChild(row);

      var how = el('details');
      how.appendChild(el('summary', null, '토큰 만드는 법'));
      var ol = el('ol');
      [
        'github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens',
        'Generate new token — 이름은 아무거나, 만료일은 원하는 대로',
        'Account permissions 에서 Gists 를 Read and write 로 (다른 권한은 주지 마세요)',
        '만들어진 토큰을 위 칸에 붙여넣고 연결',
        '두 번째 기기에서는 같은 토큰과 함께, 위에 뜬 gist 주소를 넣으세요'
      ].forEach(function (step) { ol.appendChild(el('li', null, step)); });
      how.appendChild(ol);
      panel.appendChild(how);
    };

    onStatus(function (status) {
      var stat = panel.querySelector('.stat');
      if (!stat) return;
      stat.textContent = statusText(status);
      stat.classList.toggle('err', status.state === 'error');
    });

    render();
  };

  /* ---------- 진입점 ---------- */

  window.StarSync = { syncNow: syncNow, mergeStates: mergeStates };

  var boot = function () {
    var panel = document.getElementById('sync-panel');
    if (panel) initPanel(panel);
    syncNow();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
