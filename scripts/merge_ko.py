#!/usr/bin/env python3
"""번역문(<arXiv id>.txt)을 원본 data/<날짜>.json 과 합쳐 papers.json 을 만든다.

모델에게 JSON 을 직접 쓰게 하면 abstract 의 LaTeX 백슬래시·따옴표 이스케이프가 깨진다
(실측 2026-08-05: 4청크 중 3청크가 BAD_JSON). 그래서 모델은 번역문만 순수 텍스트로 쓰고,
원문 필드와 합치는 일은 여기서 한다 — 이스케이프도 verbatim 복사도 필요 없다.

Usage: python3 merge_ko.py data/2026-08-05.json <번역문 디렉터리> papers.json

결측/부실 항목을 리포트하고, 하나라도 있으면 exit 1.
"""
import json, pathlib, sys

src, kodir, out = (pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]),
                   pathlib.Path(sys.argv[3]))

d = json.loads(src.read_text(encoding="utf-8"))
papers = d["papers"] if isinstance(d, dict) else d

problems, merged = 0, []
for p in papers:
    f = kodir / f"{p['id']}.txt"
    ko = f.read_text(encoding="utf-8").strip() if f.exists() else ""
    if not ko:
        print(f"MISSING {p['id']}")
        problems += 1
    elif len(ko) < 0.4 * len(p["abstract"]):
        print(f"SHORT_KO {p['id']} {len(p['abstract'])} -> {len(ko)}")
        problems += 1
    merged.append({**p, "abstract_ko": ko})

merged.sort(key=lambda x: x["id"])
out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"merged {len(merged)} papers -> {out} : {problems} problems")
sys.exit(1 if problems else 0)
