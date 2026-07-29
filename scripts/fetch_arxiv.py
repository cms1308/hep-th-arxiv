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
    ap.add_argument("--date")
    ap.add_argument("--from", dest="lo")
    ap.add_argument("--to", dest="hi")
    ap.add_argument("--outdir", default="data")
    a = ap.parse_args()

    if a.api:
        if not a.date:
            raise SystemExit("--api 에는 --date YYYY-MM-DD 가 필요합니다")
        lo, hi = (a.lo, a.hi) if a.lo and a.hi else announce_window(a.date)
        print(f"API 백필: {a.date}  제출창 {lo} ~ {hi} (UTC)")
        date, built, papers = a.date, f"api:{lo}-{hi}", fetch_api(lo, hi)
    else:
        date, built, papers = fetch_rss()
        print(f"RSS 수집: 공지일 {date}  lastBuildDate={built}")
        if a.date and a.date != date:
            print(f"::warning::요청 날짜 {a.date} 와 피드 공지일 {date} 가 다릅니다")

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
        {"date": date, "source": "api" if a.api else "rss",
         "built": built, "count": len(papers), "papers": papers},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path}")

    # 워크플로 후속 스텝에서 쓰도록 출력값을 넘긴다
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"date={date}\ncount={len(papers)}\npath={path}\n")


if __name__ == "__main__":
    main()
