"""이미지 배너 글자 OCR 단계(Windows 전용, ETC `IMAGE_TEXT_AD`): Windows 내장 OCR(Windows.Media.Ocr)을 Windows PowerShell 5.1 로 호출한다(추가 번들 0).

- 대상: 텍스트 없는 `<a><img></a>` 배너, alt/title 에 배너·광고·이벤트가 있는 img, IMAGE_BANNER_AD 후보 이미지(동일 사이트·외부 모두, data: URI 포함).
  이미지당 2MB·png/jpg/gif(첫 프레임)/bmp, 전체 40개, 이미지당 10초, 단계 120초, 남은 전체 시간 예산 안에서만.
- 한 번의 powershell 호출로 여러 이미지를 일괄 처리(프로세스 기동 비용 1회). 스크립트는 UTF-16LE base64 `-EncodedCommand`(BOM·코드페이지 문제 회피),
  출력은 [Console]::OutputEncoding=UTF-8 로 받아 한 이미지당 JSON 한 줄. 언어는 ko → 사용자 프로필 언어 → en-US 순, 엔진이 없으면 생략.
  MaxImageDimension 을 넘는 이미지는 BitmapTransform 으로 축소해 인식한다.
- OCR 텍스트는 기존 정규화·키워드 사전으로 판정하고 게이트(키워드 ≥2.0 또는 범주 합 ≥3.0, 행정 문맥 아님)를 지나면 ETC 로만 보고한다
  (result.json 4종에 넣지 않는다 — OCR 오인식·캠페인 배너 위험, 이미지 글자는 요강 4종 기법이 아님).
- Windows 가 아니거나 powershell.exe 가 없으면 조용히 생략. 실패·예외·타임아웃은 한 줄 경고 후 계속. 테스트용으로 IAD_OCR_EXE(가짜 실행기 .py)를 받는다.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .keywords import match_keywords_levels
from .links import host_of
from .models import Finding, Page

MAX_IMAGES = 40
MAX_IMAGE_BYTES = 2_000_000
STAGE_BUDGET = 120.0
PER_IMAGE_SEC = 10.0
MIN_KEYWORD = 2.0
MIN_SUM = 3.0
ALT_HINTS = ("배너", "광고", "이벤트", "banner", "ad", "ads", "event", "프로모션", "promo", "sponsor")

_MAGIC = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg", b"GIF8": ".gif", b"BM": ".bmp"}

# 입력: 환경변수 IAD_OCR_LIST = 경로 목록 JSON 파일. 출력: 이미지당 {"i":번호,"lang":태그,"text":글자} 또는 {"i":번호,"error":사유} 한 줄.
PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapTransform, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t, [int]$ms) {
  $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
  if (-not $task.Wait($ms)) { throw 'timeout' }
  $task.Result
}
$engine = $null
foreach ($tag in @('ko')) {
  $l = New-Object Windows.Globalization.Language($tag)
  if ([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($l)) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($l) }
  if ($engine -ne $null) { break }
}
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language('en-US'))) }
if ($engine -eq $null) { Write-Output ('{"error":"no_engine"}'); exit 2 }
$max = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
$paths = Get-Content -LiteralPath $env:IAD_OCR_LIST -Raw -Encoding UTF8 | ConvertFrom-Json
$i = 0
foreach ($p in $paths) {
  try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile]) 10000
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream]) 10000
    $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder]) 10000
    $w = $dec.PixelWidth; $h = $dec.PixelHeight
    if ($w -gt $max -or $h -gt $max) {
      $s = [Math]::Min($max / $w, $max / $h)
      $tr = New-Object Windows.Graphics.Imaging.BitmapTransform
      $tr.ScaledWidth = [uint32][Math]::Floor($w * $s); $tr.ScaledHeight = [uint32][Math]::Floor($h * $s)
      $bmp = Await ($dec.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied, $tr, [Windows.Graphics.Imaging.ExifOrientationMode]::IgnoreExifOrientation, [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap]) 10000
    } else {
      $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap]) 10000
    }
    $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult]) 10000
    Write-Output ((@{ i = $i; lang = $engine.RecognizerLanguage.LanguageTag; text = $res.Text }) | ConvertTo-Json -Compress)
    $stream.Dispose()
  } catch {
    Write-Output ((@{ i = $i; error = ('' + $_.Exception.Message).Substring(0, [Math]::Min(80, ('' + $_.Exception.Message).Length)) }) | ConvertTo-Json -Compress)
  }
  $i++
}
"""


def powershell_path() -> str | None:
    """테스트용 IAD_OCR_EXE(가짜 실행기) → Windows PowerShell 5.1(pwsh 는 WinRT 투영이 없어 불가) → None."""
    fake = os.environ.get("IAD_OCR_EXE", "").strip()
    if fake:
        return fake if Path(fake).is_file() else None
    if sys.platform != "win32":
        return None
    p = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(p) if p.is_file() else None


