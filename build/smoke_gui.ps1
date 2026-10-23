# GUI exe 스모크 테스트.
# 런타임 훅(build/hooks/rth_iad.py)이 IAD_SMOKE=1 일 때 tkinter mainloop 진입 시
# 마커 파일을 쓰고 N초 뒤 창을 닫는다. 판정:
#   PASS  = 마커에 mainloop-entered 가 있고, 프로세스가 0 으로 끝나거나 살아 있음
#   FAIL  = 제한 시간 안에 마커가 안 생김(시작 중 크래시·예외 대화상자) 또는 비정상 종료 코드
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [int]$TimeoutSec = 60,
    [int]$CloseAfterSec = 5,
    [string]$WorkDir = ""
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Exe)) { throw "GUI exe 없음: $Exe" }
if (-not $WorkDir) { $WorkDir = Join-Path ([IO.Path]::GetTempPath()) ("iad_gui_smoke_" + [guid]::NewGuid().ToString("N")) }
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$marker = Join-Path $WorkDir "gui_marker.txt"
$log = Join-Path $WorkDir "gui_stderr.log"
Remove-Item -LiteralPath $marker, $log -ErrorAction SilentlyContinue

$env:IAD_SMOKE = "1"
$env:IAD_SMOKE_MARKER = $marker
$env:IAD_SMOKE_LOG = $log
$env:IAD_SMOKE_SECONDS = "$CloseAfterSec"

Write-Host "GUI 실행: $Exe"
$proc = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path -Parent $Exe) -PassThru
$null = $proc.Handle  # ExitCode 를 나중에 읽으려면 핸들을 먼저 잡아 둬야 한다
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$entered = $false
while ((Get-Date) -lt $deadline) {
    if ((Test-Path -LiteralPath $marker) -and ((Get-Content -LiteralPath $marker -Raw) -match "mainloop-entered")) { $entered = $true; break }
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 500
}

$result = "FAIL"
$reason = ""
if ($entered) {
    # 창이 떴다. 자동 닫힘 후 종료를 기다린다.
    $exited = $proc.WaitForExit(($CloseAfterSec + 20) * 1000)
    if ($exited) {
        if ($proc.ExitCode -eq 0) { $result = "PASS"; $reason = "mainloop 진입 후 정상 종료(exit 0)" }
        else { $reason = "mainloop 진입 후 비정상 종료 exit=$($proc.ExitCode)" }
    } else {
        $result = "PASS"; $reason = "mainloop 진입, 창 닫힌 뒤에도 프로세스 잔존(백그라운드 스레드 추정) - 강제 종료"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
} elseif ($proc.HasExited) {
    $reason = "창이 뜨기 전에 종료 exit=$($proc.ExitCode)"
} else {
    try { $title = (Get-Process -Id $proc.Id).MainWindowTitle } catch { $title = "" }
    $reason = "제한 시간 ${TimeoutSec}s 안에 mainloop 미진입 (창 제목='$title'; 예외 대화상자 가능성)"
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

Write-Host "---- marker ----"; if (Test-Path -LiteralPath $marker) { Get-Content -LiteralPath $marker }
Write-Host "---- stderr log ----"; if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Encoding utf8 }
Write-Host "GUI 스모크: $result ($reason)"

Remove-Item Env:IAD_SMOKE, Env:IAD_SMOKE_MARKER, Env:IAD_SMOKE_LOG, Env:IAD_SMOKE_SECONDS -ErrorAction SilentlyContinue
if ($result -ne "PASS") { exit 1 }
exit 0
