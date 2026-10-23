# iad — 공공 웹사이트 불법광고 탐지 도구 (v0.1, 정적 규칙 기반)

진입 URL 1개를 받아 같은 도메인의 하위 페이지·게시글·댓글·iframe 내부까지 BFS 로 수집하고, 숨김·난독화된
도박/성인/불법금융 광고를 규칙과 로컬 점수화만으로 탐지한다(상용 AI API 사용 안 함, 네트워크는 대상 사이트만).

## 구조

```
src/
  run_gui.py          tkinter GUI (PyInstaller 진입점) — URL 입력, 진행 로그, 검출 결과 화면, 리포트 열기
  iad/
    __main__.py       CLI  python -m iad --url URL [--depth 3 --max-pages 300 --delay 0.3 --out DIR --result-dir DIR --render]
    scan.py           파이프라인: 크롤 → 분석 → result.json/result_extra.json → report.html/csv/json
    crawler.py        동일 도메인 BFS, 페이지네이션, iframe(동일 도메인=추적, 외부=1단계 수집+플래그), robots 옵션,
                      EUC-KR 처리, 시간 예산(기본 20분)·최대 페이지(기본 300) 상한,
                      동일 사이트 외부 CSS(<link rel=stylesheet>, @import 1단계) 수집(URL 당 1회 캐시, 최대 40개)
    analyzer.py       페이지 분석기. 요강 location 규칙, 4종 technique 판정, 추가 유형(ETC)
    hidden.py         숨김 기법: inline style / <style>·외부 CSS 규칙(명시도·!important 캐스케이드, @media print 제외) /
                      속성 / 크기 / 글자색≈배경색(조상 배경·bgcolor, 배경 이미지면 판정 보류) / transform·margin·text-indent offscreen
    normalize.py      난독화 정규화(자모 합성, NFKC 전각, 유사문자, 제로폭·특수문자·이모지 제거) — 레벨별 함수
    keywords.py       키워드 사전(도박·성인·불법금융·기타), 화이트리스트 문맥, 행정 문맥(키워드 주변 ±100자 예방·단속·신고 등)
                      (.py 모듈 — 데이터 파일 불필요)
    links.py          링크 휴리스틱(의심 TLD, 숫자 도메인, 단축 URL, 텔레그램/오픈채팅, 앵커-도메인 불일치, 대량 외부링크)
    scripts.py        document.write/innerHTML 링크 주입, eval, meta refresh, JS 리다이렉트,
                      인코딩 디코딩(base64·fromCharCode·\x/\u 이스케이프·%XX·hex 문자열·배열 join, 최대 3겹) 후 키워드·링크 재분석
    cloak.py          클로킹 점검: 최상위 페이지(진입→디렉터리별 첫 페이지→나머지, 기본 40개)를 Yeti+네이버검색 Referer / Googlebot
                      으로 다시 받아 일반 응답에 없는 요소·외부 링크·외부 리다이렉트를 ETC(CLOAKING_*) 로 보고(result.json 에는 안 넣음)
    official.py       요강 붙임4 스키마 result.json / result_extra.json 작성
    report.py         자체완결 HTML 리포트(필터·정렬·근거 펼치기) + CSV + JSON
    render.py         선택: playwright channel="msedge" 로 정적 DOM vs 렌더 DOM 차이(동적 주입)·요소 스크린샷
  fixtures/           하네스용 가짜 공공기관 사이트(gen_fixtures.py 가 dev/, holdout/, labels.json 을 생성)
  eval.py             로컬 http.server 로 fixtures 를 띄워 공식 채점 단위로 평가 → EVAL_RESULT.md, eval_result.json
  tests/              pytest
```

## 실행

```bash
cd src
~/.local/bin/uv sync --extra dev            # Python 3.12, requests/beautifulsoup4/lxml(+pytest)
uv run python -m iad --url https://www.example.go.kr/board/list --depth 3 --max-pages 300
uv run python run_gui.py                    # GUI
uv run python eval.py                       # 하네스 (프로젝트 루트에서는 uv run --project src python src/eval.py)
uv run pytest -q
```

## 결과 파일 (요강 붙임4 적용 — 결정 사항)

- `result.json`, `result_extra.json` 은 **구동 파일이 있는 폴더**에 생성한다. frozen exe 면 `sys.executable` 의 폴더,
  소스 실행이면 현재 작업 폴더(`--result-dir` 로 변경 가능). UTF-8, BOM 없음, 들여쓰기 2.
