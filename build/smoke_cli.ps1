# CLI exe 스모크 테스트.
#  1) src/fixtures 를 python -m http.server 로 띄운다.
#  2) iad-cli.exe 로 로컬 사이트를 크롤링한다(정적 모드).
#  3) 확인: 종료 코드 0, 구동 파일 폴더에 result.json 생성, UTF-8 BOM 없음, JSON 파싱 가능,
#     meta/findings 키 존재, result_extra.json(있으면) 동일 검사, HTML 리포트 생성.
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$FixturesDir,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$Port = 8765,
    [int]$TimeoutSec = 600
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)   # exe 의 UTF-8 출력을 그대로 읽는다
$failures = New-Object System.Collections.Generic.List[string]
function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Host "  [OK]   $what" } else { Write-Host "  [FAIL] $what"; $failures.Add($what) }
}

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
}
finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
}

if ($failures.Count -gt 0) {
    Write-Host "CLI 스모크: FAIL ($($failures.Count)건)"
    $failures | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "CLI 스모크: PASS"
exit 0
