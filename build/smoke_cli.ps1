# CLI exe 스모크 테스트.
#  1) src/fixtures 를 python -m http.server 로 띄운다.
#  2) iad-cli.exe 로 로컬 사이트를 크롤링한다(정적 모드).
#  3) 확인: 종료 코드 0, 구동 파일 폴더에 result.json 생성, UTF-8 BOM 없음, JSON 파싱 가능,
#     meta/findings 키 존재, result_extra.json(있으면) 동일 검사, HTML 리포트 생성.
#  4) --demo --no-open: 내장 테스트베드 스캔 → <exe 폴더>/demo 에 result.json·report.html·demo_labels.json.
#  5) -ExpectRenderFallback(정적 전용 빌드): --render 를 줘도 안내 로그를 남기고 정적 분석으로 끝나는지.
#  6) 강제 종료 내구성: 페이지 수를 크게·간격을 길게 실행하고 5초 뒤 kill → exe 폴더 result.json 이 유효 JSON(meta 포함)인지.
#  요약은 <OutDir>/smoke_summary.txt 에 남긴다.
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$FixturesDir,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$Port = 8765,
    [int]$TimeoutSec = 600,
    [switch]$ExpectRenderFallback
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)   # exe 의 UTF-8 출력을 그대로 읽는다
$failures = New-Object System.Collections.Generic.List[string]
function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Host "  [OK]   $what" } else { Write-Host "  [FAIL] $what"; $failures.Add($what) }
}