- `meta.topic` 은 요강 예시값 그대로 `"TOPIC"` 을 쓴다(표의 "TOPIC(불법광고)" 는 설명으로 해석). 필수 meta 필드
  entry_url / started_at / finished_at(ISO 8601, +09:00) / elapsed_sec 와 선택 tool_version 을 모두 넣는다.
- `result.json` findings 는 4종(HOMOGLYPH / JAMO / TRANSPARENT / OFFSCREEN)만. 한 요소에 기법이 겹치면 url·location 이
  같은 객체를 기법별로 따로 만든다. 같은 (url, location, technique) 은 1건으로 합친다.
- `result_extra.json` 은 technique `"ETC"` 고정, `extra_finding` 에 우리가 정한 유형 이름(HTML_COMMENT, NOSCRIPT,
  HIDDEN_IFRAME, HIDDEN_VISIBILITY_HIDDEN, SCRIPT_INJECTION, META_REFRESH, SUSPICIOUS_TLD, SHORTENER, MESSENGER,
  ANCHOR_MISMATCH, MASS_EXTERNAL_LINKS, OBFUSCATION_INSERT, DYNAMIC_INJECTION, SCRIPT_DECODED, HIDDEN_EXTERNAL_LINK …)+분류+위험도+점수를 적는다.
  예시에 없던 `is_violation` 도 필수 필드 표를 따라 넣는다. (url, location) 당 1건으로 합친다.
- **location 규칙**: 태그.클래스 를 상위부터 ` > ` 로 연결, 클래스가 없으면 `tr:nth-of-type(7)` 처럼 순서 지정
  (같은 클래스 형제가 여럿이면 클래스에도 nth-of-type 을 붙여 유일하게 만든다). html/body 는 생략하되 선택자가
  문서에서 유일하지 않으면 `html > body > ` 를 앞에 붙인다. iframe 내부는 `iframe[src="절대주소"] >>> 선택자`
  (중첩 시 반복, 상대 src 는 절대 주소로). iframe 내부 검출의 `url` 은 iframe 을 품은 최상위 페이지 URL 이다.
- `evidence_text` 는 해당 요소의 원문 텍스트(정규화 전) 500자까지.

