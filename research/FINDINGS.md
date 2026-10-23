# 정적 분석 한계 보완 조사 (2026-10-23, 조사 에이전트 보고 요약 저장본)

전제: Windows 11 CPU PC, 평가 타임아웃 30분, 제출 exe 25MB, playwright 미포함. 시제품은 이 폴더(edge_dump.py, cdp_probe.py, js_stub.py, win_ocr.py, fixtures/)에 있다. 맥 Chrome 155로만 실측했고 Windows 실측은 없다.

## 권고 순위

| 순위 | 방법 | 검증 | 번들 증가 | 통합 비용 |
|---|---|---|---|---|
| 1 | OS 기본 Edge `--headless=new --dump-dom` 으로 JS 실행 후 DOM을 기존 analyze_page에 한 번 더 (edge_dump.py) | 맥 실측 통과(document.write·atob+innerHTML·setTimeout 2초 지연 주입 회수, `--virtual-time-budget`, 0.41초/회, while(true)는 시간 내 None·잔여 프로세스 0) | 0 | 작음 |
| 2 | 같은 Edge를 CDP로 띄워 getComputedStyle·bbox로 숨김 판정 (cdp_probe.py, websocket은 socket 직접 구현) | 맥 실측 통과(은닉 10종 전부, 정상 문단 visible, z-index 덮기 BEHIND는 정적으로 불가능한 판정, 무한루프도 terminateExecution 후 부분 DOM) | 0 | 중간(판정 이유→Finding 매핑) |
| 3 | 브라우저 없을 때 QuickJS 스텁 DOM으로 인라인 스크립트 실행 (js_stub.py) | 맥 실측 통과(주입·eval(fromCharCode)·appendChild·referrer 조건 리다이렉트·5초 setTimeout 회수, 무한루프·재귀·메모리 폭주 상한 중단) | quickjs 휠 0.38MB | 작음(페이지당 합계 상한 필요, time limit 중 파이썬 콜백 불가라 스텁은 순수 JS) |
| 4 | Windows 내장 OCR을 powershell.exe 5.1로 호출 (win_ocr.py) | 문법만 확인, 미실측 | 0 | 중간(ko OCR 언어팩 유무 불확실, 없으면 en으로 도메인·숫자만) |

1과 2는 하나의 CDP 경로로 합칠 수 있다. 3은 Edge 없거나 정책으로 막힌 PC용 대체.

## Edge 경로 세부
- 브라우저 탐색: 환경변수 IAD_BROWSER → 레지스트리 App Paths msedge.exe(HKLM/HKCU, 32/64) → %ProgramFiles(x86)%·%ProgramFiles%·%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe → chrome.exe → PATH.
- 호출마다 임시 --user-data-dir, `--headless=new --no-first-run --no-default-browser-check --disable-extensions --disable-sync --disable-background-mode --disable-component-update`. 타임아웃 시 Windows `taskkill /T /F /PID`. stdout은 바이트로 받아 UTF-8 디코딩(text=True 금지, cp949 깨짐).
- CDP 포트: `--remote-debugging-port=0` 후 임시 프로필 DevToolsActivePort 첫 줄.
- 위험: 정책 HKLM\SOFTWARE\Policies\Microsoft\Edge HeadlessModeEnabled=0 또는 RemoteDebuggingAllowed=0이면 막힘 → 미리 읽고 0이면 건너뜀. 평가 PC 미실측 → 반드시 "None이면 정적 결과만" 구조.
- 통합 제안: 인라인 script에 write/innerHTML/insertAdjacentHTML/appendChild/eval/atob가 있는 페이지만 재수집, 정적 DOM에 없던 요소만 추가 Finding. 페이지당 15초, 브라우저 단계 전체 5분 상한.

## 정적 분석에 없는 신호 (src와 대조)
1. head 키워드 주입(title, meta description/keywords, og:title) — 하
2. JS가 로드 시 숨김 처리(getElementById(x).style.display='none') — 중
3. JS 조건 분기 클로킹(document.referrer/navigator.userAgent 검사 후 write/redirect) — 하(js_stub referrer=google)
4. 외부 `<script src>` 본문 분석 — 중
5. 클로킹 프로필 추가(모바일 UA, Bingbot, 사람 UA+google Referer) — 하
6. 상태코드 차이(봇 200/사람 404)·본문 유사도 — 중
7. sitemap.xml·robots.txt 변조 — 하
8. 도어웨이 URL 패턴(slot-gacor, 랜덤 slug .html 대량) — 하
9. 외국어 도박 사전(judi, gacor, togel, maxwin, 博彩)과 lang 불일치 — 하~중
10. 한 글자·구두점 하나에 건 링크 — 하
11. z-index 음수·이미지 뒤로 텍스트 덮기 — CDP BEHIND로 해결
12. canonical/amphtml/hreflang/alternate가 외부 도박 도메인 — 하
13. 만료 도메인 탈취 링크(국내 보도 주류 유형) — 중

참고: github.com/catsec/sitesweep, github.com/akbak/CloakDetect, github.com/jvoisin/php-malware-finder. KISA 공개 권고문은 못 찾음.

## 출처
developer.chrome.com headless-cli·removing-headless-old·remote-debugging-port, learn.microsoft.com Edge 정책 HeadlessModeEnabled·RemoteDebuggingAllowed, Windows.Media.Ocr TryCreateFromLanguage, HumanEquivalentUnit/PowerShell-Misc Get-Win10OcrTextFromImage.ps1, web.dev fix-the-japanese-keyword-hack, Google 스팸 정책 hidden text and links, Sucuri blog 2017-03 hidden SEO hack.
