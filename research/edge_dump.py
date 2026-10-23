"""Edge/Chrome 헤드리스로 JS 실행 후 DOM을 얻는 시제품 (추가 번들 0, 표준 라이브러리만).

공개 함수
    find_browser() -> str | None
    dump_dom(url, timeout_s=15.0, budget_ms=3000) -> str | None   # 실패 시 None

Windows 11 에서는 기본 탑재 Microsoft Edge(Chromium)를 찾고, 없으면 Chrome 을 찾는다.
맥/리눅스에서는 개발 검증용으로 Chrome/Edge/Chromium 을 찾는다.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# 헤드리스 공통 플래그. 첫 실행 마법사·동기화·백그라운드 상주·확장·네트워크 잡음을 끈다.
COMMON_FLAGS = [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-background-mode",       # Edge "백그라운드 확장 계속 실행" 상주 방지
    "--disable-features=msEdgeStartupBoost,msImplicitSignin,msEdgeSidebarV2,Translate,MediaRouter",
    "--mute-audio",
    "--hide-scrollbars",
    "--window-size=1366,900",
    "--log-level=3",
]

_WIN_REL = [
    r"Microsoft\Edge\Application\msedge.exe",
    r"Google\Chrome\Application\chrome.exe",
]
_WIN_APP_PATHS = ["msedge.exe", "chrome.exe"]
_MAC = [
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
_UNIX_NAMES = ["microsoft-edge", "microsoft-edge-stable", "google-chrome", "chromium", "chromium-browser"]


def _win_registry_lookup(exe: str) -> str | None:
    try:
        import winreg  # type: ignore
    except ImportError:
        return None
    key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (0, getattr(winreg, "KEY_WOW64_32KEY", 0), getattr(winreg, "KEY_WOW64_64KEY", 0)):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as k:
                    val, _ = winreg.QueryValueEx(k, None)
                    val = str(val).strip('"')
                    if val and os.path.isfile(val):
                        return val
            except OSError:
                continue
    return None


def find_browser() -> str | None:
    env = os.environ.get("IAD_BROWSER")
    if env and os.path.isfile(env):
        return env
    if sys.platform == "win32":
        for exe in _WIN_APP_PATHS:
            p = _win_registry_lookup(exe)
            if p:
                return p
        roots = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        for rel in _WIN_REL:
            for root in roots:
                if root:
                    p = os.path.join(root, rel)
                    if os.path.isfile(p):
                        return p
        return shutil.which("msedge") or shutil.which("chrome")
    if sys.platform == "darwin":
        for p in _MAC:
            if os.path.isfile(p):
                return p
    for n in _UNIX_NAMES:
        p = shutil.which(n)
        if p:
            return p
    return None


def _to_url(target: str) -> str:
    if "://" in target or target.startswith(("about:", "data:")):
        return target
    return Path(target).resolve().as_uri()  # 로컬 경로 → file:///C:/... (한글 경로는 퍼센트 인코딩)


def _popen_kwargs() -> dict:
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def kill_tree(proc: subprocess.Popen) -> None:
    """헤드리스 브라우저는 renderer/gpu/utility 자식 프로세스를 만든다. 트리째 정리."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def dump_dom(url: str, timeout_s: float = 15.0, budget_ms: int = 3000,
             browser: str | None = None) -> str | None:
    """JS 실행 후 직렬화된 DOM(outerHTML)을 돌려준다. 브라우저 없음·타임아웃·오류면 None.

    budget_ms: --virtual-time-budget. 가상 시간을 빨리 감아 setTimeout 주입까지 기다린다
    (실제 벽시계 대기 아님). 무한 setInterval 페이지도 예산 소진 시 덤프된다.
    """
    exe = browser or find_browser()
    if not exe:
        return None
    profile = tempfile.mkdtemp(prefix="iad_edge_")
    args = [exe, *COMMON_FLAGS, f"--user-data-dir={profile}",
            f"--virtual-time-budget={int(budget_ms)}", "--dump-dom", _to_url(url)]
    proc = None
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, **_popen_kwargs())
        try:
            out, _ = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            return None
        if proc.returncode not in (0, None) and not out:
            return None
        # --dump-dom 은 콘솔 코드페이지와 무관하게 UTF-8 바이트를 stdout 파이프에 쓴다.
        text = out.decode("utf-8", errors="replace").strip()
        return text or None
    except OSError:
        return None
    finally:
        if proc is not None:
            kill_tree(proc)
        shutil.rmtree(profile, ignore_errors=True)


def screenshot(url: str, out_png: str, timeout_s: float = 15.0, budget_ms: int = 3000) -> bool:
    """OCR 등 후속 처리용 전체 화면 캡처. 성공 여부만 돌려준다."""
    exe = find_browser()
    if not exe:
        return False
    profile = tempfile.mkdtemp(prefix="iad_edge_")
    args = [exe, *COMMON_FLAGS, f"--user-data-dir={profile}", f"--virtual-time-budget={int(budget_ms)}",
            f"--screenshot={os.path.abspath(out_png)}", _to_url(url)]
    proc = None
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, **_popen_kwargs())
        proc.wait(timeout=timeout_s)
        return os.path.isfile(out_png) and os.path.getsize(out_png) > 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        if proc is not None:
            kill_tree(proc)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    import time
    t = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fixtures", "js_inject.html")
    print("browser:", find_browser())
    t0 = time.time()
    dom = dump_dom(t, timeout_s=float(os.environ.get("IAD_TIMEOUT", "15")))
    print(f"elapsed {time.time() - t0:.2f}s, len={None if dom is None else len(dom)}")
    if dom:
        print(dom[:1500])
