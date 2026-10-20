# 자동실행_켜기.cmd 를 더블클릭하면 평일 11:07~23:37 에 30분마다 (로그인 직후에도)
# 브리핑이 저절로 돌도록 이 PC 의 작업 스케줄러에 등록한다. (macOS 의 launchd 등록에 해당.)
# 다시 더블클릭해도 안전하다 (덮어쓰기). 끄려면 자동실행_끄기.cmd 를 더블클릭한다.
# (UTF-8 BOM 으로 저장할 것 — Windows PowerShell 5.1 은 BOM 이 없으면 한글을 깨뜨린다.)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$LABEL = 'hep-th-brief'
# Actions 와 같은 간격. 매번 한 번 수집하고, 아직 갱신 전이면 다음 트리거가 다시 확인한다.
$HOUR = 11
$MINUTE = 7

$RUNNER = Join-Path $PSScriptRoot 'run_local.ps1'
$WORK = if ($env:BRIEF_WORK) { $env:BRIEF_WORK } else { Join-Path $HOME '.hep-th-brief-work' }
$env:PATH = "$HOME\.local\bin;$env:APPDATA\npm;$env:PATH"

function fail([string]$msg) { Write-Host; Write-Host "❌ $msg"; Write-Host; exit 1 }

Write-Host '===== hep-th 브리핑 자동실행 켜기 ====='
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

if ((Get-TimeZone).Id -ne 'Korea Standard Time') {
    Write-Host "⚠️  이 PC 의 시간대가 한국(KST)이 아닙니다 — 현재 $((Get-TimeZone).Id)."
    Write-Host '    브리핑은 한국 시간 11시가 아니라 이 PC 의 11시에 돕니다.'
    Write-Host
}

New-Item -ItemType Directory -Force (Join-Path $WORK 'logs') | Out-Null

# ---------------------------------------------------------------- 등록
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$at = [DateTime]::Today.AddHours($HOUR).AddMinutes($MINUTE)

# 창 없이 돈다. 표준출력은 run_local.ps1 이 $WORK\logs\<날짜>.log 에 직접 남긴다.
# 두 트리거가 같은 명령을 부르므로 run_local.ps1 이 -NotBefore 로 로그인 트리거를 거른다 —
# 주말이거나 정시 전이면 바로 끝낸다. 5분 당긴 것은 정시 트리거가 몇 초 일찍 와도 걸리지 않게.
$notBefore = $at.AddMinutes(-5).ToString('HH:mm')
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RUNNER`" -NotBefore $notBefore"

$checks = @(foreach ($offset in 0..25) {
    New-ScheduledTaskTrigger -Weekly -At $at.AddMinutes(30 * $offset) `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday
})

# 로그인 직후에도 한 번 돈다. 업데이트 재시작 뒤 잠금 화면에 머물러 정시를 놓친 날을 따라잡는다
# (실측 2026-10-15). StartWhenAvailable 은 로그아웃 상태로 놓친 정시를 로그인 뒤 돌려 주지 않는다.
# 이미 발행된 날은 run_local.ps1 이 git pull 뒤 바로 끝낸다. 지연은 네트워크가 붙을 시간.
$logon = New-ScheduledTaskTrigger -AtLogOn -User $me
$logon.Delay = 'PT2M'

# StartWhenAvailable: 꺼져 있거나 자던 시각을 놓치면 깨어난 뒤 한 번 돌린다 (launchd 와 같음).
# WakeToRun: 자는 중이면 깨운다 (pmset repeat wakeorpoweron 에 해당. 완전히 꺼진 PC 는 못 켠다).
# 배터리 관련 기본값은 "배터리면 안 돌림"이라 노트북에서 조용히 건너뛴다 — 둘 다 푼다.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)

# 로그온한 사용자 세션에서 돈다 — Git Credential Manager · claude 로그인 정보가 이 사용자의
# 것이기 때문. 로그아웃 상태에서는 돌지 않는다 (맥에서 로그아웃 상태와 같음).
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $LABEL -Action $action -Trigger ($checks + @($logon)) `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host '✅ 켰습니다.'
Write-Host
Write-Host '   언제      평일(월~금) 11:07~23:37, 30분마다 확인. 로그인하고 2분 뒤에도 확인.'
Write-Host '   이미 발행한 날은 즉시 종료. 마지막 확인까지 미발행이면 알림·Actions 백업 실행.'
Write-Host '   무엇을    arXiv hep-th 신규 논문 수집 → 한국어 번역 → 사이트 발행'
Write-Host '   결과      https://cms1308.github.io/hep-th-arxiv/'
Write-Host "   기록      $WORK\logs\"
Write-Host
Write-Host '   PC 가 꺼져 있거나 자고 있으면 그 시각엔 못 돌고, 깨어난 뒤 한 번 돕니다.'
Write-Host '   로그아웃(잠금 화면) 상태로 놓친 날은 로그인하고 2분 뒤에 돕니다.'
Write-Host '   상태 확인은 작업 스케줄러(taskschd.msc) 의 "hep-th-brief" 항목에서 합니다.'
Write-Host '   끄려면 scripts\자동실행_끄기.cmd 를 더블클릭하세요.'
Write-Host
exit 0
