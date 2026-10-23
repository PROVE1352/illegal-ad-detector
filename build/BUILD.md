# 빌드 재현 방법 (Windows 실행 파일)

이 문서는 「공공 웹사이트 불법광고 탐지 도구」의 Windows 실행 파일을 다시 만드는 방법을 적는다.
빌드는 GitHub Actions 의 Windows 러너에서 자동으로 돌고, 같은 명령을 Windows PC 에서 손으로 실행해도 같은 결과가 나온다.

## 1. 산출물 구성

PyInstaller onedir(단일 폴더) 방식으로 만든다. 폴더 하나에 GUI 와 CLI 실행 파일이 같이 들어 있고 런타임(`_internal/`)을 함께 쓴다.

```
IllegalAdDetector/
  IllegalAdDetector.exe   GUI (tkinter, 콘솔 창 없음)
  iad-cli.exe             CLI (콘솔)
  _internal/              Python 3.12 런타임, 라이브러리
```

빌드는 두 가지를 함께 만든다.

| 구분 | 파일 | 크기 | 내용 |
|---|---|---|---|
| 제출본 | `IllegalAdDetector-windows.zip` | 약 25 MB (풀면 약 46 MB, 1,024 files) | 정적 모드 전용. Playwright 미포함 |
| 참고본 | `IllegalAdDetector-windows-render.zip` | 약 67 MB (풀면 약 158 MB) | Edge 렌더 비교용 Playwright 드라이버(`_internal/playwright/driver/node.exe`, 약 94 MB) 포함 |

제출하는 것은 정적 전용 제출본이다. 탐지는 HTML·CSS 를 직접 받아 분석하는 정적 모드로 이루어지고, 렌더 비교는 동적 주입 링크를 추가로 찾는 선택 기능이라 용량 대비 이득이 작다. 제출본에서 `--render` 를 주면 "렌더 비교를 사용할 수 없어 정적 분석 결과로 계속합니다." 로그를 남기고 정적 분석 결과로 정상 종료한다. GUI 에서는 "Edge 렌더 비교" 체크가 비활성화되고 "(이 배포본은 정적 분석 전용 — 렌더 비교 미포함)" 안내가 붙는다.

렌더 비교와 별개로, 두 빌드 모두 **브라우저 단계**(src 7c9480a~)가 기본으로 켜져 있다. PC 에 설치된 Edge/Chrome 을 `--headless --dump-dom` 으로 직접 실행해 의심 스크립트 페이지만 JS 실행 후 다시 분석한다(Playwright 불필요, 결과는 ETC DYNAMIC_INJECTION 으로 result_extra.json 에만). 정책·미설치·실패·타임아웃이면 정적 결과만 쓰고, 페이지당 15초·단계 전체 5분 상한, `--no-browser` 로 끌 수 있다. 1쪽에 약 1~5초(환경에 따라) 걸린다.

OCR 단계(Windows 전용)도 두 빌드 모두 기본으로 켜져 있다. 배너로 보이는 이미지를 Windows 10/11 내장 OCR(Windows.Media.Ocr)로 읽어, 광고 문구가 나오면 ETC IMAGE_TEXT_AD 로 result_extra.json 에만 보고한다. OCR 엔진이나 언어 데이터를 번들하지 않아 추가 용량은 0이고, 인식 언어는 ko → 사용자 프로필 언어 → en-US 순으로 고른다. 이미지 최대 40개(이미지당 2MB·10초), 단계 전체 120초 상한이다. 예방 캠페인 배너처럼 행정 문맥이 있으면 보고하지 않는다. OCR 을 쓸 수 없거나 실패하면 한 줄 로그를 남기고 정적 결과로 계속하며, `--no-ocr` 또는 GUI 의 "OCR(이미지 글자)" 체크 해제로 끌 수 있다.

압축을 풀고 `IllegalAdDetector.exe` 를 더블클릭하면 실행된다. 설치 과정과 Python 은 필요 없다.

탐지가 끝나면 적격평가용 결과 파일 `result.json` 과 추가 탐지 결과 `result_extra.json` 이 **구동 파일(exe)이 있는 폴더**에 UTF-8(BOM 없음)으로 생성된다. onedir 방식이라 exe 위치가 곧 실제 폴더이므로 위치가 헷갈리지 않는다. 따라서 압축은 쓰기 권한이 있는 폴더(바탕화면, 문서 등)에 풀어야 한다. `C:\Program Files` 아래처럼 쓰기 권한이 없는 곳은 피한다.

CLI 사용 예:

