/* 별표(즐겨찾기) — 브리핑 페이지와 모아보기 페이지가 함께 쓰는 클라이언트 전용 스크립트.
 *
 * 저장소는 브라우저 localStorage 입니다. 기기 간 동기화는 star-sync.js 가 선택적으로
 * 얹어 주며, 그게 없어도 이 파일만으로 별표는 그 브라우저 안에서 온전히 동작합니다.
 *
 * 저장 모양 (hepth:starred):
 *   { version: 1,
 *     papers:  { "<arXiv id>": { id, title, ..., ts } },   ts = 별표한 시각(ms)
 *     removed: { "<arXiv id>": ts } }                      해제한 시각 = 삭제 표시
 *
 * 삭제 표시를 남기는 이유: 동기화할 때 "여기 없음" 과 "여기서 뗐음" 을 구별해야
 * 한쪽에서 뗀 별표가 다른 기기의 목록에서 되살아나지 않습니다.
 *
 * 이미 발행된 브리핑에도 <script> 한 줄만 넣으면 되도록 CSS 주입과 버튼 생성까지
 * 이 파일 안에서 합니다. 브리핑 HTML 의 본문 구조는 건드리지 않습니다.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'hepth:starred';
  var STAR_ON = '★';
  var STAR_OFF = '☆';

  /* ---------- 저장소 (읽은 값은 외부 데이터로 취급해 검증한다) ---------- */

  var isValidEntry = function (e) {
    return !!e && typeof e === 'object' && typeof e.id === 'string' && e.id !== '';
  };

  var emptyState = function () {
    return { version: 1, papers: {}, removed: {} };
  };

  /* 키는 항상 항목의 arXiv id 로 정규화한다 — 그래야 어떤 화면에서든 id 하나로 지운다. */
  var cleanPapers = function (raw) {
    var papers = {};
    if (!raw || typeof raw !== 'object') return papers;
    Object.keys(raw).forEach(function (key) {
      var entry = raw[key];
      if (isValidEntry(entry)) papers[entry.id] = entry;
    });
    return papers;
  };

  var cleanRemoved = function (raw) {
    var removed = {};
    if (!raw || typeof raw !== 'object') return removed;
    Object.keys(raw).forEach(function (id) {
      var ts = raw[id];
      if (typeof ts === 'number' && isFinite(ts)) removed[id] = ts;
    });
    return removed;
  };

  var normalize = function (parsed) {
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return emptyState();
    /* 삭제 표시가 없던 옛 저장본은 통째로 papers 였다. */
    var isLegacy = !parsed.papers && !parsed.removed;
    return {
      version: 1,
      papers: cleanPapers(isLegacy ? parsed : parsed.papers),
      removed: cleanRemoved(isLegacy ? null : parsed.removed)
    };
  };

  var readState = function () {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      return normalize(raw ? JSON.parse(raw) : null);
    } catch (err) {
      console.warn('[stars] 저장된 별표를 읽지 못했습니다:', err);
      return emptyState();
    }
  };

  var writeState = function (next) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return true;
    } catch (err) {
      console.warn('[stars] 별표를 저장하지 못했습니다:', err);
      window.alert('별표를 저장하지 못했습니다. 브라우저 저장 공간이 가득 찼거나 ' +
                   '비공개 모드일 수 있습니다.');
      return false;
    }
  };

  var listeners = [];
  var notify = function (origin) {
    listeners.forEach(function (fn) {
      try { fn(origin); } catch (err) { console.warn('[stars] 갱신 처리 실패:', err); }
    });
  };

  var without = function (obj, id) {
    var next = {};
    Object.keys(obj).forEach(function (key) { if (key !== id) next[key] = obj[key]; });
    return next;
  };

  var StarStore = {
    state: readState,

    papers: function () { return readState().papers; },

    has: function (id) {
      return Object.prototype.hasOwnProperty.call(readState().papers, id);
    },

    add: function (paper, now) {
      var current = readState();
      var entry = Object.assign({}, paper, { ts: now || Date.now() });
      var next = {
        version: 1,
        papers: Object.assign({}, current.papers, (function () {
          var one = {}; one[entry.id] = entry; return one;
        })()),
        removed: without(current.removed, entry.id)
      };
      if (!writeState(next)) return false;
      notify('local');
      return true;
    },

    remove: function (id, now) {
      var current = readState();
      var removed = Object.assign({}, current.removed);
      removed[id] = now || Date.now();
      var next = { version: 1, papers: without(current.papers, id), removed: removed };
      if (!writeState(next)) return false;
      notify('local');
      return true;
    },

    /* 동기화가 합쳐 온 결과를 통째로 갈아끼운다. origin='remote' 라 다시 밀어올리지 않는다. */
    replaceState: function (state, origin) {
      var next = normalize(state);
      if (!writeState(next)) return false;
      notify(origin || 'remote');
      return true;
    },

    onChange: function (fn) { listeners.push(fn); },

    /* 최신 공지일 먼저, 같은 날 안에서는 브리핑에 실린 순서대로. */
    list: function () {
      var papers = readState().papers;
      return Object.keys(papers).map(function (id) { return papers[id]; }).sort(function (a, b) {
        var da = a.date || '', db = b.date || '';
        if (da !== db) return da < db ? 1 : -1;
        return (a.n || 0) - (b.n || 0);
      });
    }
  };

  /* ---------- 스타일 (기존 페이지도 이 주입만으로 동작하도록) ---------- */

  var CSS = [
    ':root{--star:#d99e0b}',
    '@media (prefers-color-scheme:dark){:root{--star:#f0c14b}}',
    '.card h2{padding-right:36px}',
    '.starbtn{position:absolute;top:14px;right:14px;width:30px;height:30px;padding:0;',
    ' display:flex;align-items:center;justify-content:center;line-height:1;',
    ' border:1px solid transparent;border-radius:8px;background:transparent;',
    ' color:var(--muted);font-size:18px;font-family:inherit;cursor:pointer;transition:.13s}',
    '.starbtn:hover{border-color:var(--line);color:var(--star)}',
    '.card.starred .starbtn{color:var(--star)}',
    '.card.starred{border-color:color-mix(in srgb,var(--star) 45%,var(--line))}',
    '.tbtn.tlink{text-decoration:none;display:inline-flex;align-items:center}',
    'body.only-starred .card:not(.starred){display:none}',
    '.star-empty{display:none;color:var(--muted);font-size:14px;padding:26px 2px}',
    'body.only-starred .star-empty.show{display:block}'
  ].join('\n');

  var injectCss = function () {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);
  };

  /* ---------- 카드 읽기 ---------- */

  var text = function (el) { return el ? el.textContent.trim() : ''; };

  var pageDate = function () {
    var m = window.location.pathname.match(/(\d{4}-\d{2}-\d{2})\.html$/);
    return m ? m[1] : '';
  };

  var pageDatestr = function () {
    var title = document.title || '';
    var i = title.indexOf('·');
    return i >= 0 ? title.slice(i + 1).trim() : title.trim();
  };

  /* MathJax 가 제목의 $...$ 를 조판하기 전에 원문을 읽어 두어야 한다.
     그래서 이 스크립트는 MathJax 태그보다 앞에, defer 없이 놓는다. */
  var readCard = function (card, index, date, datestr) {
    var link = card.querySelector('.meta a[href*="/abs/"]');
    if (!link) return null;
    var id = (link.getAttribute('href') || '').split('/abs/')[1];
    if (!id) return null;
    var cats = Array.prototype.map.call(card.querySelectorAll('.cat'), text);
    return {
      id: id,
      n: index + 1,
      title: text(card.querySelector('h2 a') || card.querySelector('h2')),
      authors: text(card.querySelector('.authors')),
      categories: cats.join(', '),
      abstract_ko: text(card.querySelector('.abs.ko p')),
      abstract: text(card.querySelector('.abs.en p')),
      date: date,
      datestr: datestr,
      file: date ? 'briefs/' + date + '.html' : ''
    };
  };

  /* ---------- 브리핑 페이지 ---------- */

  var paintButton = function (btn, starred) {
    btn.textContent = starred ? STAR_ON : STAR_OFF;
    btn.setAttribute('aria-pressed', starred ? 'true' : 'false');
    btn.title = starred ? '별표 해제' : '별표';
  };

  var makeStarButton = function (starred) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'starbtn';
    btn.setAttribute('aria-label', '별표');
    paintButton(btn, starred);
    return btn;
  };

  var initBriefPage = function (cards) {
    var date = pageDate();
    var datestr = pageDatestr();
    var papers = Array.prototype.map.call(cards, function (card, i) {
      return readCard(card, i, date, datestr);
    });

    var controls = document.querySelector('.controls');
    var filterBtn = null;
    var emptyMsg = null;
    var buttons = [];

    var repaint = function () {
      var saved = StarStore.papers();
      var count = 0;
      buttons.forEach(function (item) {
        var starred = Object.prototype.hasOwnProperty.call(saved, item.paper.id);
        if (starred) count++;
        item.card.classList.toggle('starred', starred);
        paintButton(item.btn, starred);
      });
      if (filterBtn) filterBtn.textContent = '★만 보기 (' + count + ')';
      if (emptyMsg) emptyMsg.classList.toggle('show', count === 0);
    };

    Array.prototype.forEach.call(cards, function (card, i) {
      var paper = papers[i];
      if (!paper) return;
      var btn = makeStarButton(false);
      btn.addEventListener('click', function () {
        var on = !card.classList.contains('starred');
        if (on ? StarStore.add(paper) : StarStore.remove(paper.id)) repaint();
      });
      card.appendChild(btn);
      buttons.push({ card: card, btn: btn, paper: paper });
    });

    var main = document.querySelector('main');
    if (main) {
      emptyMsg = document.createElement('p');
      emptyMsg.className = 'star-empty';
      emptyMsg.textContent = '이 날짜에는 별표한 논문이 없습니다.';
      main.appendChild(emptyMsg);
    }

    if (controls) {
      filterBtn = document.createElement('button');
      filterBtn.type = 'button';
      filterBtn.className = 'tbtn';
      filterBtn.addEventListener('click', function () {
        filterBtn.classList.toggle('on', document.body.classList.toggle('only-starred'));
      });
      controls.appendChild(filterBtn);

      var link = document.createElement('a');
      link.className = 'tbtn tlink';
      link.href = '../starred.html';
      link.textContent = '★ 모아보기';
      controls.appendChild(link);
    }

    repaint();
    StarStore.onChange(function (origin) { if (origin !== 'local') repaint(); });
  };

  /* ---------- 모아보기 페이지 ---------- */

  var el = function (tag, cls, txt) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (txt !== undefined) node.textContent = txt;
    return node;
  };

  var absBlock = function (kind, label, body) {
    var wrap = el('div', 'abs ' + kind);
    wrap.appendChild(el('span', 'lbl', label));
    wrap.appendChild(el('p', null, body));
    return wrap;
  };

  var starredCard = function (paper, onRemove) {
    var card = el('article', 'card starred');

    var h2 = el('h2');
    var titleLink = el('a', null, paper.title || paper.id);
    titleLink.href = 'https://arxiv.org/abs/' + paper.id;
    titleLink.target = '_blank';
    titleLink.rel = 'noopener';
    h2.appendChild(titleLink);
    card.appendChild(h2);

    var meta = el('div', 'meta');
    var absLink = el('a', null, 'arXiv:' + paper.id);
    absLink.href = 'https://arxiv.org/abs/' + paper.id;
    absLink.target = '_blank';
    absLink.rel = 'noopener';
    meta.appendChild(absLink);
    var pdfLink = el('a', 'pdf', 'PDF');
    pdfLink.href = 'https://arxiv.org/pdf/' + paper.id;
    pdfLink.target = '_blank';
    pdfLink.rel = 'noopener';
    meta.appendChild(pdfLink);
    if (paper.file && paper.datestr) {
      var dayLink = el('a', 'pdf', paper.datestr);
      dayLink.href = paper.file;
      meta.appendChild(dayLink);
    }
    card.appendChild(meta);

    if (paper.authors) card.appendChild(el('div', 'authors', paper.authors));
    if (paper.abstract_ko) card.appendChild(absBlock('ko', '한국어', paper.abstract_ko));
    if (paper.abstract) card.appendChild(absBlock('en', 'Abstract', paper.abstract));

    var btn = makeStarButton(true);
    btn.addEventListener('click', function () {
      if (!StarStore.remove(paper.id)) return;
      card.remove();
      onRemove();
    });
    card.appendChild(btn);

    return card;
  };

  var typeset = function (root) {
    /* 보통은 이 스크립트가 MathJax 라이브러리보다 먼저 실행되므로 MathJax 의 startup
       조판이 방금 만든 카드까지 함께 처리한다. 이미 로드가 끝난 뒤라면 새 카드만 조판한다. */
    var mj = window.MathJax;
    if (!mj || !mj.startup || !mj.startup.promise) return;
    mj.startup.promise
      .then(function () { return mj.typesetPromise([root]); })
      .catch(function (err) { console.warn('[stars] 수식 조판 실패:', err); });
  };

  var initStarredPage = function (root) {
    var countEl = document.getElementById('starred-count');
    var emptyEl = document.getElementById('starred-empty');

    var refresh = function () {
      var left = root.querySelectorAll('.card').length;
      if (countEl) countEl.textContent = String(left);
      if (emptyEl) emptyEl.hidden = left > 0;
    };

    var render = function () {
      root.textContent = '';
      StarStore.list().forEach(function (paper) {
        root.appendChild(starredCard(paper, refresh));
      });
      refresh();
      typeset(root);
    };

    render();
    StarStore.onChange(function (origin) { if (origin !== 'local') render(); });
  };

  /* ---------- 진입점 ---------- */

  var boot = function () {
    injectCss();
    var root = document.getElementById('starred-list');
    if (root) { initStarredPage(root); return; }
    var cards = document.querySelectorAll('article.card');
    if (cards.length) initBriefPage(cards);
  };

  window.StarStore = StarStore;

  if (document.querySelector('article.card') || document.getElementById('starred-list')) {
    boot();
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
