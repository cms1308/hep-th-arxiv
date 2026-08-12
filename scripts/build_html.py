#!/usr/bin/env python3
"""Build a self-contained daily brief page from papers.json.

Usage: python3 build_html.py papers.json "2026년 6월 30일 (화)" out.html [--standalone]
  --standalone : omit the "← 전체 목록" back-link (for chat delivery, not the repo)
"""
import json, sys, html, re, pathlib

papers = json.load(open(sys.argv[1]))
datestr = sys.argv[2]
outpath = sys.argv[3]
standalone = "--standalone" in sys.argv[4:]

CATCOLORS = {
    "hep-th": "#6d5ce0", "hep-ph": "#c2410c", "gr-qc": "#0e7490",
    "math-ph": "#166534", "hep-lat": "#a16207", "cond-mat.str-el": "#9d174d",
    "quant-ph": "#1d4ed8", "astro-ph.CO": "#7c2d12", "math.QA": "#166534",
}

def cat_chip(c):
    col = CATCOLORS.get(c, "#475569")
    return f'<span class="cat" style="--c:{col}">{html.escape(c)}</span>'

cards = []
for i, p in enumerate(papers, 1):
    cats = [c.strip() for c in re.split(r"[,;]", p["categories"]) if c.strip()]
    pid = html.escape(p["id"])
    chips = "".join(cat_chip(c) for c in cats)
    cards.append(f"""
<article class="card">
  <div class="num">{i}</div>
  <h2><a href="https://arxiv.org/abs/{pid}" target="_blank" rel="noopener">{html.escape(p['title'])}</a></h2>
  <div class="meta">
    <a href="https://arxiv.org/abs/{pid}" target="_blank" rel="noopener">arXiv:{pid}</a>
    <a class="pdf" href="https://arxiv.org/pdf/{pid}" target="_blank" rel="noopener">PDF</a>
    {chips}
  </div>
  <div class="authors">{html.escape(p['authors'])}</div>
  <div class="abs ko"><span class="lbl">한국어</span><p>{html.escape(p['abstract_ko'])}</p></div>
  <div class="abs en"><span class="lbl">Abstract</span><p>{html.escape(p['abstract'])}</p></div>
</article>""")

brief_css = (pathlib.Path(__file__).resolve().parent.parent / "assets" / "brief.css").read_text()
# standalone(채팅 전달용)은 자체 완결이어야 하므로 외부 스크립트를 걸지 않는다.
stars = "" if standalone else '<script src="../assets/stars.js"></script>\n'

back = "" if standalone else '<a class="back" href="../index.html">← 전체 목록</a>'

doc = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>arXiv hep-th 데일리 · {html.escape(datestr)}</title>
<style>
{brief_css}</style></head><body>
<header><div class="wrap">
{back}
<h1>arXiv <span class="dot">hep-th</span> 데일리 브리핑</h1>
<div class="sub">{html.escape(datestr)} 공지 · 신규 제출 <b>{len(papers)}</b>편 (cross-list 제외)</div>
<div class="controls">
  <button class="tbtn on" id="tko">한국어</button>
  <button class="tbtn on" id="ten">English</button>
</div>
</div></header>
<main>{''.join(cards)}</main>
<footer>arXiv.org hep-th 신규 제출 목록(cross-list 제외)에서 추출. 한국어 abstract는 기계 번역이며 전문 용어는 원문 유지 — 인용 전 원문 확인 권장.</footer>
<script>
const tko=document.getElementById('tko'),ten=document.getElementById('ten');
tko.onclick=()=>{{document.body.classList.toggle('hide-ko');tko.classList.toggle('on')}};
ten.onclick=()=>{{document.body.classList.toggle('hide-en');ten.classList.toggle('on')}};
</script>
{stars}<script>
window.MathJax={{tex:{{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$']],
 processEscapes:true,tags:'none'}},options:{{skipHtmlTags:['script','noscript','style','textarea','pre','code'],
 ignoreHtmlClass:'meta|authors'}},chtml:{{scale:0.95}},startup:{{typeset:true}}}};
</script>
<script async src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.min.js"></script>
</body></html>"""

open(outpath, "w").write(doc)
print("wrote", outpath, len(doc), "bytes")
