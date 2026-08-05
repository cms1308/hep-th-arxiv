#!/usr/bin/env python3
"""Add today's brief to the checkout, rebuild index.html, commit, push.

Usage:
  python3 sync_repo.py OWNER/REPO papers.json 2026-06-30 "2026년 6월 30일 (화)"

이 스크립트가 들어 있는 체크아웃에서 바로 작업하고, push 는 이미 설정된 git 자격증명에
맡긴다. 트리가 pull 된 상태라고 가정한다 — 호출 쪽에서 먼저 pull 할 것.

Idempotent: re-running for the same date replaces that day's entry.
Exits 0 with "no changes" if nothing differs.
"""
import json, subprocess, sys, pathlib

repo_slug, papers_path, date, datestr = sys.argv[1:5]
papers_path = str(pathlib.Path(papers_path).resolve())
scripts = pathlib.Path(__file__).resolve().parent
work = scripts.parent

def run(*a, **kw):
    r = subprocess.run(a, cwd=kw.get("cwd", work), capture_output=True, text=True)
    if r.returncode:
        # 실패 원인을 삼키지 않는다. remote URL 에 토큰이 섞일 수 있으므로
        # 서브커맨드 이름과 stderr 만 보여준다.
        raise SystemExit(f"git {a[1]} 실패 (rc={r.returncode}): {r.stderr.strip()[:800]}")
    return r.stdout.strip()

(work / "briefs").mkdir(exist_ok=True)
(work / ".nojekyll").touch()

papers = json.load(open(papers_path))
brief_rel = f"briefs/{date}.html"
subprocess.run([sys.executable, str(scripts / "build_html.py"),
                papers_path, datestr, str(work / brief_rel)], check=True)

mpath = work / "manifest.json"
manifest = json.load(open(mpath)) if mpath.exists() else []
manifest = [m for m in manifest if m["date"] != date]
manifest.append({"date": date, "datestr": datestr, "file": brief_rel,
                 "count": len(papers), "preview": [p["title"] for p in papers[:3]]})
manifest.sort(key=lambda m: m["date"], reverse=True)
json.dump(manifest, open(mpath, "w"), ensure_ascii=False, indent=1)

subprocess.run([sys.executable, str(scripts / "build_index.py"),
                str(mpath), str(work / "index.html")], check=True)

readme = work / "README.md"
if not readme.exists():
    owner, name = repo_slug.split("/")
    readme.write_text(
        f"# arXiv hep-th 데일리 브리핑\n\n"
        f"매 평일 arXiv `hep-th` 신규 제출 논문(cross-list 제외)의 제목·저자·카테고리·abstract와\n"
        f"한국어 abstract를 정리해 자동으로 커밋합니다.\n\n"
        f"**아카이브:** https://{owner}.github.io/{name}/\n\n"
        f"- `index.html` — 발행 목록 (manifest.json에서 자동 생성)\n"
        f"- `briefs/YYYY-MM-DD.html` — 각 날짜 브리핑\n"
        f"- `manifest.json` — 발행 메타데이터\n\n"
        f"출처: https://arxiv.org/list/hep-th/new · 한국어 abstract는 기계 번역입니다.\n",
        encoding="utf-8")

run("git", "add", "-A")
if not subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=work).returncode:
    print("no changes")
    sys.exit(0)
run("git", "commit", "-m", f"{date}: hep-th 신규 {len(papers)}편")
run("git", "push", "-u", "origin", "main")
owner, name = repo_slug.split("/")
print(f"pushed https://{owner}.github.io/{name}/{brief_rel}")
