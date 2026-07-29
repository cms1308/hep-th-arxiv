#!/usr/bin/env python3
"""arXiv hep-th 신규 논문 수집기 — GitHub Actions 러너에서 실행.

이 스크립트가 arXiv를 직접 호출하는 유일한 지점입니다.
결과는 data/<공지날짜>.json 으로 커밋되고, 브리핑 세션은 그 파일만 읽습니다.

모드:
  --rss                  당일 공지분을 RSS에서 수집 (매일 자동 실행)
  --api --date D         과거 날짜 D의 공지분을 arXiv API로 백필 (수동 실행)
  --api --from T1 --to T2 --date D
                         제출시각 창을 직접 지정해 백필 (T = YYYYMMDDHHMM, UTC)

출력 스키마: [{id, title, authors, categories, abstract}, ...]
abstract_ko 는 이후 번역 단계에서 채워집니다.
"""
import argparse, json, os, pathlib, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "hep-th-daily-brief/1.0 (https://github.com/cms1308/hep-th-arxiv; mailto:cccms13081@gmail.com)"
RSS_URL = "https://rss.arxiv.org/rss/hep-th"
API_URL = "http://export.arxiv.org/api/query"
DC = "{http://purl.org/dc/elements/1.1/}"
ATOM = "{http://www.w3.org/2005/Atom}"
ARX = "{http://arxiv.org/schemas/atom}"


