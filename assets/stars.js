/* 별표(즐겨찾기) — 브리핑 페이지와 모아보기 페이지가 함께 쓰는 클라이언트 전용 스크립트.
 *
 * 저장소는 브라우저 localStorage 뿐입니다. 서버가 없으므로 별표는 그 브라우저에만
 * 남고, 다른 기기와 동기화되지 않습니다.
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

  var readAll = function () {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : null;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
      /* 키는 항상 항목의 arXiv id 로 정규화한다 — 그래야 어떤 화면에서든
         id 하나로 지울 수 있다. */
      var clean = {};
      Object.keys(parsed).forEach(function (key) {
        var entry = parsed[key];
        if (isValidEntry(entry)) clean[entry.id] = entry;
      });
      return clean;
    } catch (err) {
      console.warn('[stars] 저장된 별표를 읽지 못했습니다:', err);
      return {};
    }
  };

  var writeAll = function (next) {
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

  var StarStore = {
    all: readAll,
    add: function (paper) {
      var current = readAll();
      var next = Object.assign({}, current);
      next[paper.id] = Object.assign({}, paper);
      return writeAll(next);
    },
    remove: function (id) {
      var current = readAll();
      if (!Object.prototype.hasOwnProperty.call(current, id)) return true;
      var next = {};
      Object.keys(current).forEach(function (key) {
        if (key !== id) next[key] = current[key];
      });
      return writeAll(next);
    },
    /* 최신 공지일 먼저, 같은 날 안에서는 브리핑에 실린 순서대로. */
    list: function () {
      var all = readAll();
      return Object.keys(all).map(function (id) { return all[id]; }).sort(function (a, b) {
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

  var makeStarButton = function (starred) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'starbtn';
    btn.textContent = starred ? STAR_ON : STAR_OFF;
    btn.setAttribute('aria-pressed', starred ? 'true' : 'false');
    btn.setAttribute('aria-label', '별표');
    btn.title = starred ? '별표 해제' : '별표';
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

    var countStarred = function () {
      return document.querySelectorAll('.card.starred').length;
    };

    var refresh = function () {
      var n = countStarred();
      if (filterBtn) filterBtn.textContent = '★만 보기 (' + n + ')';
      if (emptyMsg) emptyMsg.classList.toggle('show', n === 0);
    };

    var saved = StarStore.all();
    Array.prototype.forEach.call(cards, function (card, i) {
      var paper = papers[i];
      if (!paper) return;
      var starred = Object.prototype.hasOwnProperty.call(saved, paper.id);
      card.classList.toggle('starred', starred);
      var btn = makeStarButton(starred);
      btn.addEventListener('click', function () {
        var on = !card.classList.contains('starred');
        var ok = on ? StarStore.add(paper) : StarStore.remove(paper.id);
        if (!ok) return;
        card.classList.toggle('starred', on);
        btn.textContent = on ? STAR_ON : STAR_OFF;
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        btn.title = on ? '별표 해제' : '별표';
        refresh();
      });
      card.appendChild(btn);
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
        var on = document.body.classList.toggle('only-starred');
        filterBtn.classList.toggle('on', on);
      });
      controls.appendChild(filterBtn);

      var link = document.createElement('a');
      link.className = 'tbtn tlink';
      link.href = '../starred.html';
      link.textContent = '★ 모아보기';
      controls.appendChild(link);
    }

    refresh();
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

  var initStarredPage = function (root) {
    var countEl = document.getElementById('starred-count');
    var emptyEl = document.getElementById('starred-empty');

    var papers = StarStore.list();

    var refresh = function () {
      var left = root.querySelectorAll('.card').length;
      if (countEl) countEl.textContent = String(left);
      if (emptyEl) emptyEl.hidden = left > 0;
    };

    papers.forEach(function (paper) {
      root.appendChild(starredCard(paper, refresh));
    });
    refresh();

    /* 보통은 이 스크립트가 MathJax 라이브러리보다 먼저 실행되므로 MathJax 의
       startup 조판이 방금 만든 카드까지 함께 처리한다. 이미 로드가 끝난 뒤라면
       (startup.promise 가 있을 때만) 새 카드만 따로 조판한다. */
    var mj = window.MathJax;
    if (mj && mj.startup && mj.startup.promise) {
      mj.startup.promise
        .then(function () { return mj.typesetPromise([root]); })
        .catch(function (err) { console.warn('[stars] 수식 조판 실패:', err); });
    }
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