def encoded_command(script: str = PS_SCRIPT) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def build_command(exe: str, list_path: str) -> tuple[list[str], dict]:
    cmd = [exe]
    if exe.lower().endswith(".py"):
        cmd = [sys.executable, "-I", exe]
    cmd += ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_command()]
    env = {**os.environ, "IAD_OCR_LIST": list_path}
    return cmd, env


def run_batch(exe: str, image_paths: list[str], timeout: float) -> list[dict] | None:
    """여러 이미지를 한 번의 powershell 호출로 OCR. 반환: 이미지 번호 순서와 무관한 결과 dict 목록(없으면 None = 호출 실패/타임아웃)."""
    if not image_paths:
        return []
    fd, list_path = tempfile.mkstemp(prefix="iad-ocr-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump([str(Path(p).resolve()) for p in image_paths], fh, ensure_ascii=False)
        cmd, env = build_command(exe, list_path)
        kw: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL, "env": env}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(cmd, **kw)
        except OSError:
            return None
        try:
            out, _ = proc.communicate(timeout=max(1.0, timeout))
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.communicate(timeout=5)
            except Exception:
                pass
            return None
        rows: list[dict] = []
        for line in out.decode("utf-8", "replace").splitlines():
            line = line.strip().lstrip("\ufeff")
            if not line.startswith("{"):
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        if proc.returncode != 0 and not rows:
            return None
        return rows
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass


def _sniff(data: bytes) -> str | None:
    for magic, ext in _MAGIC.items():
        if data.startswith(magic):
            return ext
    return None


def _candidates(soup: BeautifulSoup, page_url: str) -> list[tuple[Tag, Tag, str]]:
    """(위치 요소 a 또는 img, img, 절대 src). 텍스트 없는 링크 안 이미지 / alt·title 에 배너·광고·이벤트 힌트가 있는 이미지."""
    out: list[tuple[Tag, Tag, str]] = []
    seen: set[int] = set()
    body = soup.body or soup
    for img in body.find_all("img"):
        src = str(img.get("src") or img.get("data-src") or "").strip()
        if not src or src == "data:," or src.startswith("data:") and "base64," not in src:
            continue
        a = img.find_parent("a")
        hint = (str(img.get("alt", "")) + " " + str(img.get("title", ""))).lower()
        banner_link = a is not None and not a.get_text(" ").strip()
        if not banner_link and not any(h in hint for h in ALT_HINTS):
            continue
        anchor = a if banner_link else img
        if id(anchor) in seen:
            continue
        seen.add(id(anchor))
        out.append((anchor, img, src if src.startswith("data:") else urljoin(page_url, src)))
    return out


def _load_image(src: str, session: requests.Session | None, allowed_hosts: tuple[str, ...] | None, timeout: float,
                cache: dict[str, bytes | None]) -> bytes | None:
    if src in cache:
        return cache[src]
    data: bytes | None = None
    if src.startswith("data:"):
        try:
            data = base64.b64decode(src.split("base64,", 1)[1], validate=False)
        except Exception:
            data = None
    elif session is not None and src.startswith(("http://", "https://")):
        if allowed_hosts is not None and host_of(src) not in allowed_hosts:
            data = None
        else:
            try:
                resp = session.get(src, timeout=timeout, stream=True)
                if resp.status_code == 200:
                    data = resp.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
                resp.close()
            except requests.RequestException:
                data = None
    if data is not None and (len(data) > MAX_IMAGE_BYTES or _sniff(data) is None):
        data = None
    cache[src] = data
    return data


def _passes_gate(text: str) -> tuple[dict[str, float], float, bool]:
    hits = match_keywords_levels(text)
    cats = {c: min(sum(w for _, w, _ in hs), 8.0) for c, hs in hits.items()}
    max_w = max((w for hs in hits.values() for _, w, _ in hs), default=0.0)
    ok = bool(cats) and (max_w >= MIN_KEYWORD or max(cats.values()) >= MIN_SUM)
    return cats, max_w, ok


