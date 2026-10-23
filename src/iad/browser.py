"""브라우저 단계(선택, 기본 켬): OS 에 이미 있는 Edge/Chrome 을 `--headless=new --dump-dom` 으로 띄워 JS 실행 후 DOM 을 한 번 더 분석한다.

- 대상: 인라인 스크립트에 document.write / innerHTML / insertAdjacentHTML / appendChild / eval / atob / fromCharCode 등 DOM 주입 흔적이 있는
  최상위 페이지만(정적 분석으로는 주입 결과를 볼 수 없는 경우).
- 결과: 정적 DOM 에 없던(선택자가 안 풀리거나 내용이 달라진) finding 만 **ETC(DYNAMIC_INJECTION)** 로 추가한다. 채점자의 location 은 수집한 HTML
  기준으로 풀릴 가능성이 높으므로 렌더 후에만 존재하는 요소를 4종(result.json)에 넣지 않는다(정확도 보호).
- 안전장치: 브라우저가 없거나(None), 정책(HKLM/HKCU Policies\\Microsoft\\Edge HeadlessModeEnabled=0)으로 막혔거나, 호출이 실패·타임아웃이면
  정적 결과만 남긴다. 페이지당 10초, 단계 전체 90초 상한, 남은 전체 시간 예산 안에서만 돈다. 호출마다 임시 프로필을 쓰고 끝나면 지운다.
- 추가 의존성 없음(subprocess 만). Windows 실측은 하지 않았으므로 "실패하면 정적 결과만" 구조를 유지한다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from bs4 import BeautifulSoup

from .models import Finding, Page

PER_PAGE_TIMEOUT = 10.0
STAGE_BUDGET = 90.0
MAX_PAGES = 30
VIRTUAL_TIME_MS = 5000
MAX_DOM_BYTES = 3_000_000

SUSPICIOUS_JS = re.compile(
    r"document\s*\.\s*write(?:ln)?\s*\(|\.innerHTML\s*[=+]|insertAdjacentHTML|appendChild\s*\(|\.outerHTML\s*=|"
    r"\beval\s*\(|\batob\s*\(|fromCharCode|\bunescape\s*\(|createElement\s*\(\s*['\"](?:a|div|iframe|span)['\"]", re.I)
_INLINE_SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.I | re.S)

BROWSER_FLAGS = ("--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                 "--disable-sync", "--disable-background-mode", "--disable-component-update", "--disable-background-networking",
                 "--mute-audio", "--hide-scrollbars", "--window-size=1280,900")


def policy_blocked() -> str | None:
    """Windows 정책으로 headless 가 막혀 있으면 그 이유, 아니면 None. (Windows 외에서는 항상 None)"""
    if sys.platform != "win32":
        return None
    try:
        import winreg  # noqa: PLC0415
    except ImportError:
        return None
    for root, root_name in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")):
        for key in (r"SOFTWARE\Policies\Microsoft\Edge", r"SOFTWARE\Policies\Google\Chrome"):
            try:
                with winreg.OpenKey(root, key) as k:
                    try:
                        v, _ = winreg.QueryValueEx(k, "HeadlessModeEnabled")
                    except OSError:
                        continue
                    if v == 0:
                        return f"{root_name}\\{key}\\HeadlessModeEnabled=0"
            except OSError:
                continue
    return None


def find_browser() -> str | None:
    """IAD_BROWSER 환경변수 → (Windows) 레지스트리 App Paths msedge/chrome → 표준 설치 경로 → PATH 순으로 실행 파일을 찾는다."""
    env = os.environ.get("IAD_BROWSER", "").strip()
    if env:
        if Path(env).is_file():
            return env
        return shutil.which(env)
    cands: list[str] = []
    if sys.platform == "win32":
        try:
            import winreg  # noqa: PLC0415
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for exe in ("msedge.exe", "chrome.exe"):
                    for flag in (0, getattr(winreg, "KEY_WOW64_32KEY", 0), getattr(winreg, "KEY_WOW64_64KEY", 0)):
                        try:
                            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}", 0,
                                                winreg.KEY_READ | flag) as k:
                                v, _ = winreg.QueryValueEx(k, None)
                                cands.append(str(v).strip('"'))
                        except OSError:
                            continue
        except ImportError:
            pass
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands.append(str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
                cands.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    elif sys.platform == "darwin":
        cands += ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for name in ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "chrome"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


def _kill(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            proc.kill()
    except Exception:
        pass
    try:
        proc.communicate(timeout=5)
    except Exception:
        pass


def dump_dom(browser: str, url: str, timeout: float = PER_PAGE_TIMEOUT, virtual_time_ms: int = VIRTUAL_TIME_MS) -> str | None:
    """JS 실행 후 DOM(outerHTML) 문자열. 실패·타임아웃·빈 출력이면 None. stdout 은 바이트로 받아 UTF-8 로 푼다(cp949 콘솔 깨짐 방지)."""
    tmp = tempfile.mkdtemp(prefix="iad-prof-")
    try:
        cmd = [browser]
        if browser.lower().endswith(".py"):          # 테스트용 가짜 브라우저 스크립트
            cmd = [sys.executable, "-I", browser]
        cmd += [*BROWSER_FLAGS, f"--user-data-dir={tmp}", f"--virtual-time-budget={int(virtual_time_ms)}", "--dump-dom", url]
        kw: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(cmd, **kw)
        except OSError:
            return None
        try:
            out, _ = proc.communicate(timeout=max(1.0, timeout))
        except subprocess.TimeoutExpired:
            _kill(proc)
            return None
        if proc.returncode != 0 or not out:
            return None
        html = out[:MAX_DOM_BYTES].decode("utf-8", "replace")
        return html if "<" in html else None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def is_suspicious_page(html: str) -> bool:
    """인라인 스크립트에 DOM 주입·디코딩 흔적이 있는 페이지만 브라우저로 다시 본다."""
    return any(SUSPICIOUS_JS.search(m.group(1)) for m in _INLINE_SCRIPT.finditer(html or ""))


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def _static_has(static_soup: BeautifulSoup, static_norm: str, location: str, evidence_text: str, links: list[str]) -> bool:
    """정적 DOM 에 같은 내용이 이미 있으면 True(정적 분석이 이미 판단한 요소이므로 다시 올리지 않는다).

    1) location 이 정적 DOM 에서 풀리면 그 요소의 텍스트/HTML 에 evidence_text 가 있는지 본다.
    2) 안 풀리면(Chrome 이 <tbody> 삽입·잘못된 중첩 수선으로 경로가 달라진 경우) 정적 HTML 전체에 evidence_text 와 링크 href 가 모두 있는지로 판단한다.
       내용이 정말 없을 때만 '동적 주입'이다."""
    want = _norm(evidence_text)[:80]
    try:
        el = static_soup.select_one(location) if location else None
    except Exception:
        el = None
    if el is not None:
        have = _norm(el.get_text(" ") + " " + str(el)[:2000])
        if not want or want in have:
            return True
    text_present = bool(want) and want in static_norm
    links_present = bool(links) and all(_norm(u) in static_norm for u in links)
    if want and links:
        return text_present and links_present
    return text_present or links_present


def browser_stage(pages: list[Page], findings: list[Finding], base_host: str, remaining: Callable[[], float],
                  log: Callable[[str], None]) -> tuple[list[Finding], str]:
    """렌더 후에만 나타난 요소를 ETC 로 추가. 반환: (추가 finding, 한 줄 상태 메모)."""
    from .analyzer import analyze_page  # noqa: PLC0415

    blocked = policy_blocked()
    if blocked:
        log(f"브라우저 단계 생략: 정책으로 headless 비활성({blocked}) — 정적 결과만")
        return [], f"정책 비활성({blocked})"
    exe = find_browser()
    if not exe:
        log("브라우저 단계 생략: Edge/Chrome 실행 파일 없음 — 정적 결과만")
        return [], "브라우저 없음"
    cands = [p for p in pages if p.html and not p.error and not p.is_iframe and not p.external and is_suspicious_page(p.html)]
    cands.sort(key=lambda p: p.depth)
    cands = cands[:MAX_PAGES]
    if not cands:
        return [], "의심 스크립트 페이지 없음"
    known = {(f.page_url, f.location) for f in findings}
    t0 = time.monotonic()
    budget = min(STAGE_BUDGET, remaining())
    out: list[Finding] = []
    n_ok = n_fail = 0
    log(f"브라우저 단계: {Path(exe).name} 로 의심 스크립트 페이지 {len(cands)}쪽 JS 실행 비교(상한 {int(budget)}s)")
    for p in cands:
        left = min(budget - (time.monotonic() - t0), remaining())
        if left < 3:
            log("  브라우저 단계: 시간 상한 도달, 나머지는 정적 결과만")
            break
        html = dump_dom(exe, p.url, timeout=min(PER_PAGE_TIMEOUT, left))
        if html is None:
            n_fail += 1
            continue
        n_ok += 1
        rp = Page(url=p.url, html=html, depth=p.depth, top_url=p.top_url, frame_prefix=p.frame_prefix, css_texts=list(p.css_texts))
        try:
            rendered = analyze_page(rp, base_host)
        except Exception as e:
            log(f"  렌더 DOM 분석 오류 {p.url}: {e!r}")
            continue
        if not rendered:
            continue
        static_soup = BeautifulSoup(p.html, "lxml")
        static_norm = _norm(p.html + " " + static_soup.get_text(" "))   # HTML 원문 + 태그를 뺀 텍스트(태그 사이로 끊긴 문장도 비교)
        added = 0
        for f in rendered:
            if (f.page_url, f.location) in known or _static_has(static_soup, static_norm, f.location, f.evidence_text, f.links):
                continue
            # 숨긴 메뉴의 외부 링크(hidden_external)만으로는 주입 근거가 약하다(JS 로 만든 내비게이션). 키워드(≥2.0) 또는 다른 링크 규칙이 있어야 한다.
            strong = any(e.group == "keyword" and e.weight >= 2.0 for e in f.evidence) or \
                any(e.group == "link" and e.rule != "link.hidden_external" for e in f.evidence) or \
                any(e.group == "script" for e in f.evidence)
            if not strong:
                continue
            names = [*f.official, *f.extra_names]
            f.official = []
            f.add("render.dynamic_injection", "정적 HTML 에 없고 JS 실행 후에만 존재하는 요소(동적 주입)" +
                  (f" — 렌더 DOM 판정: {', '.join(names)}" if names else ""), 3.0, "script")
            f.techniques = list(dict.fromkeys(f.techniques + ["dynamic_injection"]))
            f.extra_names = list(dict.fromkeys(["DYNAMIC_INJECTION", *(n for n in f.extra_names if n not in ("SUSPICIOUS",))]))
            f.score = round(sum(e.weight for e in f.evidence), 2)
            f.risk = "높음" if f.score >= 8 else "중간" if f.score >= 5 else "낮음"
            known.add((f.page_url, f.location))
            out.append(f)
            added += 1
        if added:
            log(f"  동적 주입 {added}건: {p.url}")
    note = f"{Path(exe).name}: {n_ok}쪽 렌더, {n_fail}쪽 실패, 추가 {len(out)}건, {time.monotonic() - t0:.1f}s"
    log(f"브라우저 단계 완료: {note}")
    return out, note
