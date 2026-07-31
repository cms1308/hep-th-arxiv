#!/usr/bin/env python3
"""오늘(또는 지정 날짜)의 hep-th 신규 목록을 확보한다 — 브리핑 세션의 1단계.

arXiv를 직접 호출하는 곳은 GitHub Actions 러너 하나뿐이다.
이 스크립트는 그 워크플로를 돌리고 결과 커밋을 기다리는 역할만 한다.
(브리핑 컨테이너의 WebFetch는 arxiv.org 응답을 며칠씩 캐시해 전날 목록을 돌려주므로 쓰지 않는다.)

  1. git pull 로 최신 상태를 받는다.
  2. data/<날짜>.json 이 이미 있으면 그대로 쓴다.
  3. 없으면 .trigger 를 갱신·push 해 워크플로를 띄우고, 결과 커밋이 올 때까지 폴링한다.

Usage:
  python3 scripts/collect.py                      # 오늘(KST) 공지분
  python3 scripts/collect.py --backfill 2026-07-24  # 과거 날짜를 API로 백필
  python3 scripts/collect.py --force              # 파일이 있어도 다시 수집

환경변수 GH_TOKEN 이 필요하다 (push 권한). 값은 절대 출력하지 않는다.
성공하면 마지막 줄에 `OK <data/날짜.json 경로>` 를 찍고 exit 0.
"""
import argparse, os, pathlib, subprocess, sys, time
from datetime import datetime, timedelta, timezone

REPO = pathlib.Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode:
        # 토큰이 섞여 나올 수 있는 건 remote URL 뿐이라 URL은 출력하지 않는다.
        raise SystemExit(f"git {args[0]} 실패 (rc={r.returncode}): {r.stderr.strip()[:400]}")
    return r.stdout.strip()


def last_run():
    p = REPO / "data" / "_last_run.txt"
    return p.read_text(encoding="utf-8") if p.exists() else "(로그 없음)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", metavar="YYYY-MM-DD",
                    help="과거 공지일을 arXiv API로 백필한다")
    ap.add_argument("--force", action="store_true",
                    help="data/<날짜>.json 이 이미 있어도 다시 수집한다")
    ap.add_argument("--timeout", type=int, default=900, help="결과 대기 최대 초 (기본 900)")
    ap.add_argument("--poll", type=int, default=45, help="폴링 간격 초 (기본 45)")
    a = ap.parse_args()

    date = a.backfill or datetime.now(KST).date().isoformat()
    target = REPO / "data" / f"{date}.json"

    git("pull", "--rebase", "-q", "origin", "main")
    if target.exists() and not a.force:
        print(f"이미 수집돼 있습니다 — {target.relative_to(REPO)}")
        print(f"OK {target}")
        return

    if a.backfill:
        args = f"--api --date {date}"
    else:
        args = f"--expect {date} --retries 4 --retry-wait 120"

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (REPO / ".trigger").write_text(f"{args}\n# requested {stamp}\n", encoding="utf-8")
    git("add", ".trigger")
    git("commit", "-q", "-m", f"trigger: {date} 수집 ({args})")
    before = git("rev-parse", "HEAD")
    git("push", "-q", "origin", "HEAD:main")
    print(f"워크플로 실행 요청: {args}")

    deadline = time.time() + a.timeout
    while time.time() < deadline:
        time.sleep(a.poll)
        git("fetch", "-q", "origin", "main")
        head = git("rev-parse", "origin/main")
        left = int(deadline - time.time())
        if head == before:
            print(f"  대기 중… (러너 시작 전, {left}s 남음)")
            continue
        git("pull", "--rebase", "-q", "origin", "main")
        if target.exists():
            print(last_run())
            print(f"OK {target}")
            return
        print(f"  새 커밋은 왔지만 {date}.json 이 없습니다 ({left}s 남음)")
        before = head

    print("--- data/_last_run.txt ---")
    print(last_run())
    raise SystemExit(f"수집 실패: {a.timeout}s 안에 data/{date}.json 이 오지 않았습니다.")


if __name__ == "__main__":
    if not os.environ.get("GH_TOKEN") and "x-access-token" not in git("remote", "get-url", "origin"):
        raise SystemExit("GH_TOKEN 이 필요합니다 (push 권한).")
    main()