### 4종 판정 기준(오탐이 정확도 감점이라 보수적으로)
| 코드 | 조건 |
|---|---|
| OFFSCREEN | display:none / font-size 0~1px / position(+left·top·right·bottom·inset)·text-indent·transform translate·음수 margin 으로 화면 밖(≤-500px) 인 요소 **+** 요소 텍스트에 가중치 2.0 이상 키워드(난독화와 겹치면 1.0 이상) |
| TRANSPARENT | color 가 배경색과 같거나 채널별 차이 ≤10(가장 가까운 조상 배경색·bgcolor, 기본 흰색; 배경 이미지·그라데이션만 있으면 판정 안 함) / color:transparent·알파 ≤0.05(rgba/hsla/#rrggbbaa) / opacity ≤0.05 **+** 위와 같은 키워드 조건 |
| HOMOGLYPH | 전각·키릴·그리스·숫자 유사문자를 치환해야 키워드가 맞거나, 평문 키워드(≥2)와 전각/키릴 문자가 같은 말단 요소에 공존 |
| JAMO | 분리 자모를 합성해야 키워드가 맞거나, 평문 키워드(≥2)와 합성 가능한 자모가 같은 말단 요소에 공존 |

visibility:hidden, hidden 속성, 1×1 크기/clip, marquee, noscript, HTML 주석, 숨김 + 링크만(키워드 없음) 등 요강 정의가
불명확한 것은 result.json 에 넣지 않고 result_extra.json 으로 보낸다. 요소 위치는 숨김 스타일이 걸린 요소(4종 중
TRANSPARENT/OFFSCREEN; 부모가 display:none 이고 자식에 광고가 있으면 그 부모), 난독화 텍스트를 품은 가장 안쪽 요소(HOMOGLYPH/JAMO)다.

행정 안내문 제외 규칙(AR2): 보이는 텍스트의 불법 키워드 주변 ±100자(정규화 문자열)에 예방·단속·적발·주의보·1336·상담·교육·신고 등
행정 문맥이 합계 -2 이하로 있고, 의심 링크·은닉·스크립트·난독화 근거가 없으면 보고하지 않는다. 난독화(자모·유사문자·제로폭)가 있으면
정상 문맥 감점을 절반만 적용한다(난독화된 안내문은 없다). 접근성 숨김(.sr-only/.blind/skip-link)의 정상 텍스트·공공기관 링크는
키워드가 없으므로 4종은 물론 ETC 에도 올리지 않으며, 숨긴 요소 안 링크는 비신뢰 도메인일 때만 HIDDEN_EXTERNAL_LINK 로 보고한다.

스타일 해석 규칙: 인라인 style, 문서 `<style>`, 동일 사이트 외부 CSS(`<link rel=stylesheet>`·`@import` 1단계)를 모두 읽고
(!important, 명시도, 선언 순서) 순으로 캐스케이드한다. 의사클래스(:hover 등) 선택자와 `@media print` 블록은 적용하지 않는다.
외부 CSS 는 숨김 판정에 쓰는 속성(display/visibility/opacity/font-size/position/offset/text-indent/transform/margin/clip/color/background/크기)
만 추려 요소에 매핑하므로 대형 사이트 CSS 에서도 페이지당 수십 ms 수준이다.

## 하네스 (`eval.py`)
- `fixtures/gen_fixtures.py` 가 단일 소스에서 dev/holdout 두 사이트와 `labels.json` 을 만든다(요소 id 는 중립, 탐지기는 id 를 읽지 않음).
  각 세트: 게시판 목록 2쪽 + 게시글 16 + 댓글 + 동일 도메인 iframe + 외부(localhost) iframe + EUC-KR 페이지 + 정상 문서 7종
  (도박중독 예방, 성인지 교육, 햇살론 대출 안내, 유해정보 차단 안내, 마약류 예방, 유관기관 링크 모음+sr-only, 성인병 안내+숨김 메뉴).
  외부 CSS 파일(@import 포함) 로 숨긴 게시글 1개(transform/음수 margin/rgba·hsla·#rrggbbaa 투명/근사색/숨긴 탭 상속 + 인쇄 전용·배경 이미지 하드 네거티브).
  클로킹 페이지 1개(같은 경로의 `.bot` 파일을 eval 서버가 봇 UA·네이버 Referer 요청에만 응답).
  4종 라벨 33개(중첩 2요소 포함), ETC 라벨 17개. holdout 은 문구·TLD·CSS 수법(top:-5000px, rgb 배경 등)을 바꿨고 규칙 튜닝에 쓰지 않는다.
- 채점은 요강 방식 그대로: result.json 의 (url, location, technique) 단위로, location 을 DOM 에서 해석해 라벨 요소와 같은지 비교.
  정확도 = 정탐/전체 검출. 소요시간·기법별 재현율·오탐·미탐 목록을 `EVAL_RESULT.md`, `eval_result.json` 에 남긴다.
- 하네스는 `allowed_hosts` 오프라인 가드로 127.0.0.1/localhost 외에는 요청하지 않는다.

## 빌드 (PyInstaller, Windows)
- 진입점 `src/run_gui.py` (CLI 는 `python -m iad`). 데이터 파일 없음(키워드 사전은 .py).
- hidden imports: `lxml._elementpath`, `bs4.builder._lxml`, `soupsieve`, `requests`, `charset_normalizer`, `idna`,
  `urllib3`, `tkinter`, `tkinter.ttk`. playwright 는 번들하지 않아도 되며(없으면 자동 생략), 넣으려면 `--extra render`.
- 예: `pyinstaller --noconfirm --onefile --windowed --name iad run_gui.py --collect-submodules lxml --hidden-import bs4.builder._lxml`
- 기본값(깊이 3, 300페이지, 0.3s 간격, 10s 타임아웃, 시간 예산 20분, 클로킹 점검 40페이지×2요청)으로 30분 타임아웃 안에 끝난다.
  크롤 시간 예산을 다 쓰면 클로킹 점검은 건너뛴다. `--cloak-pages 0`(GUI 체크 해제)으로 끌 수 있다.

## 알려진 한계
- 정적 분석 중심. 외부 CSS 는 동일 사이트 것만 받고(타 도메인 CDN CSS 는 안 받음), 의사클래스·`calc()`·CSS 변수(`var()`)·
  미디어쿼리 조건(화면 크기)은 해석하지 않는다. JS 로 뒤늦게 붙는 클래스/스타일은 `--render` 일 때만 보인다.
- 렌더 비교·스크린샷은 Edge+playwright 가 있을 때만(선택). 동적 주입은 그때만 잡힌다.
- 키워드 사전 기반이라 사전에 없는 신조어는 놓칠 수 있다. 이미지(배너) 안 문구는 보지 않는다.
- 로그인·POST 폼 뒤 페이지, JS 로만 이동하는 게시판은 수집하지 못한다.
- 외부 사이트로 나가는 배너 링크의 목적지(1-hop)는 열어 보지 않는다(평가 환경이 폐쇄망이면 타임아웃만 쌓이고, 대상 사이트 외
  네트워크 접근을 하지 않는다는 원칙 때문). 외부 iframe 은 1단계 수집한다.
