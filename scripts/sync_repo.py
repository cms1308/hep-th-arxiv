#!/usr/bin/env python3
"""Clone the archive repo, add today's brief, rebuild index.html, commit, push.

Usage:
  GH_TOKEN=... python3 sync_repo.py OWNER/REPO papers.json 2026-06-30 "2026년 6월 30일 (화)"

Idempotent: re-running for the same date replaces that day's entry.
Exits 0 with "no changes" if nothing differs.
"""
import json, os, subprocess, sys, pathlib, shutil

repo_slug, papers_path, date, datestr = sys.argv[1:5]
token = os.environ["GH_TOKEN"]
work = pathlib.Path("/home/claude/work/_repo")

def run(*a, **kw):
    return subprocess.run(a, cwd=kw.get("cwd", work), check=True,
                          capture_output=True, text=True).stdout.strip()

if work.exists():
    shutil.rmtree(work)
url = f"https://x-access-token:{token}@github.com/{repo_slug}.git"
subprocess.run(["git", "clone", "--depth", "1", url, str(work)],
               check=True, capture_output=True, text=True)
run("git", "config", "user.email", "noreply@anthropic.com")
run("git", "config", "user.name", "arxiv-hep-th-bot")
run("git", "checkout", "-B", "main")

(work / "briefs").mkdir(exist_ok=True)
(work / ".nojekyll").touch()

papers = json.load(open(papers_path))
brief_rel = f"briefs/{date}.html"
subprocess.run([sys.executable, "/home/claude/repo/scripts/build_html.py",
                papers_path, datestr, str(work / brief_rel)], check=True)

mpath = work / "manifest.json"
manifest = json.load(open(mpath)) if mpath.exists() else []
manifest = [m for m in manifest if m["date"] != date]
manifest.append({"date": date, "datestr": datestr, "file": brief_rel,
                 "count": len(papers), "preview": [p["title"] for p in papers[:3]]})
manifest.sort(key=lambda m: m["date"], reverse=True)
json.dump(manifest, open(mpath, "w"), ensure_ascii=False, indent=1)

subprocess.run([sys.executable, "/home/claude/repo/scripts/build_index.py",
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
        f"출처: https://rss.arxiv.org/rss/hep-th · 한국어 abstract는 기계 번역입니다.\n",
        encoding="utf-8")

run("git", "add", "-A")
if not subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=work).returncode:
    print("no changes")
    sys.exit(0)
run("git", "commit", "-m", f"{date}: hep-th 신규 {len(papers)}편")
run("git", "push", "-u", "origin", "main")
owner, name = repo_slug.split("/")
print(f"pushed https://{owner}.github.io/{name}/{brief_rel}")
