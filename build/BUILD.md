# 빌드 재현 방법 (Windows 실행 파일)

이 문서는 「공공 웹사이트 불법광고 탐지 도구」의 Windows 실행 파일을 다시 만드는 방법을 적는다.
빌드는 GitHub Actions 의 Windows 러너에서 자동으로 돌고, 같은 명령을 Windows PC 에서 손으로 실행해도 같은 결과가 나온다.

## 1. 산출물 구성

PyInstaller onedir(단일 폴더) 방식으로 만든다. 폴더 하나에 GUI 와 CLI 실행 파일이 같이 들어 있고 런타임(`_internal/`)을 함께 쓴다.

```
IllegalAdDetector/
  IllegalAdDetector.exe   GUI (tkinter, 콘솔 창 없음)
  iad-cli.exe             CLI (콘솔)
  _internal/              Python 3.12 런타임, 라이브러리, Playwright 드라이버
```

배포 파일은 이 폴더를 압축한 `IllegalAdDetector-windows.zip` 이다(약 67 MB, 풀면 약 158 MB). 압축을 풀고 `IllegalAdDetector.exe` 를 더블클릭하면 실행된다. 설치 과정과 Python 은 필요 없다. 용량의 대부분(약 94 MB)은 Edge 렌더 비교용 Playwright 드라이버(`_internal/playwright/driver/node.exe`)다.

탐지가 끝나면 적격평가용 결과 파일 `result.json` 과 추가 탐지 결과 `result_extra.json` 이 **구동 파일(exe)이 있는 폴더**에 UTF-8(BOM 없음)으로 생성된다. onedir 방식이라 exe 위치가 곧 실제 폴더이므로 위치가 헷갈리지 않는다. 따라서 압축은 쓰기 권한이 있는 폴더(바탕화면, 문서 등)에 풀어야 한다. `C:\Program Files` 아래처럼 쓰기 권한이 없는 곳은 피한다.

CLI 사용 예:

```
iad-cli.exe --url https://www.example.go.kr/ --depth 3 --max-pages 300
iad-cli.exe --help
```

onefile 대신 onedir 을 고른 이유는 다음과 같다.

1. 요강은 result.json 을 구동 파일과 같은 폴더에 만들도록 정한다. onefile 은 실행 중 코드가 임시 폴더에서 돌기 때문에 기준 폴더가 헷갈리기 쉽다. onedir 은 exe 폴더가 그대로 기준 폴더다.
2. onefile 은 실행할 때마다 임시 폴더(`%TEMP%\_MEIxxxx`)에 압축을 풀기 때문에 시작이 느리고, 사용자 이름이 한글인 계정이나 보안 프로그램이 임시 폴더를 막는 환경에서 실패할 여지가 있다.
3. onedir 은 압축 해제 단계가 없어 시작이 빠르고, 백신 오탐도 상대적으로 적다.
4. GUI 와 CLI 가 런타임을 공유하므로 두 exe 를 따로 onefile 로 만드는 것보다 용량이 작다.

## 2. 필요 환경

| 항목 | 버전 |
|---|---|
| OS | Windows 10/11 x64 (CI: `windows-latest`) |
| Python | 3.12 (64bit) |
| PyInstaller | 6.22.3 (`build/requirements-build.txt` 에 고정) |
| pyinstaller-hooks-contrib | 2026.9 |
| Playwright (Python) | 1.64.1, 브라우저는 내려받지 않음 |
| 실행 PC 의 브라우저 | Microsoft Edge (Windows 기본 설치). 렌더링 모드에서만 사용 |

런타임 라이브러리는 `src/requirements.txt` (requests, beautifulsoup4, lxml) 를 따른다.

## 3. 자동 빌드 (GitHub Actions)

워크플로 파일: `.github/workflows/build-windows.yml`

* 트리거: `main` 브랜치 push, 또는 Actions 탭에서 `Run workflow` (workflow_dispatch)
* 순서: 의존성 설치 → (테스트가 있으면) pytest → PyInstaller 빌드 → 스모크 테스트 → zip → artifact 업로드
* 결과물: 실행(run) 페이지 하단 Artifacts 의 `IllegalAdDetector-windows` (zip), `smoke-output` (스모크 테스트가 만든 리포트)

명령줄에서 내려받기:

```
gh run list --workflow build-windows.yml -L 5
gh run download <run-id> -n IllegalAdDetector-windows -D build/dist_windows/
```

## 4. 손으로 빌드 (Windows PowerShell)