```
iad-cli.exe --url https://www.example.go.kr/ --depth 3 --max-pages 300
iad-cli.exe --demo            내장 테스트 사이트를 스캔하고 리포트를 연다(네트워크 불필요, 결과는 exe 폴더\demo)
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
| Playwright (Python) | 1.64.1, 참고본만 (`build/requirements-build-render.txt`), 브라우저는 내려받지 않음 |
| 실행 PC 의 브라우저 | 필수 아님. Windows 11 기본 Edge 가 있으면 브라우저 단계(JS 실행 후 재분석)에 쓰고, 없으면 정적 분석만 한다. 참고본의 렌더링 모드도 Edge 사용 |
| 실행 PC 의 OCR | 필수 아님. Windows 10/11 내장 OCR 사용(번들 없음), 없으면 OCR 단계 생략 |

런타임 라이브러리는 `src/requirements.txt` (requests, beautifulsoup4, lxml) 를 따른다.

## 3. 자동 빌드 (GitHub Actions)

워크플로 파일: `.github/workflows/build-windows.yml`

* 트리거: `main` 브랜치 push, 또는 Actions 탭에서 `Run workflow` (workflow_dispatch)
* matrix 로 두 job 이 병렬로 돈다: `build (static)` = 제출본(`IAD_STATIC_ONLY=1`, playwright 미설치), `build (render)` = 참고본
* 순서: 의존성 설치 → (테스트가 있으면) pytest → PyInstaller 빌드(정적 전용인데 playwright 가 들어가면 실패) → 스모크 테스트 → zip → artifact 업로드
* 결과물: Artifacts 의 `IllegalAdDetector-windows` (제출본 zip), `IllegalAdDetector-windows-render` (참고본 zip), `smoke-output-static`·`smoke-output-render` (스모크 리포트·로그)

명령줄에서 내려받기:

```
gh run list --workflow build-windows.yml -L 5
gh run download <run-id> -n IllegalAdDetector-windows -D build/dist_windows/
gh run download <run-id> -n IllegalAdDetector-windows-render -D build/dist_windows/
```

## 4. 손으로 빌드 (Windows PowerShell)

저장소 루트에서 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r src/requirements.txt
# 제출본(정적 전용)
python -m pip install -r build/requirements-build.txt
$env:IAD_STATIC_ONLY = "1"
pyinstaller build/iad.spec --noconfirm --clean --distpath build/dist --workpath build/work
Compress-Archive -Path build/dist/IllegalAdDetector -DestinationPath build/IllegalAdDetector-windows.zip -Force
```

참고본은 `build/requirements-build-render.txt` 를 설치하고 `IAD_STATIC_ONLY` 를 지운 뒤 같은 pyinstaller 명령을 실행한다(새 venv 권장). `IAD_STATIC_ONLY=1` 이면 spec 이 playwright 가 설치돼 있어도 넣지 않는다.

`playwright install` 은 실행하지 않는다. 렌더링 모드는 PC 에 이미 있는 Edge 를 `channel="msedge"` 로 띄우므로 브라우저를 따로 받을 필요가 없다. Edge 를 찾지 못하면 프로그램이 정적(HTML 직접 수집) 모드로 자동 전환한다.

## 5. 빌드 설정 파일

