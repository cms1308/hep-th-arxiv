#!/bin/bash
# 로컬(macOS)에서 데일리 브리핑을 처음부터 끝까지 실행한다.
# launchd 가 매 평일 11:00 KST 에 이걸 부른다. 수동 실행도 같은 명령이다.
#
# 브리핑 컨테이너 절차(RUNBOOK.md)와 다른 점:
#   - arXiv 를 이 머신에서 직접 호출한다. WebFetch 캐시 문제가 없으므로
#     .trigger push → GitHub Actions → 결과 커밋 폴링 왕복이 통째로 필요 없다.
#   - 번역은 청크마다 `claude -p` 프로세스를 하나씩 띄워 병렬로 돌린다.
#     한 세션이 서브에이전트를 부리는 것보다 실패한 청크만 다시 돌리기 쉽다.
#   - push 는 keychain 에 저장된 git 자격증명을 쓴다. GH_TOKEN 이 필요 없다.
#
# 실패하면 커밋 없이 0 이 아닌 코드로 종료한다. 로그는 $BRIEF_WORK/logs/<날짜>.log.

set -euo pipefail

# launchd 는 PATH 를 거의 비운 채 부른다. 필요한 것만 명시한다.
export PATH="$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PY=/usr/bin/python3

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${BRIEF_WORK:-$HOME/.hep-th-brief-work}"
export BRIEF_WORK="$WORK"

SLUG=cms1308/hep-th-arxiv
CHUNK_SIZE=6
MODEL=sonnet

TODAY="$(TZ=Asia/Seoul date +%F)"
mkdir -p "$WORK/in" "$WORK/out" "$WORK/logs"
LOG="$WORK/logs/$TODAY.log"
exec > >(tee -a "$LOG") 2>&1

say() { echo "[$(TZ=Asia/Seoul date +%T)] $*"; }

say "===== hep-th 브리핑 $TODAY ====="
say "claude $(claude --version 2>&1 | head -1)"

# ---------------------------------------------------------------- 1. 최신 상태
say "1/5 git pull"
git -C "$REPO" pull --rebase -q origin main

# ---------------------------------------------------------------- 2. arXiv 수집
if [ -f "$REPO/data/$TODAY.json" ]; then
  say "2/5 수집 생략 — data/$TODAY.json 이 이미 있음"
else
  say "2/5 arXiv 수집"
  "$PY" "$REPO/scripts/fetch_arxiv.py" --expect "$TODAY" \
        --retries 4 --retry-wait 120 --outdir "$REPO/data"
fi

# fetch_arxiv.py 는 0편이면 파일을 쓰지 않는다 — 주말이거나 아직 공지 전.
if [ ! -f "$REPO/data/$TODAY.json" ]; then
  say "신규 0편 — 주말이거나 아직 공지 전입니다. 커밋 없이 종료."
  exit 0
fi

# ---------------------------------------------------------------- 3. 번역
say "3/5 청크 분할"
"$PY" "$REPO/scripts/split_chunks.py" "$REPO/data/$TODAY.json" "$CHUNK_SIZE"
rm -f "$WORK"/out/*.txt

prompt_for() {
  cat <<EOF
You are translating arXiv hep-th abstracts into Korean.

STEP 1. Read $WORK/in/chunk$1.json — a JSON array of papers with keys
id, title, authors, categories, abstract.

STEP 2. For each paper write a Korean translation of the abstract:
- Natural, fluent academic Korean ("~한다/~이다" 평서체).
- KEEP all technical/physics terminology in English (holography, entanglement
  entropy, black hole, CFT, AdS/CFT, Yang-Mills, supersymmetry, moduli, brane,
  S-matrix, stress tensor, gauge theory, Calabi-Yau, renormalization, ...).
  Keep all math notation, LaTeX, symbols and arXiv IDs exactly as in the original.
- Do not translate proper nouns or model names.
- Translate the FULL abstract sentence for sentence. Never summarize.

STEP 3. Write each translation to $WORK/out/<id>.txt where <id> is that paper's
id field (for example 2608.02696.txt). The file contains the Korean translation
and NOTHING else — no JSON, no quotes, no title, no markdown fences. Write LaTeX
and backslashes literally; this is plain text, so nothing needs escaping.

Return ONLY the string "chunk$1 done: N papers". Do not return paper content.
EOF
}

# --safe-mode: 전역 CLAUDE.md·훅·플러그인·MCP 를 끈다. 인증/모델/도구/권한은 그대로.
# --allowedTools 는 가변 인자라 프롬프트를 삼킨다 — 프롬프트는 반드시 stdin 으로 넘긴다.
translate() {
  prompt_for "$1" | claude -p --safe-mode \
      --model "$MODEL" --fallback-model opus \
      --permission-mode acceptEdits \
      --allowedTools "Read" "Write" \
      > "$WORK/logs/$TODAY-chunk$1.out" 2>&1
}

# 청크의 모든 논문이 비어 있지 않은 out/<id>.txt 를 갖고 있는지 확인한다.
chunk_ok() {
  "$PY" -c 'import json, os, sys
papers = json.load(open(sys.argv[1]))
outdir = sys.argv[2]
def ok(p):
    f = os.path.join(outdir, p["id"] + ".txt")
    return os.path.isfile(f) and os.path.getsize(f) > 0
sys.exit(0 if papers and all(ok(p) for p in papers) else 1)' \
    "$WORK/in/chunk$1.json" "$WORK/out" 2>/dev/null
}

N=$(find "$WORK/in" -name 'chunk*.json' | wc -l | tr -d ' ')
say "번역 시작 — $N개 청크, model=$MODEL"
for i in $(seq 1 "$N"); do translate "$i" || true & done
wait

for i in $(seq 1 "$N"); do
  if ! chunk_ok "$i"; then
    say "  chunk$i 실패 — 1회 재시도"
    translate "$i" || true
  fi
done

# ---------------------------------------------------------------- 4. 병합·검증
say "4/5 병합"
cd "$WORK"
if ! "$PY" "$REPO/scripts/merge_ko.py" "$REPO/data/$TODAY.json" out papers.json \
        | tee "$WORK/logs/$TODAY-merge.txt"; then
  say "중단 — 번역이 불완전합니다. 커밋하지 않습니다."
  say "청크 로그: $WORK/logs/$TODAY-chunk*.out"
  exit 1
fi
GOT=$("$PY" -c 'import json;print(len(json.load(open("papers.json"))))')

# ---------------------------------------------------------------- 5. 커밋·푸시
DATESTR=$("$PY" -c 'import sys,datetime
d=datetime.date.fromisoformat(sys.argv[1])
print("%d년 %d월 %d일 (%s)" % (d.year, d.month, d.day, "월화수목금토일"[d.weekday()]))' "$TODAY")

say "5/5 빌드·커밋·푸시 — $DATESTR, ${GOT}편"
"$PY" "$REPO/scripts/sync_repo.py" "$SLUG" "$WORK/papers.json" "$TODAY" "$DATESTR"
say "완료 — https://cms1308.github.io/hep-th-arxiv/"