저장소 루트에서 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r src/requirements.txt
python -m pip install -r build/requirements-build.txt
pyinstaller build/iad.spec --noconfirm --clean --distpath build/dist --workpath build/work
Compress-Archive -Path build/dist/IllegalAdDetector -DestinationPath build/IllegalAdDetector-windows.zip -Force
```

`playwright install` 은 실행하지 않는다. 렌더링 모드는 PC 에 이미 있는 Edge 를 `channel="msedge"` 로 띄우므로 브라우저를 따로 받을 필요가 없다. Edge 를 찾지 못하면 프로그램이 정적(HTML 직접 수집) 모드로 자동 전환한다.

## 5. 빌드 설정 파일

| 파일 | 역할 |
|---|---|
| `build/iad.spec` | PyInstaller 설정. GUI(`src/run_gui.py`)·CLI 두 진입점을 한 폴더로 묶는다. `iad` 패키지 서브모듈과 데이터 파일, certifi 인증서, Playwright 드라이버(node + package)를 포함한다 |
| `build/entry_cli.py` | CLI exe 진입점. `python -m iad` 와 같은 동작 |
| `build/hooks/rth_iad.py` | 런타임 훅. 표준 출력을 UTF-8 로 바꿔 한글 출력이 깨지거나 오류 나는 것을 막는다. 스모크 테스트 때만 GUI 창을 몇 초 뒤 자동으로 닫는다 |
| `build/requirements-build.txt` | 빌드 도구 버전 고정 |
| `build/smoke_cli.ps1` | CLI 스모크 테스트 |
| `build/smoke_gui.ps1` | GUI 스모크 테스트 |
| `build/selftest/` | GUI 스모크 판정이 실제 크래시를 잡는지 확인하는 자체검증용 스크립트 (워크플로 수동 실행 시 `selftest` 체크) |

## 6. 스모크 테스트

빌드 직후 같은 러너에서 실행 파일을 **한글과 공백이 들어간 경로**(`%RUNNER_TEMP%\한글 경로\불법광고 탐지기\`)에 복사한 뒤 돌린다.

1. CLI: `src/fixtures` 를 `python -m http.server` 로 로컬 웹서버에 올리고(`src/fixtures/index.html`, 없으면 `src/fixtures/dev/`, 그것도 없으면 `build/smoke_site/` 사용), `iad-cli.exe --url http://127.0.0.1:8765/` 로 크롤링한다. 검사 항목은 다음과 같다.
   * 종료 코드 0, `--help` 의 한글 출력이 파이프에서 오류 없이 나옴
   * `result.json` 이 exe 와 같은 폴더(한글 경로)에 생성됨
   * `result.json`·`result_extra.json` 첫 3바이트가 UTF-8 BOM(EF BB BF)이 아님, JSON 파싱 가능
   * `meta`(topic, entry_url, started_at, finished_at, elapsed_sec) 와 `findings` 키 존재, 검출 1건 이상
   * `report.html` 이 한글 경로의 출력 폴더에 생성됨
2. GUI: `IllegalAdDetector.exe` 를 실행해 tkinter 메인 루프까지 정상 진입하는지 확인한다. 런타임 훅이 진입 시 마커 파일을 쓰고 5초 뒤 창을 닫는다. 창이 뜨기 전에 죽거나 오류 대화상자에서 멈추면 마커가 생기지 않아 실패로 판정한다.

손으로 돌릴 때:

```powershell
./build/smoke_cli.ps1 -AppDir build/dist/IllegalAdDetector -FixturesDir src/fixtures -OutDir $env:TEMP\iad_smoke
./build/smoke_gui.ps1 -Exe build/dist/IllegalAdDetector/IllegalAdDetector.exe
```

워크플로를 수동 실행할 때 `selftest` 를 체크하면 GUI 판정 로직 자체를 검증한다. 일부러 시작 중에 예외를 던지는 exe 는 Windows 에서 "Unhandled exception in script" 대화상자를 띄운 채 프로세스가 살아 있으므로, 단순히 "몇 초 뒤 프로세스 생존"만 보면 통과로 잘못 판정된다. 마커 방식은 이 경우를 실패로 잡는다(2026-10-23 실행에서 확인).

## 7. 최근 빌드 결과

| 항목 | 값 |
|---|---|
| 실행 | GitHub Actions run 39891832150 (커밋 678cab4, 2026-10-23) |
| 산출물 | `IllegalAdDetector-windows.zip` 66,524,646 bytes, 1,226 files (풀면 약 158 MB) |
| 단위 테스트 | 30 passed |
| CLI 스모크 | PASS. `src/fixtures/dev` 25페이지를 5.2초에 탐지, result.json 25건(HOMOGLYPH, JAMO, OFFSCREEN, TRANSPARENT), result_extra.json 16건, 둘 다 BOM 없음 |
| GUI 스모크 | PASS. mainloop 진입 후 5초 뒤 자동 종료, exit 0 |

평가 PC 조건(요강 붙임3): Windows 11, GPU 없는 일반 PC, 검출 시간 상한 30분. CLI 기본 시간 예산은 `--time-budget 1200`(20분)이다.
