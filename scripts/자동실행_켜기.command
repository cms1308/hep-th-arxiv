#!/bin/bash
# 더블클릭하면 평일 11:00 에 브리핑이 저절로 돌도록 이 맥에 등록한다.
# 다시 더블클릭해도 안전하다 (덮어쓰기). 끄려면 자동실행_끄기.command 를 더블클릭한다.

set -euo pipefail

LABEL="com.cms1308.hep-th-brief"
HOUR=11
MINUTE=0

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO/scripts/run_local.sh"
WORK="${BRIEF_WORK:-$HOME/.hep-th-brief-work}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

fail() { echo; echo "❌ $*"; echo; read -r -n1 -p "엔터를 누르면 창이 닫힙니다." || true; exit 1; }

echo "===== hep-th 브리핑 자동실행 켜기 ====="
echo

# ---------------------------------------------------------------- 준비 확인
[ -f "$RUNNER" ] || fail "run_local.sh 를 찾지 못했습니다: $RUNNER"

if ! PATH="$HOME/.local/bin:$PATH" command -v claude >/dev/null; then
  fail "claude 명령을 찾지 못했습니다. Claude Code 가 설치돼 있는지 확인하세요."
fi

if [ "$(date '+%Z')" != "KST" ]; then
  echo "⚠️  이 맥의 시간대가 한국(KST)이 아닙니다 — 현재 $(date '+%Z')."
  echo "    브리핑은 한국 시간 11시가 아니라 이 맥의 11시에 돕니다."
  echo
fi

mkdir -p "$HOME/Library/LaunchAgents" "$WORK/logs"

# ---------------------------------------------------------------- 등록 파일 작성
# launchd 는 요일 범위를 모른다 — 월~금을 하나씩 적는다.
{
  cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$RUNNER</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
XML
  for day in 1 2 3 4 5; do
    echo "    <dict><key>Weekday</key><integer>$day</integer>"
    echo "          <key>Hour</key><integer>$HOUR</integer>"
    echo "          <key>Minute</key><integer>$MINUTE</integer></dict>"
  done
  cat <<XML
  </array>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$WORK/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$WORK/logs/launchd.log</string>
</dict>
</plist>
XML
} > "$PLIST"

plutil -lint "$PLIST" >/dev/null || fail "등록 파일이 잘못 만들어졌습니다: $PLIST"

# ---------------------------------------------------------------- 등록
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
launchctl enable "gui/$UID/$LABEL"

echo "✅ 켰습니다."
echo
echo "   언제      평일(월~금) 오전 $(printf '%d:%02d' "$HOUR" "$MINUTE")"
echo "   무엇을    arXiv hep-th 신규 논문 수집 → 한국어 번역 → 사이트 발행"
echo "   결과      https://cms1308.github.io/hep-th-arxiv/"
echo "   기록      $WORK/logs/"
echo
echo "   맥이 꺼져 있거나 자고 있으면 그 시각엔 못 돌고, 깨어난 뒤 한 번 돕니다."
echo "   끄려면 scripts/자동실행_끄기.command 를 더블클릭하세요."
echo
read -r -n1 -p "엔터를 누르면 창이 닫힙니다." || true
