# 실행 캡처 3장 (제출 서류용).
#  capture_1.png  GUI 첫 화면
#  capture_2.png  GUI 에서 데모 실행 후 결과 화면
#  capture_3.png  report.html 을 Edge headless --screenshot 으로
# GUI 는 런타임 훅의 캡처 모드(IAD_SMOKE_CAPTURE=1)로 띄운다: 훅이 shotN-ready 마커를 쓰면
# 이 스크립트가 창을 System.Drawing 으로 캡처하고 ackN 파일로 다음 단계를 허락한다.
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$TimeoutSec = 240
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class IadWin {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
}
"@
[void][IadWin]::SetProcessDPIAware()

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
# GUI·Edge 는 작업 폴더가 달라 상대 경로를 다르게 해석하므로 절대 경로로 바꾼다
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path
$work = Join-Path $OutDir "capture_work"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$marker = Join-Path $work "marker.txt"
Remove-Item -LiteralPath $marker -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $work -Filter "ack*" -ErrorAction SilentlyContinue | Remove-Item -Force

function Save-Shot([System.Diagnostics.Process]$p, [string]$path) {
    $p.Refresh()
    $h = $p.MainWindowHandle
    $x = 0; $y = 0; $w = [IadWin]::GetSystemMetrics(0); $hgt = [IadWin]::GetSystemMetrics(1)
    if ($h -ne [IntPtr]::Zero) {
        [void][IadWin]::SetForegroundWindow($h)
        Start-Sleep -Milliseconds 400
        $r = New-Object IadWin+RECT
        if ([IadWin]::GetWindowRect($h, [ref]$r) -and ($r.Right - $r.Left) -gt 100) {
            $x = [Math]::Max(0, $r.Left); $y = [Math]::Max(0, $r.Top)
            $w = $r.Right - $x; $hgt = $r.Bottom - $y
        }
    }
    $bmp = New-Object System.Drawing.Bitmap $w, $hgt
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Host "  캡처 저장: $path (${w}x${hgt} @ $x,$y)"
}

function Wait-Marker([System.Diagnostics.Process]$p, [string]$word, [datetime]$deadline) {
    while ((Get-Date) -lt $deadline) {
        if ((Test-Path -LiteralPath $marker) -and ((Get-Content -LiteralPath $marker -Raw) -match $word)) { return $true }
        if ($p.HasExited) { return $false }
        Start-Sleep -Milliseconds 300
    }
    return $false
}

$exe = Join-Path $AppDir "IllegalAdDetector.exe"
$env:IAD_SMOKE = "1"
$env:IAD_SMOKE_CAPTURE = "1"
$env:IAD_SMOKE_MARKER = $marker
$env:IAD_SMOKE_LOG = (Join-Path $work "gui_stderr.log")
$env:IAD_SMOKE_ACK_DIR = $work
$ok = $true
$proc = Start-Process -FilePath $exe -WorkingDirectory $AppDir -PassThru
$null = $proc.Handle
$deadline = (Get-Date).AddSeconds($TimeoutSec)
try {
    if (Wait-Marker $proc "shot1-ready" $deadline) {
        Start-Sleep -Milliseconds 500
        Save-Shot $proc (Join-Path $OutDir "capture_1.png")
        New-Item -ItemType File -Force -Path (Join-Path $work "ack1") | Out-Null
    } else { $ok = $false; Write-Host "::warning::shot1 마커 없음" }
    if ($ok -and (Wait-Marker $proc "shot2-ready" $deadline)) {
        Start-Sleep -Milliseconds 500
        Save-Shot $proc (Join-Path $OutDir "capture_2.png")
        New-Item -ItemType File -Force -Path (Join-Path $work "ack2") | Out-Null
    } elseif ($ok) { $ok = $false; Write-Host "::warning::shot2 마커 없음" }
    if (-not $proc.WaitForExit(20000)) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
} finally {
    Remove-Item Env:IAD_SMOKE, Env:IAD_SMOKE_CAPTURE, Env:IAD_SMOKE_MARKER, Env:IAD_SMOKE_LOG, Env:IAD_SMOKE_ACK_DIR -ErrorAction SilentlyContinue
}
Write-Host "---- marker ----"; if (Test-Path -LiteralPath $marker) { Get-Content -LiteralPath $marker }

# 3) report.html → Edge headless 스크린샷 (GUI 데모가 exe 폴더\demo 에 만든 리포트)
$report = Join-Path $AppDir "demo\report.html"
$edgeCands = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")
$edge = $edgeCands | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ((Test-Path -LiteralPath $report) -and $edge) {
    $png = Join-Path $OutDir "capture_3.png"
    $uri = ([Uri]::new($report)).AbsoluteUri
    $prof = Join-Path $work "edge_profile"
    $eargs = @("--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--user-data-dir=`"$prof`"",
        "--window-size=1366,1000", "--virtual-time-budget=3000", "--screenshot=`"$png`"", "`"$uri`"")
    $ep = Start-Process -FilePath $edge -ArgumentList $eargs -PassThru -WindowStyle Hidden
    if (-not $ep.WaitForExit(60000)) { Stop-Process -Id $ep.Id -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $png) { Write-Host "  캡처 저장: $png ($((Get-Item $png).Length) bytes)" } else { $ok = $false; Write-Host "::warning::Edge 스크린샷 실패" }
} else { $ok = $false; Write-Host "::warning::report.html($report) 또는 Edge($edge) 없음" }

if ($ok) { Write-Host "캡처: 3장 완료"; exit 0 }
Write-Host "캡처: 일부 실패"; exit 1