def ocr_stage(pages: list[Page], findings: list[Finding], base_host: str, session: requests.Session | None,
              allowed_hosts: tuple[str, ...] | None, remaining: Callable[[], float], log: Callable[[str], None],
              fetch_timeout: float = 10.0) -> tuple[list[Finding], str]:
    """반환: (추가·보강된 ETC finding 목록, 한 줄 상태 메모). 이미 같은 location 에 finding 이 있으면 그 finding 에 근거를 붙인다."""
    from .analyzer import ADMIN_EXCLUDE, PageAnalyzer  # noqa: PLC0415
    from .keywords import admin_context_score  # noqa: PLC0415

    exe = powershell_path()
    if not exe:
        return [], "Windows OCR 없음(생략)"
    t0 = time.monotonic()
    budget = min(STAGE_BUDGET, remaining())
    if budget < 5:
        return [], "시간 예산 소진으로 생략"
    # 1) 후보 수집
    jobs: list[tuple[Page, PageAnalyzer, Tag, Tag, str]] = []
    for p in pages:
        if not p.html or p.error or p.external:
            continue
        an = PageAnalyzer(p, base_host)
        for anchor, img, src in _candidates(an.soup, p.url):
            jobs.append((p, an, anchor, img, src))
            if len(jobs) >= MAX_IMAGES:
                break
        if len(jobs) >= MAX_IMAGES:
            break
    if not jobs:
        return [], "배너 이미지 후보 없음"
    # 2) 이미지 받기(2MB·형식 확인) → 임시 파일
    tmpdir = tempfile.mkdtemp(prefix="iad-ocr-img-")
    cache: dict[str, bytes | None] = {}
    files: list[tuple[str, tuple[Page, PageAnalyzer, Tag, Tag, str]]] = []
    try:
        for job in jobs:
            if time.monotonic() - t0 > budget * 0.4:
                break
            data = _load_image(job[4], session, allowed_hosts, fetch_timeout, cache)
            if data is None:
                continue
            path = Path(tmpdir) / f"img{len(files):03d}{_sniff(data)}"
            path.write_bytes(data)
            files.append((str(path), job))
        if not files:
            return [], f"배너 후보 {len(jobs)}개 중 받을 수 있는 이미지 없음"
        left = min(budget - (time.monotonic() - t0), remaining())
        timeout = min(left, PER_IMAGE_SEC * len(files) + 15)
        log(f"OCR 단계: 배너 이미지 {len(files)}개를 Windows OCR 로 일괄 인식(상한 {int(timeout)}s)")
        rows = run_batch(exe, [f for f, _ in files], timeout)
    finally:
        for f, _ in files:
            try:
                os.unlink(f)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
    if rows is None:
        log("OCR 단계 실패(호출 오류·타임아웃) — 정적 결과로 계속")
        return [], f"호출 실패/타임아웃({len(files)}개)"
    if any(r.get("error") == "no_engine" for r in rows):
        log("OCR 엔진(ko/사용자 언어/en-US) 없음 — 생략")
        return [], "OCR 언어 엔진 없음"
    by_i = {int(r["i"]): r for r in rows if "i" in r}
    # 3) 판정
    by_loc = {(f.page_url, f.location): f for f in findings}
    out: list[Finding] = []
    n_text = n_hit = 0
    for idx, (_, (p, an, anchor, img, src)) in enumerate(files):
        r = by_i.get(idx)
        if not r or r.get("error") or not str(r.get("text", "")).strip():
            continue
        text = re.sub(r"\s+", " ", str(r["text"])).strip()
        lang = str(r.get("lang", "?"))
        n_text += 1
        cats, max_w, ok = _passes_gate(text)
        if not ok or admin_context_score(text) <= ADMIN_EXCLUDE:   # 도박 예방 캠페인·신고 안내 배너 제외
            continue
        f = an._new(anchor)   # noqa: SLF001
        f.evidence_text = text[:300]
        an._add_keywords(f, text)   # noqa: SLF001
        if anchor.name == "a":
            an._add_links(f, anchor, "")   # noqa: SLF001
        f.add("ocr.image_text", f"이미지 글자(OCR {lang}): '{text[:80]}'", 2.5, "keyword")
        f.techniques.append("image_text")
        f.extra_names.append("IMAGE_TEXT_AD")
        f.links = list(dict.fromkeys(f.links))
        if an._is_admin_notice(f, text):   # noqa: SLF001
            continue
        before = len(an.findings)
        an._finalize(f, cats)   # noqa: SLF001
        if len(an.findings) == before:
            continue
        f.official = []
        n_hit += 1
        g = by_loc.get((f.page_url, f.location))
        if g is not None:   # 같은 위치의 기존 ETC(IMAGE_BANNER_AD 등)에 근거를 합친다
            have = {(e.rule, e.detail) for e in g.evidence}
            g.evidence.extend(e for e in f.evidence if (e.rule, e.detail) not in have)
            g.extra_names = list(dict.fromkeys(g.extra_names + ["IMAGE_TEXT_AD"]))
            g.techniques = list(dict.fromkeys(g.techniques + ["image_text"]))
            g.score = round(sum(e.weight for e in g.evidence), 2)
            if not g.official:
                g.evidence_text = g.evidence_text or f.evidence_text
            continue
        by_loc[(f.page_url, f.location)] = f
        out.append(f)
    note = f"이미지 {len(files)}개 인식, 글자 있음 {n_text}, 광고 판정 {n_hit}(신규 {len(out)}), {time.monotonic() - t0:.1f}s"
    log(f"OCR 단계 완료: {note}")
    return out, note
