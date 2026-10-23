"""Windows 내장 OCR(Windows.Media.Ocr)을 Windows PowerShell 5.1 로 호출 (추가 번들 0). [맥에서 미검증]

공개 함수
    ocr_languages() -> list[str]                       # 설치된 OCR 인식 언어 태그 (예: ["ko", "en-US"])
    ocr_image(path, lang="ko", timeout_s=20) -> str | None
        lang 엔진이 없으면 사용자 프로필 언어 → en-US 순으로 대체. 전부 없거나 실패면 None.

주의
- pwsh(PowerShell 7)는 WinRT 투영이 없어 실패한다. 반드시 %SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe.
- 이미지 한 변이 OcrEngine.MaxImageDimension(대개 수천 px)을 넘으면 실패하므로 스크립트에서 축소 대신 거부(None)한다.
- 실행정책 우회는 -ExecutionPolicy Bypass + -Command(스크립트 파일 미작성)로 처리.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys

_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$mode = $env:IAD_OCR_MODE
if ($mode -eq 'langs') {
  $langs = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }
  @{ langs = @($langs) } | ConvertTo-Json -Compress; exit 0
}
$engine = $null
if ($env:IAD_OCR_LANG) {
  $l = New-Object Windows.Globalization.Language($env:IAD_OCR_LANG)
  if ([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($l)) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($l) }
}
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language('en-US'))) }
if ($engine -eq $null) { @{ error = 'no_engine' } | ConvertTo-Json -Compress; exit 2 }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:IAD_OCR_PATH)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$max = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
if ($dec.PixelWidth -gt $max -or $dec.PixelHeight -gt $max) { @{ error = 'too_large'; max = $max } | ConvertTo-Json -Compress; exit 3 }
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
@{ lang = $engine.RecognizerLanguage.LanguageTag; text = $res.Text } | ConvertTo-Json -Compress
"""


def _powershell() -> str | None:
    if sys.platform != "win32":
        return None
    p = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return p if os.path.isfile(p) else None


def _run(env_extra: dict, timeout_s: float) -> dict | None:
    ps = _powershell()
    if not ps:
        return None
    enc = base64.b64encode(_PS.encode("utf-16-le")).decode()
    env = {**os.environ, **env_extra}
    try:
        cp = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                            capture_output=True, timeout=timeout_s, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return json.loads(cp.stdout.decode("utf-8", errors="replace").strip().splitlines()[-1])
    except Exception:
        return None


def ocr_languages(timeout_s: float = 15) -> list[str]:
    r = _run({"IAD_OCR_MODE": "langs"}, timeout_s)
    return list(r.get("langs") or []) if r else []


def ocr_image(path: str, lang: str = "ko", timeout_s: float = 20) -> str | None:
    r = _run({"IAD_OCR_MODE": "ocr", "IAD_OCR_LANG": lang, "IAD_OCR_PATH": os.path.abspath(path)}, timeout_s)
    if not r or "error" in r:
        return None
    return r.get("text") or ""


if __name__ == "__main__":
    print("langs:", ocr_languages())
    if len(sys.argv) > 1:
        print(ocr_image(sys.argv[1]))
