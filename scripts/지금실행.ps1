# 지금실행.cmd 를 더블클릭하면 이 파일이 실행된다 — 오늘치 브리핑을 지금 한 번 돌린다.
# 평소에는 자동실행_켜기.cmd 로 등록해 둔 평일 11:07 실행이 대신 한다.
# 이미 오늘 발행됐으면 아무것도 하지 않고 끝난다.
# (UTF-8 BOM 으로 저장할 것 — Windows PowerShell 5.1 은 BOM 이 없으면 한글을 깨뜨린다.)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$REPO = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RUNNER = Join-Path $PSScriptRoot 'run_local.ps1'
$WORK = if ($env:BRIEF_WORK) { $env:BRIEF_WORK } else { Join-Path $HOME '.hep-th-brief-work' }
$env:PATH = "$HOME\.local\bin;$env:APPDATA\npm;$env:PATH"

function fail([string]$msg) { Write-Host; Write-Host "❌ $msg"; Write-Host; exit 1 }

Write-Host '===== hep-th 브리핑 지금 실행 ====='
Write-Host

# ---------------------------------------------------------------- 준비 확인
if (-not (Test-Path $RUNNER)) { fail "run_local.ps1 을 찾지 못했습니다: $RUNNER" }

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host 'claude 명령을 찾지 못했습니다. Claude Code 를 설치하세요:'
    Write-Host '    irm https://claude.ai/install.ps1 | iex'
    fail '설치 후 새 창에서 다시 실행하세요.'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    fail 'python 을 찾지 못했습니다. Python 3 을 설치하고 PATH 에 추가하세요.'
}
if (-not (& git config user.name)) {
    fail 'git user.name 이 없어 커밋할 수 없습니다.  git config --global user.name "이름"  으로 설정하세요.'
}

# run_local.ps1 의 git pull --rebase 는 추적 중인 파일에 커밋하지 않은 변경이 있으면
# 멈춘다. 여기서 먼저 걸러야 "cannot pull with rebase" 대신 이유가 보인다.
# untracked 는 rebase 를 막지 않으므로 세지 않는다 — 중간에 실패한 실행이 남긴
# data\<날짜>.json 이 여기 걸리면 다시 돌릴 수가 없다.
$dirty = & git -C $REPO status --porcelain --untracked-files=no
if ($dirty) {
    Write-Host '⚠️  레포에 커밋하지 않은 변경이 있습니다:'
    & git -C $REPO -c core.quotepath=false status --short --untracked-files=no | ForEach-Object { "      $_" }
    Write-Host
    fail '이대로면 git pull 에서 멈춥니다. 변경을 커밋하거나 되돌린 뒤 다시 실행하세요.'
}

# ---------------------------------------------------------------- 실행
$today = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Korea Standard Time').ToString('yyyy-MM-dd')
Write-Host "   기록  $WORK\logs\$today.log"
Write-Host '   공지가 아직 안 올라왔으면 30분 간격으로 12:37 까지 기다립니다 — 창을 열어 두세요.'
Write-Host

try { & $RUNNER; $status = $LASTEXITCODE } catch { Write-Host $_; $status = 1 }

Write-Host
if ($status -eq 0) {
    Write-Host '✅ 끝났습니다.   https://cms1308.github.io/hep-th-arxiv/'
} else {
    Write-Host "❌ 실패했습니다 (종료 코드 $status). 위 기록에서 마지막 줄을 확인하세요."
}
Write-Host
exit $status
