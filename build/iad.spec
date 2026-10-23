# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: GUI exe + CLI exe 를 한 폴더(onedir)에 함께 만든다.
#   pyinstaller build/iad.spec --noconfirm --clean --distpath build/dist --workpath build/work
# 결과: build/dist/IllegalAdDetector/{IllegalAdDetector.exe, iad-cli.exe, _internal/}
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

BUILD_DIR = Path(SPECPATH).resolve()
ROOT = BUILD_DIR.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

APP_NAME = "IllegalAdDetector"
GUI_NAME = "IllegalAdDetector"
CLI_NAME = "iad-cli"

gui_entry = SRC / "run_gui.py"
cli_entry = SRC / "run_cli.py"
if not cli_entry.exists():
    cli_entry = BUILD_DIR / "entry_cli.py"

datas = []
binaries = []
hiddenimports = []

# iad 패키지: 서브모듈 전부 + 패키지 안의 비(非)파이썬 파일(템플릿·규칙 등)을
# 같은 상대 경로(iad/...)로 넣어 Path(__file__).parent 기반 접근이 그대로 동작하게 한다.
hiddenimports += collect_submodules("iad")
datas += collect_data_files("iad", include_py_files=False)

# src/ 최상위의 데이터 폴더(있을 때만). fixtures 는 테스트용이라 넣지 않는다.
for name in ("rules", "templates", "assets", "data", "config"):
    p = SRC / name
    if p.is_dir():
        datas.append((str(p), name))

# 파서·HTTP 스택
for mod in ("bs4", "lxml", "requests", "certifi", "charset_normalizer", "idna", "urllib3"):
    try:
        hiddenimports += collect_submodules(mod)
    except Exception:
        pass
datas += collect_data_files("certifi")

# Playwright(선택): 브라우저는 받지 않고 드라이버(node + package)만 포함한다.
# 런타임에 channel="msedge" 로 시스템 Edge 를 쓴다.
# IAD_STATIC_ONLY=1 이면 playwright 가 설치돼 있어도 넣지 않는다(제출본).
STATIC_ONLY = os.environ.get("IAD_STATIC_ONLY") == "1"
try:
    if STATIC_ONLY:
        raise ImportError("IAD_STATIC_ONLY=1")
    import playwright  # noqa: F401

    pw_datas, pw_binaries, pw_hidden = collect_all("playwright")
    datas += pw_datas
    binaries += pw_binaries
    hiddenimports += pw_hidden
except ImportError:
    print("[iad.spec] playwright 미설치: 정적 모드 전용으로 빌드")

hiddenimports += ["tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "tkinter.scrolledtext"]

runtime_hooks = [str(BUILD_DIR / "hooks" / "rth_iad.py")]
excludes = ["matplotlib", "numpy.tests", "pytest", "IPython"]
if STATIC_ONLY:
    excludes += ["playwright", "greenlet", "pyee"]

icon_path = BUILD_DIR / "icon.ico"
icon = str(icon_path) if icon_path.exists() else None


def make_analysis(entry):
    return Analysis(
        [str(entry)],
        pathex=[str(SRC)],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        runtime_hooks=runtime_hooks,
        excludes=excludes,
        noarchive=False,
    )


a_gui = make_analysis(gui_entry)
a_cli = make_analysis(cli_entry)

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name=GUI_NAME,
    console=False,
    upx=False,
    icon=icon,
)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name=CLI_NAME,
    console=True,
    upx=False,
    icon=icon,
)

coll = COLLECT(
    exe_gui,
    a_gui.binaries,
    a_gui.datas,
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
