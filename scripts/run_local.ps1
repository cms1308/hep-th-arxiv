# 로컬(Windows)에서 데일리 브리핑을 처음부터 끝까지 실행한다 — run_local.sh 의 Windows 판.
# 평소에는 자동실행_켜기.cmd 로 등록한 작업 스케줄러가 평일 11:07 에 이 파일을 부른다.
# 손으로 돌릴 때는 지금실행.cmd 를 더블클릭한다 (준비 확인을 먼저 한 뒤 여기로 온다).
#
# run_local.sh 와 같은 순서·같은 규칙:
#   1. git pull  2. 수집  3. 청크별 `claude -p` 병렬 번역  4. 병합·검증  5. 빌드·커밋·푸시
#   실패하면 커밋 없이 0 이 아닌 코드로 종료한다. 로그는 $BRIEF_WORK\logs\<날짜>.log.
#
# Windows 에서 다른 점:
#   - Python 이 Windows 기본 인코딩(cp949)으로 파일을 쓰지 않도록 PYTHONUTF8=1 을 켠다.
#     (build_html.py 등이 encoding 없이 open() 하므로, 수식 기호에서 UnicodeEncodeError 가 난다.)
#   - push 는 Git Credential Manager 에 저장된 자격증명을 쓴다.
#   - 청크 번역은 Start-Process 로 띄운다. PowerShell 5.1 은 네이티브 명령에 2>&1 을 걸면
#     stderr 줄을 오류로 바꿔 버리므로, 표준출력·표준오류를 파일로 직접 받는다.
#
# 이 파일은 UTF-8 (BOM 포함) 으로 저장해야 한다 — Windows PowerShell 5.1 은 BOM 이 없으면
# 한글을 ANSI 로 읽어 깨뜨린다.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$REPO = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$WORK = if ($env:BRIEF_WORK) { $env:BRIEF_WORK } else { Join-Path $HOME '.hep-th-brief-work' }
$env:BRIEF_WORK = $WORK

$SLUG = 'cms1308/hep-th-arxiv'
$CHUNK_SIZE = 6
$MODEL = 'sonnet'

# claude 설치 위치(공식 설치기 · npm)가 PATH 에 없을 수 있다.
$env:PATH = "$HOME\.local\bin;$env:APPDATA\npm;$env:PATH"

function Get-KstNow {
    [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Korea Standard Time')
}
$TODAY = (Get-KstNow).ToString('yyyy-MM-dd')

foreach ($d in 'in', 'out', 'logs') { New-Item -ItemType Directory -Force (Join-Path $WORK $d) | Out-Null }
$LOG = Join-Path $WORK "logs\$TODAY.log"
Start-Transcript -Path $LOG -Append | Out-Null

function say([string]$msg) { Write-Host ("[{0}] {1}" -f (Get-KstNow).ToString('HH:mm:ss'), $msg) }

# 네이티브 명령을 돌리고 종료 코드를 돌려준다. 표준출력·표준오류를 한 줄씩 화면과 로그에 남긴다.
# Start-Transcript 는 네이티브 명령의 출력을 그냥은 기록하지 않고, 2>&1 은 $ErrorActionPreference=Stop
# 아래서 stderr 첫 줄에 스크립트를 죽인다 — 그래서 잠시 Continue 로 내리고 Write-Host 로 흘린다.
function Run-Native {
    param([string]$exe, [string[]]$argv)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $exe @argv 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host $_.Exception.Message }
            else { Write-Host ([string]$_) }
        }
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $prev }
}

