#!/bin/bash
# 더블클릭하면 오늘치 브리핑을 지금 한 번 돌린다.
# 평소에는 자동실행_켜기.command 로 등록해 둔 평일 11:07 실행이 대신 한다.
# 이미 오늘 발행됐으면 아무것도 하지 않고 끝난다.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO/scripts/run_local.sh"
WORK="${BRIEF_WORK:-$HOME/.hep-th-brief-work}"

fail() { echo; echo "❌ $*"; echo; read -r -n1 -p "엔터를 누르면 창이 닫힙니다." || true; exit 1; }

echo "===== hep-th 브리핑 지금 실행 ====="
echo

# ---------------------------------------------------------------- 준비 확인
[ -f "$RUNNER" ] || fail "run_local.sh 를 찾지 못했습니다: $RUNNER"

if ! PATH="$HOME/.local/bin:$PATH" command -v claude >/dev/null; then
  fail "claude 명령을 찾지 못했습니다. Claude Code 가 설치돼 있는지 확인하세요."
fi

# run_local.sh 는 깨끗한 트리를 전제로 git pull --rebase 를 한다. 여기서 먼저 걸러야
# "cannot pull with rebase" 라는 알아보기 어려운 메시지 대신 이유가 보인다.
if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
  echo "⚠️  레포에 커밋하지 않은 변경이 있습니다:"
  git -C "$REPO" -c core.quotepath=false status --short | sed 's/^/      /'
  echo
  fail "이대로면 git pull 에서 멈춥니다. 변경을 커밋하거나 되돌린 뒤 다시 실행하세요."
fi

# ---------------------------------------------------------------- 실행
echo "   기록  $WORK/logs/$(TZ=Asia/Seoul date +%F).log"
echo "   공지가 아직 안 올라왔으면 30분 간격으로 12:37 까지 기다립니다 — 창을 열어 두세요."
echo
/bin/bash "$RUNNER" && STATUS=0 || STATUS=$?

echo
if [ "$STATUS" -eq 0 ]; then
  echo "✅ 끝났습니다.   https://cms1308.github.io/hep-th-arxiv/"
else
  echo "❌ 실패했습니다 (종료 코드 $STATUS). 위 기록에서 마지막 줄을 확인하세요."
fi
echo
read -r -n1 -p "엔터를 누르면 창이 닫힙니다." || true
