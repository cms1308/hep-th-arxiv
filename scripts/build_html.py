#!/usr/bin/env python3
"""Build a self-contained daily brief page from papers.json.

Usage: python3 build_html.py papers.json "2026년 6월 30일 (화)" out.html [--standalone]
  --standalone : omit the "← 전체 목록" back-link (for chat delivery, not the repo)
"""
import json, sys, html, re

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

back = "" if standalone else '<a class="back" href="../index.html">← 전체 목록</a>'

doc = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>arXiv hep-th 데일리 · {html.escape(datestr)}</title>
<style>
:root{{
  --bg:#f7f7f5; --card:#fff; --ink:#1c1b19; --muted:#6b6a66; --line:#e5e3dd;
  --accent:#6d5ce0; --shadow:0 1px 2px rgba(0,0,0,.04),0 4px 16px rgba(0,0,0,.04);
}}
@media (prefers-color-scheme:dark){{
  :root{{--bg:#141413;--card:#1d1d1b;--ink:#eceae4;--muted:#9b998f;--line:#2f2f2c;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 16px rgba(0,0,0,.25);}}
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.65 -apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo","Noto Sans KR",Segoe UI,sans-serif;
 -webkit-font-smoothing:antialiased}}
header{{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);
 backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:16px 24px 13px}}
.wrap{{max-width:940px;margin:0 auto}}
.back{{display:inline-block;color:var(--muted);text-decoration:none;font-size:12.5px;margin-bottom:6px}}
.back:hover{{color:var(--accent)}}
h1{{margin:0;font-size:20px;letter-spacing:-.02em;font-weight:650}}
h1 .dot{{color:var(--accent)}}
.sub{{color:var(--muted);font-size:13.5px;margin-top:3px}}
.controls{{display:flex;gap:8px;align-items:center;margin-top:11px}}
.tbtn{{padding:5px 11px;border:1px solid var(--line);background:var(--card);color:var(--muted);
 border-radius:999px;font-size:12.5px;cursor:pointer;font-family:inherit;transition:.13s}}
.tbtn:hover{{border-color:var(--accent);color:var(--ink)}}
.tbtn.on{{background:var(--ink);border-color:var(--ink);color:var(--bg)}}
main{{max-width:940px;margin:0 auto;padding:22px 24px 80px}}
.card{{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:20px 22px 18px;margin-bottom:14px;box-shadow:var(--shadow)}}
.num{{position:absolute;top:20px;left:-38px;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums;opacity:.7}}
@media(max-width:1040px){{.num{{position:static;margin-bottom:4px}}}}
.card h2{{margin:0 0 8px;font-size:17.5px;line-height:1.4;letter-spacing:-.01em;font-weight:640}}
.card h2 a{{color:inherit;text-decoration:none}}
.card h2 a:hover{{color:var(--accent)}}
.meta{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;font-size:12px;margin-bottom:7px}}
.meta>a{{color:var(--accent);text-decoration:none;font-variant-numeric:tabular-nums}}
.meta>a:hover{{text-decoration:underline}}
.meta a.pdf{{color:var(--muted)}}
.cat{{color:var(--c);border:1px solid color-mix(in srgb,var(--c) 35%,transparent);
 background:color-mix(in srgb,var(--c) 9%,transparent);padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:500}}
.authors{{color:var(--muted);font-size:13.5px;margin-bottom:12px}}
.abs{{margin-top:10px;padding-left:13px;border-left:2px solid var(--line)}}
.abs.ko{{border-left-color:color-mix(in srgb,var(--accent) 45%,transparent)}}
.abs p{{margin:4px 0 0;font-size:14.6px;line-height:1.72;word-break:keep-all;overflow-wrap:anywhere}}
.abs.en p{{font-size:13.8px;line-height:1.62;color:var(--muted);word-break:normal}}
.lbl{{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:600}}
body.hide-en .abs.en{{display:none}}
body.hide-ko .abs.ko{{display:none}}
footer{{max-width:940px;margin:0 auto;padding:0 24px 40px;color:var(--muted);font-size:12.5px}}
</style></head><body>
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
<script>
window.MathJax={{tex:{{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$']],
 processEscapes:true,tags:'none'}},options:{{skipHtmlTags:['script','noscript','style','textarea','pre','code'],
 ignoreHtmlClass:'meta|authors'}},chtml:{{scale:0.95}},startup:{{typeset:true}}}};
</script>
<script async src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.min.js"></script>
</body></html>"""

open(outpath, "w").write(doc)
print("wrote", outpath, len(doc), "bytes")