| 파일 | 역할 |
|---|---|
| `build/iad.spec` | PyInstaller 설정. GUI(`src/run_gui.py`)·CLI 두 진입점을 한 폴더로 묶는다. `iad` 패키지 서브모듈과 데이터 파일, certifi 인증서를 넣고, playwright 가 설치돼 있고 `IAD_STATIC_ONLY=1` 이 아닐 때만 Playwright 드라이버(node + package)를 포함한다 |
| `build/entry_cli.py` | CLI exe 진입점. `python -m iad` 와 같은 동작 |
| `build/hooks/rth_iad.py` | 런타임 훅. 표준 출력을 UTF-8 로 바꿔 한글 출력이 깨지거나 오류 나는 것을 막는다. 스모크 테스트 때만 GUI 창을 몇 초 뒤 자동으로 닫는다 |
| `build/requirements-build.txt` | 제출본 빌드 도구 버전 고정 (PyInstaller) |
| `build/requirements-build-render.txt` | 참고본 빌드 도구 (위 + Playwright) |
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
   * `iad-cli.exe --demo --no-open`: exe 폴더의 `demo\` 에 result.json(같은 검사)·report.html·demo_labels.json 생성
   * `--demo` 로그에 브라우저 단계 실행 또는 생략 사유가 찍히는지, 소요 시간 기록
   * `--demo` 로그에 OCR 단계 결과(인식 이미지 수, 광고 판정 수) 또는 생략 사유가 찍히는지
   * 제출본만(`-ExpectRenderFallback`): `--render` 를 줘도 종료 코드 0, "렌더 비교를 사용할 수 없어…" 안내 로그, result.json 정상 생성
   * 강제 종료 내구성: `--max-pages 1000 --depth 10 --delay 1` 로 실행하고 5초 뒤 `Stop-Process -Force`(TerminateProcess) → exe 폴더 result.json 이 이번 실행에서 기록됐고 BOM 없는 유효 JSON, meta 5키 존재
   * 요약은 `smoke_summary.txt` (artifact `smoke-output-static`)
2. GUI: `IllegalAdDetector.exe` 를 실행해 tkinter 메인 루프까지 정상 진입하는지 확인한다. 런타임 훅이 진입 시 마커 파일을 쓰고 5초 뒤 창을 닫는다. 창이 뜨기 전에 죽거나 오류 대화상자에서 멈추면 마커가 생기지 않아 실패로 판정한다.
3. 실행 캡처(제출본만, `build/capture_gui.ps1`): 런타임 훅 캡처 모드(`IAD_SMOKE_CAPTURE=1`)로 GUI 를 띄워 첫 화면 → 데모 버튼 실행 → 결과 화면을 System.Drawing 으로 캡처하고, exe 폴더 `demo\report.html` 을 Edge `--headless=new --screenshot` 으로 찍는다. artifact `captures-static` (capture_1~3.png)

손으로 돌릴 때:

```powershell
./build/smoke_cli.ps1 -AppDir build/dist/IllegalAdDetector -FixturesDir src/fixtures -OutDir $env:TEMP\iad_smoke -ExpectRenderFallback
./build/smoke_gui.ps1 -Exe build/dist/IllegalAdDetector/IllegalAdDetector.exe
```

워크플로를 수동 실행할 때 `selftest` 를 체크하면 GUI 판정 로직 자체를 검증한다. 일부러 시작 중에 예외를 던지는 exe 는 Windows 에서 "Unhandled exception in script" 대화상자를 띄운 채 프로세스가 살아 있으므로, 단순히 "몇 초 뒤 프로세스 생존"만 보면 통과로 잘못 판정된다. 마커 방식은 이 경우를 실패로 잡는다(2026-10-23 실행에서 확인).

## 7. 최근 빌드 결과

| 항목 | 값 |
|---|---|
| 실행 | GitHub Actions run 39910503805 (커밋 5fe2bb3, 2026-10-23), static·render 두 job 모두 success. 이 문서 갱신 커밋은 `[skip ci]` 로 재빌드하지 않음(코드 동일) |
| 제출본 | `IllegalAdDetector-windows.zip` 25,202,348 bytes, 1,024 files (풀면 45,775,967 bytes) |
| 참고본 | `IllegalAdDetector-windows-render.zip` 66,795,741 bytes |
| 단위 테스트 | 285 passed (static·render) |
| CLI 스모크(제출본) | PASS, 검사 59개 FAIL 0. fixtures 크롤(result.json·BOM·meta·리포트), `--demo` 9.3초, `--render` 폴백 안내, 5초 강제 종료 후 exe 폴더 result.json 유효(meta 5키) |
| 브라우저 단계 | 러너 Edge 로 동작. 제출본 데모 의심 페이지 1쪽 렌더 성공, 0쪽 실패. 1쪽 약 1~5초(환경에 따라) |
| 실행 캡처 | `build/capture_gui.ps1` 3장 (artifact `captures-static`) |
| GUI 스모크(제출본) | PASS. mainloop 진입 후 5초 뒤 자동 종료, exit 0 |
| 캡처 확인 | capture_1 의 "OCR(이미지 글자)" 체크와 "정적 분석 전용 배포본 / Edge 렌더 비교 미포함" 두 줄 안내가 창 안에 잘림 없이 표시됨(이미지로 확인) |
| OCR 단계 | 러너 데모: 배너 이미지 2개 인식 0.5초. 광고 판정은 아래 실기 검증에서 확인 |
| 실기 검증 | Windows 11 ARM64 한국어 환경에서 제출본 실행: 데모 12.5초, 4종 59/59, OCR 단계 이미지 2개 3.2초·도박 배너 1건 IMAGE_TEXT_AD 검출·예방 캠페인 배너 제외, Edge 단계 정상, 트레이스백 없음, `--no-ocr` 동작 |

평가 PC 조건(요강 붙임3): Windows 11, GPU 없는 일반 PC, 검출 시간 상한 30분. CLI 기본 시간 예산은 `--time-budget 1200`(20분)이다.
