# iad — 공공 웹사이트 불법광고 탐지 도구 (v0.1, 정적 규칙 기반)

진입 URL 1개를 받아 같은 도메인의 하위 페이지·게시글·댓글·iframe 내부까지 BFS 로 수집하고, 숨김·난독화된
도박/성인/불법금융 광고를 규칙과 로컬 점수화만으로 탐지한다(상용 AI API 사용 안 함, 네트워크는 대상 사이트만).

## 구조

```
src/
  run_gui.py          tkinter GUI (PyInstaller 진입점) — URL 입력, 진행 로그, 검출 결과(우선순위·영역·필터·검색, 더블클릭 상세/조치 가이드,
                      선택자·URL 복사), 데모 실행, 리포트 열기
  iad/
    __main__.py       CLI  python -m iad --url URL [--depth 3 --max-pages 300 --delay 0.3 --out DIR --result-dir DIR --render]
    scan.py           파이프라인: 크롤 → 분석 → result.json/result_extra.json → report.html/csv/json
    crawler.py        동일 도메인 우선순위 BFS(진입 경로 상세 > 페이지네이션 > 진입 경로 > 다른 영역 상세 > 게시판 영역 > 그 외),
                      링크 소스: href·javascript:/onclick 핸들러 안 URL·data-href/url/link·rel=next/prev·meta refresh·
                      인라인 스크립트 안 동일 사이트 경로(.do/.jsp/.php/.html…, 댓글 목록 URL 등), 지연 로딩 iframe(data-src),
                      iframe(동일 도메인=추적, 외부=1단계 수집+플래그, 중첩 3단계), robots 옵션,
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
    triage.py         작업지시서 보강: 발견 영역 분류(게시글 본문/댓글/목록/푸터/iframe…), 기법별 조치 가이드·신고처, defang URL,
                      SHA-256 지문(URL+위치+원문 HTML), 처리 우선순위(긴급/높음/보통)
    report.py         자체완결 HTML 작업지시서(요약 카드·영역별 집계, 필터·정렬·검색·4종만, 행별 조치 가이드·근거·지문, 선택자/URL 복사,
                      처리 상태·메모(localStorage), 페이지별 작업지시서 인쇄 화면, 상태 JSON 내보내기) + CSV + JSON
    render.py         선택: playwright channel="msedge" 로 정적 DOM vs 렌더 DOM 차이(동적 주입)·요소 스크린샷
    testbed.py        내장 테스트베드: 가짜 공공기관 사이트 생성기(dev/holdout + labels.json) + 로컬 서버(클로킹 .bot 응답 포함)
    demo.py           --demo: 테스트베드를 임시 폴더에 생성·127.0.0.1 로 서빙 → 스캔 → 구동폴더/demo 에 결과·리포트 → 브라우저 열기
  fixtures/           하네스용 가짜 공공기관 사이트(gen_fixtures.py 는 iad/testbed.py 의 얇은 래퍼; dev/, holdout/, labels.json 생성)
  eval.py             로컬 http.server 로 fixtures 를 띄워 공식 채점 단위로 평가 → EVAL_RESULT.md, eval_result.json
  tests/              pytest
```

## 실행

```bash
cd src
~/.local/bin/uv sync --extra dev            # Python 3.12, requests/beautifulsoup4/lxml(+pytest)
uv run python -m iad --url https://www.example.go.kr/board/list --depth 3 --max-pages 300
uv run python -m iad --demo                 # 내장 테스트베드 데모(네트워크 불필요, 결과는 ./demo/, 리포트 자동 열기)
uv run python run_gui.py                    # GUI ("데모 실행" 버튼 = --demo)
uv run python eval.py                       # 하네스 (프로젝트 루트에서는 uv run --project src python src/eval.py)
uv run pytest -q
```

## 결과 파일 (요강 붙임4 적용 — 결정 사항)

- `result.json`, `result_extra.json` 은 **구동 파일이 있는 폴더**에 생성한다. frozen exe 면 `sys.executable` 의 폴더,
  소스 실행이면 현재 작업 폴더(`--result-dir` 로 변경 가능). UTF-8, BOM 없음, 들여쓰기 2.
- `meta.topic` 은 요강 예시값 그대로 `"TOPIC"` 을 쓴다(표의 "TOPIC(불법광고)" 는 설명으로 해석). 필수 meta 필드
  entry_url / started_at / finished_at(ISO 8601, +09:00) / elapsed_sec 와 선택 tool_version 을 모두 넣는다.
