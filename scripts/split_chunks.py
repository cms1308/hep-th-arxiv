#!/usr/bin/env python3
"""data/<date>.json 을 번역 서브에이전트용 입력 청크로 쪼갠다.

Usage: python3 split_chunks.py /home/claude/repo/data/2026-07-28.json [size]
출력: $BRIEF_WORK/in/chunk1.json ... (각각 papers 배열)
BRIEF_WORK 기본값은 /home/claude/work (브리핑 컨테이너).
"""
import json, os, pathlib, sys

src = pathlib.Path(sys.argv[1])
size = int(sys.argv[2]) if len(sys.argv) > 2 else 6

d = json.loads(src.read_text(encoding="utf-8"))
papers = d["papers"] if isinstance(d, dict) else d
papers.sort(key=lambda p: p["id"])

indir = pathlib.Path(os.environ.get("BRIEF_WORK", "/home/claude/work")) / "in"
indir.mkdir(parents=True, exist_ok=True)
for f in indir.glob("chunk*.json"):
    f.unlink()

n = 0
for i in range(0, len(papers), size):
    n += 1
    (indir / f"chunk{n}.json").write_text(
        json.dumps(papers[i:i + size], ensure_ascii=False, indent=1), encoding="utf-8")

print(f"date={d.get('date') if isinstance(d, dict) else '?'}")
print(f"papers={len(papers)} chunks={n}")
for i in range(1, n + 1):
    c = json.loads((indir / f"chunk{i}.json").read_text(encoding="utf-8"))
    print(f"  chunk{i}: {len(c)}편  {', '.join(p['id'] for p in c)}")