def get(url, tries=4):
    """arXiv 권장 정책에 맞춰 여유 있게 재시도한다."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # 429/5xx/타임아웃 모두 동일 처리
            last = e
            wait = 15 * (i + 1)
            print(f"  재시도 {i+1}/{tries} ({e}) — {wait}s 대기", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"arXiv 요청 실패: {url}\n{last}")


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


# ---------------------------------------------------------------- RSS 모드
def strip_prefix(desc):
    """'arXiv:2607.xxxxx Announce Type: new Abstract: ...' 접두부를 떼어낸다."""
    d = clean(desc)
    d = re.sub(r"^arXiv:\s*\S+\s*", "", d)
    d = re.sub(r"^Announce Type:\s*\S+\s*", "", d, flags=re.I)
    d = re.sub(r"^Abstract:\s*", "", d, flags=re.I)
    return d.strip()


def fetch_rss():
    raw = get(RSS_URL)
    ch = ET.fromstring(raw).find("channel")

    pub = ch.findtext("pubDate") or ch.findtext("lastBuildDate")
    announce = parsedate_to_datetime(pub).date().isoformat()
    built = clean(ch.findtext("lastBuildDate"))

    papers = []
    for it in ch.findall("item"):
        desc = it.findtext("description") or ""
        atype = ""
        m = re.search(r"Announce Type:\s*(\S+)", desc, flags=re.I)
        if m:
            atype = m.group(1).lower()
        if atype != "new":
            continue

        aid = ""
        m = re.search(r"arXiv:(\S+)", desc)
        if m:
            aid = m.group(1)
        else:  # link fallback
            m = re.search(r"/abs/(\S+)", it.findtext("link") or "")
            aid = m.group(1) if m else ""
        aid = re.sub(r"v\d+$", "", aid.rstrip(":"))   # 2607.24632v1 -> 2607.24632

        papers.append({
            "id": aid,
            "title": clean(it.findtext("title")),
            "authors": clean(it.findtext(DC + "creator")),
            "categories": ", ".join(
                clean(c.text) for c in it.findall("category") if clean(c.text)),
            "abstract": strip_prefix(desc),
        })
    return announce, built, papers


# ------------------------------------------------- /list/new 모드 (권장·조기)
NEW_URL = "https://arxiv.org/list/hep-th/new"
DUMP = None   # --dump-html 로 설정되면 원본 HTML을 저장한다


def fetch_new_listing():
    """arxiv.org/list/hep-th/new 의 'New submissions' 절만 파싱한다.

    이 페이지는 공지 시각(20:00 ET = 09:00 KST)에 갱신되는 확정 목록이라
    RSS(13:00 KST 빌드)보다 4시간 빠르고, API처럼 제출시각 창을 추정할 필요가 없다.
    """
    html_text = get(NEW_URL).decode("utf-8", "replace")
    if DUMP:
        pathlib.Path(DUMP).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(DUMP).write_text(html_text[:400000], encoding="utf-8")
        print(f"  [dump] {DUMP} ({len(html_text)} bytes 원본)")

    # 절 경계는 <h3> 로 잡는다. 페이지 상단 목차에도 'Cross-lists' 문구가 있어
    # 단순 문자열 검색으로는 본문이 통째로 잘린다.
    ms = re.search(r'<h3[^>]*>\s*New submissions', html_text, re.I)
    if not ms:
        print("::warning::'New submissions' 절을 찾지 못했습니다 (페이지 구조 변경?)")
        return []
    start = ms.end()
    nxt = re.search(r'<h3[^>]*>', html_text[start:], re.I)
    cut = start + nxt.start() if nxt else len(html_text)
    body = html_text[start:cut]

    declared = None
    md = re.search(r'showing\s+(\d+)\s+of\s+(\d+)\s+entries', ms.group(0) + html_text[ms.end():ms.end() + 120])
    if md:
        declared = int(md.group(2))
    print(f"  [parse] 본문 {cut-start} bytes, 페이지 표기 {declared}편")

    # 항목 경계: <dt> ... </dd>
    chunks = re.split(r'<dt[^>]*>', body)[1:]
    papers = []
    for ch in chunks:
        m = re.search(r'arXiv:(\d{4}\.\d{4,5})', ch)
        if not m:
            continue
        aid = m.group(1)

        def grab(cls, tag="div"):
            # arXiv는 class='...' (작은따옴표) 를 쓴다. 두 방식 모두 받는다.
            mm = re.search(rf'''<{tag}[^>]*class=["'][^"']*{cls}[^"']*["'][^>]*>(.*?)</{tag}>''',
                           ch, re.S)
            return mm.group(1) if mm else ""

        def detag(s):
            s = re.sub(r'''<span[^>]*class=["']descriptor["'][^>]*>.*?</span>''',
                       ' ', s, flags=re.S)
            s = re.sub(r'<[^>]+>', ' ', s)
            s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                  .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
            return clean(s)

        title = detag(grab("list-title"))
        authors = detag(grab("list-authors"))
        subjects = detag(grab("list-subjects"))
        abstract = detag(grab("mathjax", tag="p"))

        # "Subjects: High Energy Physics - Theory (hep-th); General Relativity (gr-qc)"
        cats = re.findall(r'\(([a-zA-Z\-]+(?:\.[A-Za-z\-]+)?)\)', subjects)
        papers.append({
            "id": aid, "title": title, "authors": authors,
            "categories": ", ".join(dict.fromkeys(cats)),
            "abstract": abstract,
        })

    seen, uniq = set(), []
    for p in papers:
        if p["id"] not in seen:
            seen.add(p["id"]); uniq.append(p)
    return uniq


def stale_against(papers, outdir, date):
    """이미 저장된 다른 날짜와 ID 집합이 동일하면 그 날짜를 돌려준다."""
    ids = {p["id"] for p in papers}
    if not ids:
        return None
    for f in sorted(pathlib.Path(outdir).glob("*.json")):
        if f.stem == date:
            continue
        try:
            prev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        pl = prev["papers"] if isinstance(prev, dict) else prev
        if {p["id"] for p in pl} == ids:
            return f.stem
    return None


# ---------------------------------------------------------------- API 모드
def announce_window(date_str):
    """공지일 D의 신규분에 해당하는 제출 시각 창(UTC)을 추정한다.

    arXiv는 14:00 ET 마감이며 주말에는 공지하지 않는다.
    D의 목록 = (D-1 직전 영업일 14:00 ET) ~ (D-1 14:00 ET).
    한국시간 기준 공지일을 그대로 넣으면 된다. 휴일은 반영하지 못하므로
    백필 결과 편수는 반드시 눈으로 확인할 것.
    """
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    end_day = d - timedelta(days=1)
    while end_day.weekday() >= 5:                 # 토·일이면 직전 금요일로
        end_day -= timedelta(days=1)
    start_day = end_day - timedelta(days=1)
    while start_day.weekday() >= 5:
        start_day -= timedelta(days=1)
    # 14:00 ET = 18:00 UTC (EDT 기준). 겨울철은 19:00 UTC라 1시간 여유를 둔다.
    fmt = lambda day, h: f"{day.strftime('%Y%m%d')}{h:02d}00"
    return fmt(start_day, 18), fmt(end_day, 18)


def fetch_api(lo, hi):
    """cat:hep-th 중 제출시각이 [lo,hi]인 항목을 모두 받아온다 (100건씩 페이징)."""
    out, start, page = [], 0, 100
    while True:
        q = (f"cat:hep-th AND submittedDate:[{lo} TO {hi}]")
        url = (f"{API_URL}?" + urllib.parse.urlencode({
            "search_query": q, "start": start, "max_results": page,
            "sortBy": "submittedDate", "sortOrder": "ascending"}))
        feed = ET.fromstring(get(url))
        entries = feed.findall(ATOM + "entry")
        if not entries:
            break
        for e in entries:
            prim = e.find(ARX + "primary_category")
            prim = prim.get("term") if prim is not None else ""
            if prim != "hep-th":          # cross-list 제외 — RSS의 announce_type=new 와 동일 기준
                continue
            aid = (e.findtext(ATOM + "id") or "").rsplit("/abs/", 1)[-1]
            out.append({
                "id": re.sub(r"v\d+$", "", aid),
                "title": clean(e.findtext(ATOM + "title")),
                "authors": ", ".join(
                    clean(a.findtext(ATOM + "name")) for a in e.findall(ATOM + "author")),
                "categories": ", ".join(
                    c.get("term") for c in e.findall(ATOM + "category") if c.get("term")),
                "abstract": clean(e.findtext(ATOM + "summary")),
            })
        start += page
        if len(entries) < page:
            break
        time.sleep(3)                      # arXiv 권장 호출 간격
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rss", action="store_true")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--new", action="store_true",
                    help="arxiv.org/list/hep-th/new 에서 확정 목록을 조기 수집")
    ap.add_argument("--date")
    ap.add_argument("--from", dest="lo")
    ap.add_argument("--to", dest="hi")
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--expect", help="기대 공지일 YYYY-MM-DD. 다르면 재시도한다.")
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--retry-wait", dest="retry_wait", type=int, default=300)
    ap.add_argument("--dump-html", dest="dump_html", help="원본 HTML을 이 경로에 저장(디버그)")
    a = ap.parse_args()

    global DUMP
    DUMP = a.dump_html

    if a.new:
        date = a.expect or a.date or datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        built = "list/new"
        # 공지 전에 돌면 전날 목록이 그대로 온다. 기존 날짜 파일과 ID 집합이
        # 똑같으면 아직 갱신 전으로 보고 재시도한다.
        for attempt in range(1, a.retries + 2):
            papers = fetch_new_listing()
            stale = stale_against(papers, a.outdir, date)
            print(f"/list/new 수집 {attempt}회차: {len(papers)}편 (공지일 {date} 로 기록)")
            if not stale:
                break
            if attempt > a.retries:
                print(f"::warning::{stale} 와 동일한 목록입니다. 갱신 전일 수 있습니다.")
                papers = []
                break
            print(f"  {stale} 와 동일 — 아직 갱신 전. {a.retry_wait}s 후 재시도")
            time.sleep(a.retry_wait)
    elif a.api:
        if not a.date:
            raise SystemExit("--api 에는 --date YYYY-MM-DD 가 필요합니다")
        lo, hi = (a.lo, a.hi) if a.lo and a.hi else announce_window(a.date)
        print(f"API 백필: {a.date}  제출창 {lo} ~ {hi} (UTC)")
        date, built, papers = a.date, f"api:{lo}-{hi}", fetch_api(lo, hi)
    else:
        # arXiv는 04:00~04:40 UTC 사이 어딘가에서 당일 공지를 올린다(실측: 04:00 미반영, 04:38 반영).
        # --expect 를 주면 그 날짜가 나올 때까지 재시도해, cron 시각을 정확히 맞추지 않아도 되게 한다.
        for attempt in range(1, a.retries + 2):
            date, built, papers = fetch_rss()
            print(f"RSS 수집 {attempt}회차: 공지일 {date}  lastBuildDate={built}  신규 {len(papers)}편")
            if not a.expect or date == a.expect:
                break
            if attempt > a.retries:
                print(f"::warning::기대 날짜 {a.expect} 를 못 받고 {date} 로 종료합니다")
                break
            print(f"  기대={a.expect} 불일치 — {a.retry_wait}s 후 재시도")
            time.sleep(a.retry_wait)
        if a.expect and date != a.expect:
            print(f"::warning::피드 공지일({date})이 기대 날짜({a.expect})와 다릅니다")

    papers.sort(key=lambda p: p["id"])
    print(f"신규 {len(papers)}편")
    if not papers:
        print("항목 0편 — 주말이거나 공지 전입니다. 커밋하지 않습니다.")
        return

    thin = [p["id"] for p in papers if len(p["abstract"]) < 200]
    if thin:
        print(f"::warning::abstract 가 짧은 항목: {thin}")

    outdir = pathlib.Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{date}.json"
    path.write_text(json.dumps(
        {"date": date, "source": "new" if a.new else ("api" if a.api else "rss"),
         "built": built, "count": len(papers), "papers": papers},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path}")

    # 워크플로 후속 스텝에서 쓰도록 출력값을 넘긴다
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"date={date}\ncount={len(papers)}\npath={path}\n")


if __name__ == "__main__":
    main()