- `result.json` findings 는 4종(HOMOGLYPH / JAMO / TRANSPARENT / OFFSCREEN)만. 같은 (url, location, technique) 은 1건으로 합친다.
- **겹침 이중 보고(결정)**: 한 요소가 은닉(OFFSCREEN/TRANSPARENT)되어 있으면서 내용이 난독화(JAMO/HOMOGLYPH)된 경우, 같은
  url+location 으로 두 finding(은닉 기법 1개 + 난독화 기법 1개)을 모두 낸다. 근거: 요강은 finding 당 technique 1개이고 "동일 요소에
  2개 이상의 기법이 중첩 적용된 경우 기법별로 별도 객체 생성"을 허용하며, 채점자가 어느 쪽 라벨을 붙였을지 알 수 없어 한쪽만 내면
  검출 개수(45점)를 잃을 수 있다. 은닉 기법끼리 겹칠 때(opacity:0 + left:-9999px, display:none + color:#fff)는 지배적인 하나만
  낸다(display:none > 화면 밖 위치 > font-size 0 > 글자색=배경색 > opacity). 난독화 기법끼리(JAMO + HOMOGLYPH)는 각각 치환 매칭이
  성립할 때만 둘 다 낸다.
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
| OFFSCREEN | display:none(hidden 속성 포함) / font-size 0~1px(0, 0px, 0em, 0~6%, font 단축 `0/0`) / position(+left·top·right·bottom·inset)·text-indent·transform translate·음수 margin 으로 화면 밖(≤-500px) 이거나 absolute/fixed 로 뷰포트 밖 양수(≥5000px) / overflow:hidden 조상 상자(명시 크기) 밖에 absolute 배치 / 잘림(1×1·0 크기+overflow:hidden, clip:rect(0 0 0 0), clip-path inset(100%)·circle(0), transform:scale(0), max-height 0+overflow hidden) **+** 요소 텍스트에 가중치 2.0 이상 키워드(난독화와 겹치면 1.0 이상) |
| TRANSPARENT | color 가 배경색과 같거나 채널별 차이 ≤10(가장 가까운 조상 배경색·bgcolor, 기본 흰색; 배경 이미지·그라데이션만 있으면 판정 안 함) / color:transparent·알파 ≤0.05(rgba/hsla/#rrggbbaa) / opacity ≤0.05 **+** 위와 같은 키워드 조건 |
| HOMOGLYPH | (a) 전각·키릴·그리스·라틴확장·leet(0/1/3/4/5/7/8/9/@/$, 1은 l·i 두 가지로) 유사문자를 치환해야 사전 키워드가 맞음(평문 키워드 없어도 됨) (b) **스크립트 혼용 토큰**(한 단어 안에 키릴·그리스·체로키·아르메니아·스몰캡 + 라틴/한글/숫자, 라틴 글자 사이 숫자·기호(leet), 전각 영문자)을 confusables 골격으로 되돌린 문자열에 사전 키워드 또는 영문 도박어(casino/toto/slot/bet/poker/jackpot/win…)가 있음 — 위장 자체가 1급 신호. 전각만인 토큰(ＷＩＮ－ＷＩＮ, IME 입력)은 가중치 ≥2 단어만, 가장자리 기호(@vip, $10)·끝 숫자(covid19)는 혼용으로 안 봄 (c) 평문 키워드(≥2)와 전각 문자/스크립트 혼용이 같은 말단 요소에 공존. 문장 전체가 키릴인 정상 러시아어는 해당 없음 |
| JAMO | 분리 자모를 합성해야 키워드가 맞거나, **초성 축약**(ㅋㅈㄴ=카지노, ㅂㅋㄹ=바카라; 3자 이상은 단독, 2자(ㅌㅌ)는 흔한 채팅 축약 제외+사이트·가입·코드 등 문맥어 동반 시)이 맞거나, 평문 키워드(≥2)와 합성 가능한 자모가 공존. 초성 퀴즈·한글 교육 문맥(화이트리스트 ≤-3)에서는 초성 축약만으로는 인정하지 않음 |

visibility:hidden, aria-hidden, input type=hidden, 1×1 iframe, marquee, noscript, HTML 주석, 숨김 + 링크만(키워드 없음) 등 요강 정의가
불명확한 것은 result.json 에 넣지 않고 result_extra.json 으로 보낸다. (결정 변경: `hidden` 속성은 UA 스타일 display:none 이고,
1×1/clip/scale(0) 잘림은 "화면 밖 은닉"의 일반형이므로 OFFSCREEN 으로 낸다 — 키워드 조건은 동일해 접근성 숨김 정상 문구는 해당 없음.) 요소 위치는 숨김 스타일이 걸린 요소(4종 중
TRANSPARENT/OFFSCREEN; 부모가 display:none 이고 자식에 광고가 있으면 그 부모), 난독화 텍스트를 품은 가장 안쪽 요소(HOMOGLYPH/JAMO)다.

행정 안내문 제외 규칙(AR2): 보이는 텍스트의 불법 키워드 주변 ±100자(정규화 문자열)에 예방·단속·적발·주의보·1336·상담·교육·신고 등
행정 문맥이 합계 -2 이하로 있고, 의심 링크·은닉·스크립트·난독화 근거가 없으면 보고하지 않는다. 난독화(자모·유사문자·제로폭)가 있으면
정상 문맥 감점을 절반만 적용한다(난독화된 안내문은 없다). 접근성 숨김(.sr-only/.blind/skip-link)의 정상 텍스트·공공기관 링크는
키워드가 없으므로 4종은 물론 ETC 에도 올리지 않으며, 숨긴 요소 안 링크는 비신뢰 도메인일 때만 HIDDEN_EXTERNAL_LINK 로 보고한다.

스타일 해석 규칙: 인라인 style, 문서 `<style>`, 동일 사이트 외부 CSS(`<link rel=stylesheet>`·`@import` 1단계)를 모두 읽고
(!important, 명시도, 선언 순서) 순으로 캐스케이드한다. 의사클래스(:hover 등) 선택자와 `@media print` 블록은 적용하지 않는다.
외부 CSS 는 숨김 판정에 쓰는 속성(display/visibility/opacity/font-size/position/offset/text-indent/clip/color/background/크기, margin·transform 은
화면 밖 값일 때만)만 추리고, 단순 선택자(tag/.class/#id)는 페이지당 1회 만든 색인으로 해석하므로 5,000규칙 CSS + 300페이지 사이트도
전체 7초 안팎(페이지당 ~25ms, 클로킹 점검 포함)이다.

## 하네스 (`eval.py`)
- `fixtures/gen_fixtures.py` 가 단일 소스에서 dev/holdout 두 사이트와 `labels.json` 을 만든다(요소 id 는 중립, 탐지기는 id 를 읽지 않음).
  각 세트: 게시판 목록 2쪽 + 게시글 16 + 댓글 + 동일 도메인 iframe + 외부(localhost) iframe + EUC-KR 페이지 + 정상 문서 7종
  (도박중독 예방, 성인지 교육, 햇살론 대출 안내, 유해정보 차단 안내, 마약류 예방, 유관기관 링크 모음+sr-only, 성인병 안내+숨김 메뉴).
  외부 CSS 파일(@import 포함) 로 숨긴 게시글 1개(transform/음수 margin/rgba·hsla·#rrggbbaa 투명/근사색/숨긴 탭 상속 + 인쇄 전용·배경 이미지 하드 네거티브).
  클로킹 페이지 1개(같은 경로의 `.bot` 파일을 eval 서버가 봇 UA·네이버 Referer 요청에만 응답),
  레드팀 R1 약점 페이지 1개(font-size 0%·font 단축, 초성 축약, 평문 없는 키릴·그리스·leet + 정상 러시아어·자모 교육·초성 퀴즈·전화번호 하드 네거티브).
  R2 페이지 1개(키릴 전체·전각·leet·체로키로 위장한 영문 도박어 + 정상 러시아어·전각 약어·covid19 하드 네거티브).
  R2 OFFSCREEN 일반형 페이지 1개(뷰포트 밖 양수·부모 overflow 밖·clip-path/clip·1×1·scale(0)·max-height 0·hidden 속성 + 접힌 아코디언·sr-only·숨긴 메뉴 하드 네거티브).
  4종 라벨 49개(중첩 2요소 포함), ETC 라벨 16개. holdout 은 문구·TLD·CSS 수법(top:-5000px, rgb 배경 등)을 바꿨고 규칙 튜닝에 쓰지 않는다.
- 채점은 요강 방식 그대로: result.json 의 (url, location, technique) 단위로, location 을 DOM 에서 해석해 라벨 요소와 같은지 비교.
  정확도 = 정탐/전체 검출. 소요시간·기법별 재현율·오탐·미탐 목록을 `EVAL_RESULT.md`, `eval_result.json` 에 남긴다.
- 하네스는 `allowed_hosts` 오프라인 가드로 127.0.0.1/localhost 외에는 요청하지 않는다.

## 빌드 (PyInstaller, Windows)
- 진입점 `src/run_gui.py` (CLI 는 `python -m iad`). 데이터 파일 없음(키워드 사전은 .py, `--demo` 테스트 사이트도 `iad/testbed.py` 가
  실행 시점에 임시 폴더에 생성하므로 `src/fixtures/` 를 번들할 필요 없음). `collect_submodules("iad")` 로 testbed/demo/cloak 모듈이 포함된다.
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