try {
    say "===== hep-th 브리핑 $TODAY ====="

    $PY = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PY) { throw 'python 을 찾지 못했습니다. Python 3 을 설치하고 PATH 에 추가하세요.' }
    $CLAUDE = (Get-Command claude -ErrorAction SilentlyContinue).Source
    if (-not $CLAUDE) { throw 'claude 명령을 찾지 못했습니다. Claude Code 가 설치돼 있는지 확인하세요.' }
    say "claude $(& $CLAUDE --version | Select-Object -First 1)"

    # 번역 프로세스를 여러 개 띄우기 전에 CLI 인증을 확인한다.
    $authOutput = & $CLAUDE auth status
    $authRc = $LASTEXITCODE
    try { $auth = ($authOutput -join "`n") | ConvertFrom-Json }
    catch { throw 'Claude 로그인 상태를 확인하지 못했습니다. 터미널에서 claude auth status 를 확인하세요.' }
    if ($authRc -ne 0 -or -not $auth.loggedIn) {
        throw 'Claude Code CLI 로그인이 필요합니다. PowerShell에서 & "$HOME\.local\bin\claude.exe" auth login 을 실행해 로그인한 뒤 지금실행.cmd 를 다시 실행하세요.'
    }
    # ------------------------------------------------------------ 1. 최신 상태
    say '1/5 git pull'
    $rc = Run-Native git @('-C', $REPO, 'pull', '--rebase', '-q', 'origin', 'main')
    if ($rc) { throw "git pull 실패 (rc=$rc)" }

    # 이미 발행된 날이면 아무것도 하지 않는다 — 워크플로가 먼저 올렸거나 오늘 이미 돌린 경우.
    # (다시 만들려면 briefs\<날짜>.html 을 지우고 실행한다.)
    if (Test-Path "$REPO\briefs\$TODAY.html") {
        say "$TODAY 는 이미 발행돼 있습니다 — 종료."
        exit 0
    }

    # ------------------------------------------------------------ 2. arXiv 수집
    if (Test-Path "$REPO\data\$TODAY.json") {
        say "2/5 수집 생략 — data\$TODAY.json 이 이미 있음"
    } else {
        say '2/5 arXiv 수집'
        $rc = Run-Native $PY @("$REPO\scripts\fetch_arxiv.py", '--expect', $TODAY,
                               '--retries', '3', '--retry-wait', '1800', '--outdir', "$REPO\data")
        if ($rc) { throw "fetch_arxiv.py 실패 (rc=$rc)" }
    }

    # fetch_arxiv.py 는 0편이면 파일을 쓰지 않는다 — 주말이거나 아직 공지 전.
    if (-not (Test-Path "$REPO\data\$TODAY.json")) {
        say '신규 0편 — 주말이거나 아직 공지 전입니다. 커밋 없이 종료.'
        exit 0
    }

    # ------------------------------------------------------------ 3. 번역
    say '3/5 청크 분할'
    $rc = Run-Native $PY @("$REPO\scripts\split_chunks.py", "$REPO\data\$TODAY.json", "$CHUNK_SIZE")
    if ($rc) { throw "split_chunks.py 실패 (rc=$rc)" }
    Remove-Item "$WORK\out\*.txt" -Force -ErrorAction SilentlyContinue

    function Get-Prompt([int]$i) {
@"
You are translating arXiv hep-th abstracts into Korean.

STEP 1. Read $WORK\in\chunk$i.json — a JSON array of papers with keys
id, title, authors, categories, abstract.

STEP 2. For each paper write a Korean translation of the abstract:
- Natural, fluent academic Korean ("~한다/~이다" 평서체).
- KEEP all technical/physics terminology in English (holography, entanglement
  entropy, black hole, CFT, AdS/CFT, Yang-Mills, supersymmetry, moduli, brane,
  S-matrix, stress tensor, gauge theory, Calabi-Yau, renormalization, ...).
  Keep all math notation, LaTeX, symbols and arXiv IDs exactly as in the original.
- Do not translate proper nouns or model names.
- Translate the FULL abstract sentence for sentence. Never summarize.

STEP 3. Write each translation to $WORK\out\<id>.txt where <id> is that paper's
id field (for example 2608.02696.txt). The file contains the Korean translation
and NOTHING else — no JSON, no quotes, no title, no markdown fences. Write LaTeX
and backslashes literally; this is plain text, so nothing needs escaping.

Return ONLY the string "chunk$i done: N papers". Do not return paper content.
"@
    }

    # --safe-mode: 전역 CLAUDE.md·훅·플러그인·MCP 를 끈다. 인증/모델/도구/권한은 그대로.
    # --allowedTools 는 가변 인자라 프롬프트를 삼킨다 — 프롬프트는 반드시 stdin 으로 넘긴다.
    # npm 설치본은 claude.cmd 라서 cmd.exe 를 거쳐야 표준입출력 리디렉션이 붙는다.
    $claudeArgs = "-p --safe-mode --model $MODEL --fallback-model opus " +
                  '--permission-mode acceptEdits --allowedTools Read Write'
    if ($CLAUDE -match '\.(cmd|bat)$') {
        $exe = "$env:SystemRoot\System32\cmd.exe"
        $argLine = "/d /c `"`"$CLAUDE`" $claudeArgs`""
    } else {
        $exe = $CLAUDE
        $argLine = $claudeArgs
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)

    # 청크 하나를 번역하는 claude 프로세스를 띄우고 프로세스 객체를 돌려준다.
    function Start-Translate([int]$i) {
        $prompt = Join-Path $WORK "in\prompt$i.txt"
        [System.IO.File]::WriteAllText($prompt, (Get-Prompt $i), $utf8)
        Start-Process -FilePath $exe -ArgumentList $argLine -WorkingDirectory $WORK `
            -RedirectStandardInput $prompt `
            -RedirectStandardOutput "$WORK\logs\$TODAY-chunk$i.out" `
            -RedirectStandardError  "$WORK\logs\$TODAY-chunk$i.err" `
            -NoNewWindow -PassThru
    }

    # 청크의 모든 논문이 비어 있지 않은 out\<id>.txt 를 갖고 있는지 확인한다.
    function Test-ChunkOk([int]$i) {
        $papers = @(Get-Content "$WORK\in\chunk$i.json" -Raw -Encoding UTF8 | ConvertFrom-Json)
        if ($papers.Count -eq 0) { return $false }
        foreach ($p in $papers) {
            $f = "$WORK\out\$($p.id).txt"
            if (-not (Test-Path $f) -or (Get-Item $f).Length -eq 0) { return $false }
        }
        return $true
    }

    $N = @(Get-ChildItem "$WORK\in" -Filter 'chunk*.json').Count
    say "번역 시작 — ${N}개 청크, model=$MODEL"
    $procs = @()
    foreach ($i in 1..$N) { $procs += Start-Translate $i }
    $procs | Wait-Process

    foreach ($i in 1..$N) {
        if (-not (Test-ChunkOk $i)) {
            say "  chunk$i 실패 — 1회 재시도"
            Start-Translate $i | Wait-Process
        }
    }

    # ------------------------------------------------------------ 4. 병합·검증
    say '4/5 병합'
    Set-Location $WORK
    $report = @(& $PY "$REPO\scripts\merge_ko.py" "$REPO\data\$TODAY.json" out papers.json)
    $mergeRc = $LASTEXITCODE
    $report | ForEach-Object { Write-Host $_ }
    [System.IO.File]::WriteAllLines("$WORK\logs\$TODAY-merge.txt", [string[]]$report, $utf8)
    if ($mergeRc) {
        say '중단 — 번역이 불완전합니다. 커밋하지 않습니다.'
        say "청크 로그: $WORK\logs\$TODAY-chunk*.out"
        exit 1
    }
    $GOT = @(Get-Content "$WORK\papers.json" -Raw -Encoding UTF8 | ConvertFrom-Json).Count

    # ------------------------------------------------------------ 5. 커밋·푸시
    $d = [DateTime]::ParseExact($TODAY, 'yyyy-MM-dd', $null)
    $DATESTR = '{0}년 {1}월 {2}일 ({3})' -f $d.Year, $d.Month, $d.Day, '월화수목금토일'[([int]$d.DayOfWeek + 6) % 7]

    say "5/5 빌드·커밋·푸시 — $DATESTR, ${GOT}편"
    $rc = Run-Native $PY @("$REPO\scripts\sync_repo.py", $SLUG, "$WORK\papers.json", $TODAY, $DATESTR)
    if ($rc) { throw "sync_repo.py 실패 (rc=$rc)" }
    say '완료 — https://cms1308.github.io/hep-th-arxiv/'
    exit 0
}
catch {
    say "오류: $($_.Exception.Message)"
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch { }
}