function Invoke-Cli([string[]]$CliArgs, [string]$Tag) {
    # stdout/stderr 를 파일로 받아 마지막 줄을 보여 주고 종료 코드를 돌려준다.
    $logOut = Join-Path $OutDir "cli_${Tag}_stdout.log"
    $logErr = Join-Path $OutDir "cli_${Tag}_stderr.log"
    Write-Host "== iad-cli $($CliArgs -join ' ')"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $cli -ArgumentList ($CliArgs | ForEach-Object { "`"$_`"" }) -WorkingDirectory $OutDir `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru -NoNewWindow
    $null = $p.Handle
    if (-not $p.WaitForExit($TimeoutSec * 1000)) { Stop-Process -Id $p.Id -Force; throw "CLI($Tag) 시간 초과 ${TimeoutSec}s" }
    $sw.Stop()
    # 함수 반환값에 섞이지 않게 Out-Host 로 보낸다
    Get-Content -LiteralPath $logOut -Encoding utf8 | Select-Object -Last 25 | Out-Host
    Write-Host "---- stderr ----"; Get-Content -LiteralPath $logErr -Encoding utf8 | Select-Object -Last 25 | Out-Host
    Write-Host ("CLI($Tag) 소요 {0:N1}s" -f $sw.Elapsed.TotalSeconds)
    return @{ Code = $p.ExitCode; Out = (Get-Content -LiteralPath $logOut -Raw -Encoding utf8) + (Get-Content -LiteralPath $logErr -Raw -Encoding utf8) }
}
function Test-ResultJson([string]$path, [string]$label, [bool]$needFindings) {
    if (-not (Test-Path -LiteralPath $path)) { Check $false "$label 생성 ($path)"; return }
    Check $true "$label 생성 ($path)"
    $bytes = [IO.File]::ReadAllBytes($path)
    $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    Check (-not $bom) "$label UTF-8 BOM 없음"
    try {
        $json = [Text.UTF8Encoding]::new($false, $true).GetString($bytes) | ConvertFrom-Json
        Check ($null -ne $json.meta) "$label meta 키"
        Check ($json.PSObject.Properties.Name -contains "findings") "$label findings 키"
        foreach ($k in @("topic", "entry_url", "started_at", "finished_at", "elapsed_sec")) {
            Check ($json.meta.PSObject.Properties.Name -contains $k) "$label meta.$k"
        }
        $n = @($json.findings).Count
        Write-Host "  $label findings = $n 건"
        if ($needFindings) { Check ($n -gt 0) "$label 검출 1건 이상" }
    } catch { Check $false "$label JSON 파싱 ($($_.Exception.Message))" }
}

$summary = New-Object System.Collections.Generic.List[string]

$cli = Join-Path $AppDir "iad-cli.exe"
if (-not (Test-Path -LiteralPath $cli)) { throw "CLI exe 없음: $cli" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
# 테스트 사이트 선택: <Fixtures>/index.html → <Fixtures>/dev/index.html → build/smoke_site
if (-not (Test-Path -LiteralPath (Join-Path $FixturesDir "index.html")) -and (Test-Path -LiteralPath (Join-Path $FixturesDir "dev/index.html"))) {
    $FixturesDir = Join-Path $FixturesDir "dev"
}
if (-not (Test-Path -LiteralPath (Join-Path $FixturesDir "index.html"))) {
    Write-Host "::warning::$FixturesDir 에 index.html 이 없어 build/smoke_site 로 대체"
    $FixturesDir = Join-Path $PSScriptRoot "smoke_site"
}
$FixturesDir = (Resolve-Path -LiteralPath $FixturesDir).Path
Write-Host "테스트 사이트: $FixturesDir"

# 이전 결과 제거 (구동 파일 폴더에 새로 생기는지 보려고)
Remove-Item -LiteralPath (Join-Path $AppDir "result.json"), (Join-Path $AppDir "result_extra.json") -ErrorAction SilentlyContinue

# 1) 로컬 웹서버
$server = Start-Process -FilePath python -ArgumentList @("-m", "http.server", "$Port", "--bind", "127.0.0.1", "--directory", "`"$FixturesDir`"") -PassThru -WindowStyle Hidden
try {
    $up = $false
    for ($i = 0; $i -lt 40; $i++) {
        try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2 | Out-Null; $up = $true; break } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $up) { throw "http.server 가 뜨지 않음" }

    $entry = "http://127.0.0.1:$Port/"
    if (Test-Path -LiteralPath (Join-Path $FixturesDir "index.html")) { $entry = "http://127.0.0.1:$Port/index.html" }

    # 2) CLI 실행 (--help 먼저: 한글 도움말 출력이 파이프에서 깨지지 않는지)
    Write-Host "== iad-cli --help"
    $helpOut = & $cli --help 2>&1 | Out-String
    Write-Host $helpOut
    Check ($LASTEXITCODE -eq 0) "--help 종료 코드 0"

    $reportDir = Join-Path $OutDir "리포트"
    $cliArgs = @("--url", $entry, "--out", $reportDir, "--delay", "0", "--depth", "3")
    Write-Host "== iad-cli $($cliArgs -join ' ')"
    $logFile = Join-Path $OutDir "cli_stdout.log"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $cli -ArgumentList ($cliArgs | ForEach-Object { "`"$_`"" }) -WorkingDirectory $OutDir `
        -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $OutDir "cli_stderr.log") -PassThru -NoNewWindow
    $null = $p.Handle
    if (-not $p.WaitForExit($TimeoutSec * 1000)) { Stop-Process -Id $p.Id -Force; throw "CLI 시간 초과 ${TimeoutSec}s" }
    $sw.Stop()
    Get-Content -LiteralPath $logFile -Encoding utf8 | Select-Object -Last 40
    Write-Host "---- stderr ----"; Get-Content -LiteralPath (Join-Path $OutDir "cli_stderr.log") -Encoding utf8 | Select-Object -Last 40
    Write-Host ("CLI 소요 {0:N1}s" -f $sw.Elapsed.TotalSeconds)
    Check ($p.ExitCode -eq 0) "CLI 종료 코드 0 (실제 $($p.ExitCode))"

    # 3) result.json / result_extra.json 검사 (구동 파일 폴더)
    foreach ($name in @("result.json", "result_extra.json")) {
        $path = Join-Path $AppDir $name
        $exists = Test-Path -LiteralPath $path
        if ($name -eq "result.json") { Check $exists "$name 이 구동 파일 폴더에 생성됨 ($path)" }
        elseif (-not $exists) { Write-Host "  [--]   $name 없음(선택)"; continue }
        if (-not $exists) { continue }
        $bytes = [IO.File]::ReadAllBytes($path)
        $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
        Check (-not $bom) "$name UTF-8 BOM 없음"
        try {
            $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
            $json = $text | ConvertFrom-Json
            Check ($null -ne $json.meta) "$name meta 키"
            Check ($json.PSObject.Properties.Name -contains "findings") "$name findings 키"
            foreach ($k in @("topic", "entry_url", "started_at", "finished_at", "elapsed_sec")) {
                Check ($json.meta.PSObject.Properties.Name -contains $k) "$name meta.$k"
            }
            $n = @($json.findings).Count
            Write-Host "  $name findings = $n 건"
            if ($name -eq "result.json") {
                Check ($n -gt 0) "result.json 에 검출 1건 이상 (fixtures 에 은닉 광고가 있으므로)"
                $techs = @($json.findings | ForEach-Object { $_.technique } | Sort-Object -Unique)
                Write-Host "  technique: $($techs -join ', ')"
            }
            Copy-Item -LiteralPath $path -Destination (Join-Path $OutDir $name) -Force
        } catch {
            Check $false "$name JSON 파싱 ($($_.Exception.Message))"
        }
    }

    # HTML 리포트
    $html = @(Get-ChildItem -LiteralPath $OutDir -Recurse -Filter *.html -ErrorAction SilentlyContinue)
    Check ($html.Count -gt 0) "HTML 리포트 생성 ($($html.FullName -join '; '))"
    if ($html.Count -gt 0) {
        $content = [IO.File]::ReadAllText($html[0].FullName, [Text.Encoding]::UTF8)
        Check ($content.Length -gt 500) "HTML 리포트 내용 있음 ($($content.Length) chars)"
    }

    # 4) --demo (브라우저 자동 열기 끔). 결과는 기본 위치 <exe 폴더>/demo 에 생긴다.
    $demoDir = Join-Path $AppDir "demo"
    if (Test-Path -LiteralPath $demoDir) { Remove-Item -LiteralPath $demoDir -Recurse -Force }
    $swDemo = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-Cli @("--demo", "--no-open") "demo"
    $swDemo.Stop()
    Check ($r.Code -eq 0) "--demo 종료 코드 0 (실제 $($r.Code))"
    $bLines = @($r.Out -split "`r?`n" | Where-Object { $_ -match "브라우저 단계" } | ForEach-Object { $_.Trim() })
    Check ($bLines.Count -gt 0) "--demo 로그에 브라우저 단계 실행/생략 사유"
    $summary.Add(("demo 소요 {0:N1}s" -f $swDemo.Elapsed.TotalSeconds))
    foreach ($l in $bLines) { $summary.Add("demo 브라우저: $l") }
    $tLine = @($r.Out -split "`r?`n" | Where-Object { $_ -match "탐지 완료|데모 결과" } | ForEach-Object { $_.Trim() })
    foreach ($l in $tLine) { $summary.Add("demo: $l") }
    Test-ResultJson (Join-Path $demoDir "result.json") "demo/result.json" $true
    Check (Test-Path -LiteralPath (Join-Path $demoDir "demo_labels.json")) "demo/demo_labels.json 생성"
    $demoHtml = @(Get-ChildItem -LiteralPath $demoDir -Filter *.html -ErrorAction SilentlyContinue)
    Check ($demoHtml.Count -gt 0) "demo HTML 리포트 생성 ($($demoHtml.FullName -join '; '))"
    if (Test-Path -LiteralPath $demoDir) { Copy-Item -Recurse -Force -LiteralPath $demoDir -Destination (Join-Path $OutDir "demo") }

    # 5) 정적 전용 빌드에서 --render: 안내 로그 후 정적 분석으로 정상 종료해야 한다.
    if ($ExpectRenderFallback) {
        $fbDir = Join-Path $OutDir "렌더 폴백"
        $r = Invoke-Cli @("--url", $entry, "--render", "--result-dir", $fbDir, "--delay", "0", "--depth", "3") "render_fallback"
        Check ($r.Code -eq 0) "--render(정적 전용) 종료 코드 0 (실제 $($r.Code))"
        $fbLine = @($r.Out -split "`r?`n" | Where-Object { $_ -match "렌더 비교 생략|렌더 비교를 사용할 수 없어" })
        Check ($fbLine.Count -gt 0) "--render 선택 시 안내 로그 ('$($fbLine -join ' / ')')"
        Test-ResultJson (Join-Path $fbDir "result.json") "렌더 폴백 result.json" $true
        $summary.Add("render 폴백: $($fbLine -join ' / ')")
    }

    # 6) 강제 종료 내구성 (TerminateProcess: 종료 핸들러가 돌 기회 없음)
    $resPath = Join-Path $AppDir "result.json"
    Remove-Item -LiteralPath $resPath, (Join-Path $AppDir "result_extra.json") -ErrorAction SilentlyContinue
    $killArgs = @("--url", $entry, "--max-pages", "1000", "--depth", "10", "--delay", "1")
    Write-Host "== (강제 종료) iad-cli $($killArgs -join ' ')"
    $t0 = Get-Date
    $kp = Start-Process -FilePath $cli -ArgumentList ($killArgs | ForEach-Object { "`"$_`"" }) -WorkingDirectory $OutDir `
        -RedirectStandardOutput (Join-Path $OutDir "cli_kill_stdout.log") -RedirectStandardError (Join-Path $OutDir "cli_kill_stderr.log") -PassThru -NoNewWindow
    $null = $kp.Handle
    Start-Sleep -Seconds 5
    $alive = -not $kp.HasExited
    Check $alive "강제 종료 시점(5초)에 아직 실행 중"
    Stop-Process -Id $kp.Id -Force -ErrorAction SilentlyContinue
    $null = $kp.WaitForExit(10000)
    Get-Content -LiteralPath (Join-Path $OutDir "cli_kill_stdout.log") -Encoding utf8 | Select-Object -Last 8 | Out-Host
    $fresh = (Test-Path -LiteralPath $resPath) -and ((Get-Item -LiteralPath $resPath).LastWriteTime -ge $t0.AddSeconds(-1))
    Check $fresh "강제 종료 후 result.json 이 이번 실행에서 기록됨"
    Test-ResultJson $resPath "강제 종료 후 result.json" $false
    if (Test-Path -LiteralPath $resPath) {
        Copy-Item -LiteralPath $resPath -Destination (Join-Path $OutDir "result_after_kill.json") -Force
        try {
            $kj = [IO.File]::ReadAllText($resPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
            $summary.Add("kill(5s): 유효 JSON, findings $(@($kj.findings).Count)건, meta.elapsed_sec=$($kj.meta.elapsed_sec), finished_at=$($kj.meta.finished_at)")
        } catch { $summary.Add("kill(5s): JSON 파싱 실패 $($_.Exception.Message)") }
    } else { $summary.Add("kill(5s): result.json 없음") }
    $tmpLeft = @(Get-ChildItem -LiteralPath $AppDir -Filter "*.tmp" -ErrorAction SilentlyContinue)
    Write-Host "  exe 폴더 임시파일 잔존: $($tmpLeft.Count)개"
}
finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
}

$summary.Add("실패 검사 $($failures.Count)건")
$summary | Set-Content -LiteralPath (Join-Path $OutDir "smoke_summary.txt") -Encoding utf8
Write-Host "---- 요약 ----"; $summary | ForEach-Object { Write-Host "  $_" }

if ($failures.Count -gt 0) {
    Write-Host "CLI 스모크: FAIL ($($failures.Count)건)"
    $failures | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "CLI 스모크: PASS"
exit 0
