# 자동실행_끄기.cmd 를 더블클릭하면 이 파일이 실행된다 — 브리핑 자동실행을 해제한다.
# 다시 켜려면 자동실행_켜기.cmd 를 더블클릭한다.
# (UTF-8 BOM 으로 저장할 것 — Windows PowerShell 5.1 은 BOM 이 없으면 한글을 깨뜨린다.)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$LABEL = 'hep-th-brief'

Write-Host '===== hep-th 브리핑 자동실행 끄기 ====='
Write-Host

if (Get-ScheduledTask -TaskName $LABEL -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $LABEL -Confirm:$false
}

Write-Host '✅ 껐습니다. 이제 자동으로 돌지 않습니다.'
Write-Host '   지금까지 발행된 브리핑은 그대로 남아 있습니다.'
Write-Host
exit 0
