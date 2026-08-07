#!/bin/bash
# 더블클릭하면 브리핑 자동실행을 해제한다. 다시 켜려면 자동실행_켜기.command 를 더블클릭한다.

set -euo pipefail

LABEL="com.cms1308.hep-th-brief"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "===== hep-th 브리핑 자동실행 끄기 ====="
echo

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$PLIST"

echo "✅ 껐습니다. 이제 자동으로 돌지 않습니다."
echo "   지금까지 발행된 브리핑은 그대로 남아 있습니다."
echo
read -r -n1 -p "엔터를 누르면 창이 닫힙니다." || true
