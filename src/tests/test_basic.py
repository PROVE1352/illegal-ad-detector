"""기본 테스트: 정규화, 키워드 레벨, 숨김 기법, 링크 휴리스틱, 요강 location 규칙, 픽스처 end-to-end(파일 기반)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from bs4 import BeautifulSoup  # noqa: E402

from iad import hidden as H  # noqa: E402
from iad.analyzer import analyze_page, location_of  # noqa: E402
from iad.keywords import match_keywords_levels  # noqa: E402
from iad.links import analyze_link  # noqa: E402
from iad.models import Page  # noqa: E402
from iad.normalize import aggressive, compose_jamo, level_homoglyph, level_jamo  # noqa: E402
from iad.official import build_extra, build_official  # noqa: E402


# ---------- normalize ----------
@pytest.mark.parametrize("src,expected", [("ㅌㅗㅌㅗ", "토토"), ("ㅋㅏㅈㅣㄴㅗ", "카지노"), ("ㅁㅓㄱㅌㅟ", "먹튀"), ("ㅋㅋ", "ㅋㅋ"), ("바ㅋㅏ라", "바카라")])
def test_compose_jamo(src, expected):
    assert compose_jamo(src) == expected


def test_levels_are_distinct():
    assert "토토사이트" in level_jamo("ㅌㅗㅌㅗ ㅅㅏㅇㅣㅌㅡ")
    assert "토토사이트" not in level_homoglyph("ㅌㅗㅌㅗ ㅅㅏㅇㅣㅌㅡ")   # NFKC 가 자모를 합성하지 않아야 함
    assert "casino" in level_homoglyph("c@sin0")
    assert aggressive("토.토 사 이 트") == "토토사이트"


# ---------- keywords ----------
def test_keyword_levels():
    assert match_keywords_levels("토토사이트 추천")["gambling"][0][2] == "plain"
    assert match_keywords_levels("ㅌㅗㅌㅗ ㅅㅏㅇㅣㅌㅡ")["gambling"][0][2] == "JAMO"
    assert match_keywords_levels("ｃａｓｉｎｏ 입장")["gambling"][0][2] == "HOMOGLYPH"
    assert "gambling" not in match_keywords_levels("오늘 날씨가 좋습니다")


# ---------- hidden ----------
@pytest.mark.parametrize("style,tech", [
    ("display:none", "display_none"), ("visibility:hidden", "visibility_hidden"), ("opacity:0", "opacity_zero"),
    ("font-size:0px", "font_size_zero"), ("font-size:1px", "font_size_zero"), ("position:absolute;left:-9999px", "offscreen"),
    ("text-indent:-9999px", "offscreen"), ("width:1px;height:1px;overflow:hidden", "tiny_size"), ("color:#fff", "color_match"),
    ("color:transparent", "color_match"), ("color:rgb(255,255,255)", "color_match"),
])
def test_hidden_inline(style, tech):
    soup = BeautifulSoup(f'<html><body><span style="{style}">x</span></body></html>', "lxml")
    el = soup.find("span")
    assert tech in [t for t, _ in H.hidden_techniques(el, {})]


def test_hidden_stylesheet_and_bg():
    html = '<html><head><style>.sr{position:absolute;left:-9999px}</style></head><body><div style="background:#eee"><span class="sr">a</span><b style="color:#eeeeee">b</b></div></body></html>'
    soup = BeautifulSoup(html, "lxml")
    sheet = H.apply_sheet(soup, H.sheet_rules(soup))
    assert ("offscreen", "position:absolute; left:-9999px") in H.hidden_techniques(soup.find("span"), sheet)
    assert "color_match" in [t for t, _ in H.hidden_techniques(soup.find("b"), sheet)]


# ---------- links ----------
def test_link_rules():
    rules = {r for r, _, _ in analyze_link("http://kk8282.top/x", "", "happy.go.kr")}
    assert {"link.suspicious_tld", "link.numeric_domain"} <= rules
    assert "link.shortener" in {r for r, _, _ in analyze_link("https://bit.ly/abc", "", "happy.go.kr")}
    assert "link.messenger" in {r for r, _, _ in analyze_link("https://t.me/xx", "", "happy.go.kr")}
    assert "link.anchor_mismatch" in {r for r, _, _ in analyze_link("http://evil.top", "www.happy.go.kr", "happy.go.kr")}
    assert analyze_link("https://www.mois.go.kr", "", "happy.go.kr") == []
    assert analyze_link("/local/path", "", "happy.go.kr") == []


# ---------- location 규칙 ----------
def test_location_rule():
    html = ('<html><body><div class="notice-board"><table class="board-list"><tr><td class="title"><a href="#">a</a></td></tr>'
            '<tr><td class="title"><a href="#">b</a></td></tr></table><p>x</p><p><span>y</span></p></div></body></html>')
    soup = BeautifulSoup(html, "lxml")
    a2 = soup.find_all("a")[1]
    loc = location_of(a2, soup)
    assert loc == "div.notice-board > table.board-list tr:nth-of-type(2) > td.title > a"
    assert soup.select(loc)[0] is a2
    span = soup.find("span")
    assert location_of(span, soup) == "div.notice-board > p:nth-of-type(2) > span"


# ---------- analyzer / official ----------
def test_official_codes_and_schema():
    html = '''<html><body><div class="a">
    <span class="h" style="display:none">토토사이트 추천 안전놀이터</span>
    <p class="d">정상 <span style="color:#fff">먹튀검증 안전놀이터 텔레그램 @x</span></p>
    <td class="t">ｍｅｇａ－ＢＥＴ 첫충 30％ 지급</td>
    <p>ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드 LUCKY7</p>
    <p>도박 중독 예방 상담 1336</p>
    <div style="display:none"><a href="/menu">메뉴</a></div>
    </div></body></html>'''
    fs = analyze_page(Page(url="http://ex.go.kr/v?id=1", html=html), "ex.go.kr")
    codes = {c for f in fs for c in f.official}
    assert codes == {"OFFSCREEN", "TRANSPARENT", "HOMOGLYPH", "JAMO"}
    # 정상 문맥·숨긴 메뉴는 4종에 없어야 함
    assert all("1336" not in f.evidence_text for f in fs if f.official)
    assert all("메뉴" not in f.evidence_text for f in fs)
    off = build_official(fs)
    for item in off:
        assert set(item) == {"id", "url", "is_violation", "location", "evidence_text", "technique"}
        assert item["is_violation"] is True and item["technique"] in ("HOMOGLYPH", "JAMO", "TRANSPARENT", "OFFSCREEN")
    assert len({i["id"] for i in off}) == len(off)
    for item in build_extra(fs):
        assert item["technique"] == "ETC" and item["extra_finding"]


def test_iframe_location_prefix():
    page = Page(url="http://ex.go.kr/widget/n", html='<html><body><div class="wrap"><span class="hidden-link" style="display:none">무료 슬롯사이트 체험</span></div></body></html>',
                is_iframe=True, top_url="http://ex.go.kr/view?id=1", frame_prefix='iframe[src="http://ex.go.kr/widget/n"] >>> ')
    fs = analyze_page(page, "ex.go.kr")
    assert fs and fs[0].location == 'iframe[src="http://ex.go.kr/widget/n"] >>> div.wrap > span.hidden-link'
    assert fs[0].page_url == "http://ex.go.kr/view?id=1"


def test_fixture_file_end_to_end():
    labels = json.loads((SRC / "fixtures" / "labels.json").read_text(encoding="utf-8"))
    doc = "post/post_recruit.html"
    html = (SRC / "fixtures" / "dev" / doc).read_text(encoding="utf-8")
    fs = analyze_page(Page(url=f"http://127.0.0.1:8765/dev/{doc}", html=html), "127.0.0.1")
    want = {l["element_id"] for l in labels["labels"] if l["set"] == "dev" and l["doc"] == doc}
    soup = BeautifulSoup(html, "lxml")
    got = set()
    for f in fs:
        if f.official:
            els = soup.select(f.location)
            assert len(els) == 1
            got.add(els[0].get("id"))
    assert want <= got


@pytest.mark.parametrize("html", [
    '<p>불법 토토사이트 신고 기간（10.1～10.15）</p>',             # 전각 구두점만으로 HOMOGLYPH 되면 안 됨
    '<p>문의 02-7070-1234</p>',                                     # 전화번호가 toto 로 읽히면 안 됨
    '<div style="display:none">강원랜드 카지노 관광 안내 캠페인</div>',  # 숨긴 탭 안 정상 안내
    '<font size="1" color="#000">작은 글씨 바카라 안내</font>',       # font size=1 은 1px 아님
])
def test_no_official_false_positive(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert not any(f.official for f in fs), [(f.location, f.official) for f in fs]


def test_table_tr_descendant_combinator():
    soup = BeautifulSoup('<html><body><table class="b"><tr><td>a</td></tr><tr><td class="t">b</td></tr></table></body></html>', "lxml")
    td = soup.find("td", class_="t")
    loc = location_of(td, soup)
    assert loc == "table.b tr:nth-of-type(2) > td.t"
    assert soup.select(loc)[0] is td
    with_tbody = BeautifulSoup('<html><body><table class="b"><tbody><tr><td>a</td></tr><tr><td class="t">b</td></tr></tbody></table></body></html>', "lxml")
    assert with_tbody.select(loc)[0].get_text() == "b"


def test_euc_kr_decode():
    from iad.crawler import decode_html

    class R:  # noqa: D401
        content = "<html><head><meta charset=euc-kr></head><body>고수익알바</body></html>".encode("cp949")
        headers = {"content-type": "text/html"}
    txt, enc = decode_html(R())
    assert "고수익알바" in txt and enc == "cp949"


# ---------- G0: 외부 CSS·캐스케이드·새 offscreen/투명 패턴 ----------
@pytest.mark.parametrize("style,tech", [
    ("position:absolute;transform:translateX(-9999px)", "offscreen"), ("transform:translate(-50%, -12000px)", "offscreen"),
    ("position:relative;margin-left:-9999px", "offscreen"), ("margin:0 0 0 -9999px", "offscreen"),
    ("position:fixed;inset:-9999px auto auto 0", "offscreen"), ("text-indent:-100em", "offscreen"),
    ("color:rgba(0,0,0,0)", "color_match"), ("color:rgba(255, 255, 255, 0.03)", "color_match"),
    ("color:hsla(0,0%,100%,1)", "color_match"), ("color:#00000000", "color_match"), ("color:#fdfdfd", "color_match"),
    ("color:rgb(255 255 255 / 0)", "color_match"), ("opacity:0%", "opacity_zero"), ("font:0px/1 sans-serif", "font_size_zero"),
])
def test_hidden_new_patterns(style, tech):
    soup = BeautifulSoup(f'<html><body><span style="{style}">x</span></body></html>', "lxml")
    assert tech in [t for t, _ in H.hidden_techniques(soup.find("span"), {})]


@pytest.mark.parametrize("style", [
    "color:#999", "color:#e0e0e0", "transform:translate(-50%,-50%)", "margin-left:-20px", "left:-9999px",  # position 없음 (#f0f0f0 은 고명도 허용폭 18 안이라 의도적 매치)
    "text-indent:-50%", "opacity:0.5", "font-size:1.2px",
])
def test_hidden_negative_patterns(style):
    soup = BeautifulSoup(f'<html><body><span style="{style}">x</span></body></html>', "lxml")
    assert not H.hidden_techniques(soup.find("span"), {})


def test_background_image_unknown_and_bgcolor_attr():
    html = ('<html><body><div style="background:url(dark.png) no-repeat"><span style="color:#fff">a</span></div>'
            '<table bgcolor="#000"><tr><td><span style="color:#000">b</span></td></tr></table>'
            '<div style="background:#000 url(x.png)"><span style="color:#000">c</span></div></body></html>')
    soup = BeautifulSoup(html, "lxml")
    spans = soup.find_all("span")
    assert not H.hidden_techniques(spans[0], {})          # 배경 이미지 → 색 비교 불가 → 보고 안 함
    assert "color_match" in [t for t, _ in H.hidden_techniques(spans[1], {})]
    assert "color_match" in [t for t, _ in H.hidden_techniques(spans[2], {})]


def test_sheet_cascade_media_and_external_css():
    css = ("@media print{.np{display:none}} .a{display:none} .a.on{display:block} #x{display:none !important}"
           ".b{color:#fff} div.b{color:#000} @font-face{font-family:x;src:url(a.woff)} .c{left:-9999px;position:absolute}")
    html = ('<html><head><style>.c{position:static}</style></head><body><p class="np">p</p><div class="a on">a</div>'
            '<div id="x" style="display:block">x</div><div class="b">b</div><span class="c">c</span></body></html>')
    soup = BeautifulSoup(html, "lxml")
    sheet = H.apply_sheet(soup, H.sheet_rules(soup, [css]))
    assert not H.hidden_techniques(soup.find("p"), sheet)                                  # print 전용 무시
    assert not H.hidden_techniques(soup.find("div", class_="a"), sheet)                    # 명시도 .a.on > .a
    assert "display_none" in [t for t, _ in H.hidden_techniques(soup.find(id="x"), sheet)]  # !important > 인라인
    assert not H.hidden_techniques(soup.find("div", class_="b"), sheet)                    # div.b(#000) > .b(#fff)
    assert not H.hidden_techniques(soup.find("span"), sheet)                               # 문서 <style> 이 외부 CSS 뒤 → static


@pytest.mark.parametrize("html,code", [
    ('<div class="notice-board"><span class="visually-hidden" style="display:none">ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드 LUCKY7</span></div>', "JAMO"),
    ('<div class="notice-board"><span class="visually-hidden" style="display:none">ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드 LUCKY7</span></div>', "OFFSCREEN"),
    ('<div class="board-list"><table><tr><td class="title"><a href="#">ｍｅｇａ－ＢＥＴ 첫충 30％ 지급</a></td></tr></table></div>', "HOMOGLYPH"),
    ('<div class="article-body"><p class="desc"><span style="color:#fff">먹튀검증 안전놀이터 상담 텔레그램 @promo_777</span></p></div>', "TRANSPARENT"),
    ('<div class="wrap"><span class="hidden-link" style="position:absolute;left:-9999px">무료 슬롯 체험 바로가기</span></div>', "OFFSCREEN"),
    ('<div class="wrap"><span class="hidden-link" style="font-size:0">무료 슬롯 체험 바로가기</span></div>', "OFFSCREEN"),
])
def test_spec_examples(html, code):
    """요강 붙임4 예시 evidence_text 를 그대로 넣었을 때 해당 코드가 나와야 한다."""
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert code in {c for f in fs for c in f.official}, [(f.location, f.official) for f in fs]


def test_crawler_collects_same_site_css(tmp_path):
    from iad.crawler import Crawler, CrawlConfig
    c = Crawler("http://ex.go.kr/a.html", CrawlConfig(allowed_hosts=()))   # 네트워크 차단
    c.css_cache["http://ex.go.kr/s.css"] = ".h{display:none}"
    soup = BeautifulSoup('<html><head><link rel="stylesheet" href="/s.css"><link rel="stylesheet" href="http://cdn.x.com/b.css"></head></html>', "lxml")
    assert c.stylesheets(Page(url="http://ex.go.kr/a.html", html=""), soup) == [".h{display:none}"]


# ---------- AR2: 행정 문맥 화이트리스트 / 접근성 숨김 ----------
@pytest.mark.parametrize("html", [
    '<p>불법 토토사이트 광고 집중 단속 결과 32건 적발, 운영자 검거</p>',
    '<td>온라인 카지노사이트 접속 차단 및 도박 중독 예방 교육 실시</td>',
    '<p>출장안마 등 성매매 알선 광고 신고는 112, 피해 상담 1366</p>',
    '<a class="skip-nav" style="position:absolute;left:-9999px" href="#content">본문 바로가기</a>',
    '<span class="blind">새 창 열림 <a href="https://www.gov.kr">정부24</a></span>',
    '<p class="sr-only" style="position:absolute;left:-9999px">현재 페이지 <a href="https://www.mois.go.kr">행정안전부</a></p>',
])
def test_admin_context_and_a11y_hidden_not_reported(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><head><style>.blind{{position:absolute;left:-9999px}}</style></head><body>{html}</body></html>"), "ex.go.kr")
    assert not fs, [(f.location, f.official, f.extra_names, f.score) for f in fs]


@pytest.mark.parametrize("html,code", [
    ('<p>ㅌㅗㅌㅗ ㅅㅏㅇㅣㅌㅡ 추천 (예방 단속 신고 안내 아님)</p>', "JAMO"),          # 난독화는 행정 문맥으로 면제 안 됨
    ('<p>단속 안내: <span style="display:none">토토사이트 안전놀이터 가입코드</span></p>', "OFFSCREEN"),   # 은닉은 면제 안 됨
])
def test_admin_context_does_not_excuse_obfuscation_or_hiding(html, code):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert code in {c for f in fs for c in f.official}


def test_admin_context_keeps_suspicious_link():
    html = '<p>불법 도박 단속 안내 <a href="http://kk8282.top">토토사이트 안전놀이터 바로가기</a></p>'
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert any("SUSPICIOUS_TLD" in n or "suspicious_tld" in n for f in fs for n in f.extra_names), fs


# ---------- AR3: 스크립트 디코딩 재분석 ----------
def _cc(s: str) -> str:
    return "String.fromCharCode(" + ",".join(str(ord(c)) for c in s) + ")"


@pytest.mark.parametrize("script", [
    "document.body.innerHTML+=" + _cc('<a href="http://casino-vip.top">온라인 카지노 바카라</a>') + ";",
    'var h="\\x3c\\x61\\x20\\x68\\x72\\x65\\x66\\x3d\\x22http://slot-77.xyz\\x22\\x3e슬롯사이트 꽁머니\\x3c\\x2f\\x61\\x3e";document.write(h);',
    'eval(unescape("%3Ca%20href%3D%22http%3A%2F%2Fbet-99.top%22%3E%ED%86%A0%ED%86%A0%EC%82%AC%EC%9D%B4%ED%8A%B8%3C%2Fa%3E"));',
    'var s=atob("' + __import__("base64").b64encode(__import__("base64").b64encode('<a href="http://go-casino.top">토토사이트 추천</a>'.encode())).decode() + '");eval(atob(s));',  # base64 2겹
    'var p=["htt","p://","kk8","282",".top","/토토사이트"].join("");location.href=p;',
])
def test_script_decoding_layers(script):
    from iad.scripts import analyze_script
    rules, extra = analyze_script(script, "ex.go.kr")
    names = {r for r, _, _ in rules}
    assert names & {"script.encoded", "script.base64", "script.document_write", "script.innerhtml", "script.js_redirect"}, rules
    assert "토토" in extra or "카지노" in extra or "슬롯" in extra or "kk8282" in extra, extra


def test_script_decoded_finding_has_keyword_and_link():
    html = "<html><body><script>document.body.innerHTML+=" + _cc('<a href="http://casino-vip.top">온라인 카지노 바카라</a>') + ";</script></body></html>"
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=html), "ex.go.kr")
    assert fs and "SCRIPT_DECODED" in fs[0].extra_names and fs[0].category == "도박" and any("casino-vip.top" in l for l in fs[0].links)


# ---------- AR1: 클로킹 ----------
def test_cloaking_detects_bot_only_content_and_redirect():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from iad.cloak import check_cloaking
    from iad.crawler import Crawler, CrawlConfig

    NORMAL = "<html><body><p>정상 공지</p></body></html>"
    BOT = '<html><body><p>정상 공지</p><div style="display:none"><a href="http://bet-1.top">토토사이트</a> 안전놀이터</div></body></html>'

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D102
            pass

        def do_GET(self):
            bot = "Yeti" in self.headers.get("User-Agent", "") or "Googlebot" in self.headers.get("User-Agent", "")
            if self.path == "/r.html" and bot:
                self.send_response(302)
                self.send_header("Location", "http://go-casino.top/")
                self.end_headers()
                return
            body = (BOT if bot and self.path == "/a.html" else NORMAL).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        c = Crawler(base + "/a.html", CrawlConfig(delay=0, allowed_hosts=("127.0.0.1",)))
        import time
        c.started = time.monotonic()
        pages = [Page(url=base + "/a.html", html=NORMAL), Page(url=base + "/r.html", html=NORMAL, depth=1)]
        fs = check_cloaking(c, pages, [], "127.0.0.1", 10, lambda m: None)
    finally:
        srv.shutdown()
    names = {n for f in fs for n in f.extra_names}
    assert "CLOAKING_OFFSCREEN" in names and "CLOAKING_REDIRECT" in names, names
    assert all(not f.official for f in fs)   # 봇 전용 DOM 은 result.json 에 넣지 않는다


# ---------- 탐색 커버리지 ----------
def test_crawler_link_extraction_and_priority():
    from iad.crawler import Crawler, CrawlConfig
    c = Crawler("http://ex.go.kr/board/list.do?bbsId=B1", CrawlConfig(allowed_hosts=()))
    html = '''<html><head><link rel="next" href="/board/list.do?bbsId=B1&pageIndex=2"></head><body>
    <a href="javascript:fn_view('123')" onclick="location.href='/board/view.do?nttId=123';return false;">글</a>
    <a href="#none" onclick="window.open('/board/view.do?nttId=124')">글2</a>
    <tr data-href="/board/view.do?nttId=125"></tr>
    <a href="/member/login.do">로그인</a><a href="/board/download.do?f=1">첨부</a><a href="/blueprint/plan.html">계획</a>
    <a href="/about/print.do">인쇄</a><a href="/board/view.do?nttId=1&mode=download">다운</a>
    <script>function cm(){ $.get("/board/comment/list.do?nttId=123"); }</script>
    <a href="/intro/greeting.do">인사말</a></body></html>'''
    soup = BeautifulSoup(html, "lxml")
    links = list(c.extract_links(Page(url="http://ex.go.kr/board/list.do?bbsId=B1", html=html), soup))
    assert "http://ex.go.kr/board/view.do?nttId=123" in links and "http://ex.go.kr/board/view.do?nttId=124" in links
    assert "http://ex.go.kr/board/view.do?nttId=125" in links and "http://ex.go.kr/board/comment/list.do?nttId=123" in links
    assert "http://ex.go.kr/board/list.do?bbsId=B1&pageIndex=2" in links
    assert c._skip_link("http://ex.go.kr/member/login.do") and c._skip_link("http://ex.go.kr/board/download.do?f=1")
    assert c._skip_link("http://ex.go.kr/about/print.do") and c._skip_link("http://ex.go.kr/board/view.do?nttId=1&mode=download")
    assert not c._skip_link("http://ex.go.kr/blueprint/plan.html")   # 'print' 부분 문자열로 건너뛰면 안 됨
    pr = c._priority
    d = "/board/"
    assert pr("http://ex.go.kr/board/view.do?nttId=123", d) < pr("http://ex.go.kr/board/list.do?pageIndex=2", d) \
        < pr("http://ex.go.kr/board/etc.do", d) < pr("http://ex.go.kr/news/view.do?id=3", d) < pr("http://ex.go.kr/intro/greeting.do", d)


def test_crawler_lazy_iframe_data_src():
    from iad.crawler import Crawler, CrawlConfig
    c = Crawler("http://ex.go.kr/a.html", CrawlConfig(allowed_hosts=()))
    soup = BeautifulSoup('<html><body><iframe data-src="/w/x.html"></iframe><iframe src="about:blank" data-src="w/y.html"></iframe></body></html>', "lxml")
    srcs = [u for u, _ in c.extract_frames(Page(url="http://ex.go.kr/a.html", html=""), soup)]
    assert srcs == ["http://ex.go.kr/w/x.html", "http://ex.go.kr/w/y.html"]


# ---------- AR5: --demo ----------
def test_demo_runs_offline(tmp_path):
    from iad.demo import run_demo
    logs: list[str] = []
    res = run_demo(log=logs.append, result_dir=tmp_path, open_browser=False)
    assert (tmp_path / "result.json").is_file() and (tmp_path / "report.html").is_file()
    off = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))["findings"]
    assert len(off) >= 30 and res.pages
    assert all(f["url"].startswith("http://127.0.0.1:") for f in off)


# ---------- AR4: 작업지시서 보강 ----------
def test_triage_enrichment_and_report_files(tmp_path):
    from iad.triage import area_of, defang, enrich, fingerprint, priority_of
    from iad.report import write_reports
    html = ('<html><body><div class="article-body"><p><span style="display:none">토토사이트 안전놀이터 http://kk8282.top/x</span></p></div>'
            '<ul class="comments"><li class="comment"><span style="color:#fff">먹튀검증 텔레그램 @x</span></li></ul></body></html>')
    fs = analyze_page(Page(url="http://ex.go.kr/board/view?id=1", html=html), "ex.go.kr")
    assert fs
    areas = {area_of(f) for f in fs}
    assert "게시글 본문" in areas and "댓글" in areas
    assert defang("http://kk8282.top/x?a=1") == "hxxp://kk8282[.]top/x?a=1"
    assert all(len(fingerprint(f)) == 64 for f in fs)
    assert {priority_of(f) for f in fs} <= {"긴급", "높음", "보통"}
    e = enrich(fs[0])
    assert e["guide"] and e["contact"] and e["defanged_url"].startswith("hxxp://")

    from datetime import datetime
    from iad.official import KST

    class R:  # 최소 ScanResult 흉내
        entry_url = "http://ex.go.kr/board/list"
        started = finished = datetime.now(KST)
        elapsed = 0.0
        pages = [Page(url="http://ex.go.kr/board/view?id=1", html=html)]
        findings = fs
        stopped_reason = ""
        render_used = False

    out = write_reports(R(), tmp_path)
    text = out.read_text(encoding="utf-8")
    assert "작업지시서" in text and "fingerprint" in text and "hxxp://" in text
    rows = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["findings"]
    assert rows[0]["area"] and rows[0]["guide"] and rows[0]["fingerprint"]
    csv_head = (tmp_path / "report.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert "조치요약" in csv_head and "지문(SHA-256)" in csv_head


def test_large_stylesheet_is_fast_and_correct():
    import time
    css = "\n".join(f".c{i}{{padding:{i % 9}px;margin:{i % 5}px;font-weight:400;color:#333}}" for i in range(5000))
    css += "\n.hide{display:none}\n.a.on{display:block}\n.a{display:none}\n"
    html = '<html><body>' + "".join(f'<p class="c{i}">t</p>' for i in range(300)) + '<span class="hide">x</span><div class="a on">y</div></body></html>'
    soup = BeautifulSoup(html, "lxml")
    t0 = time.monotonic()
    sheet = H.apply_sheet(soup, H.sheet_rules(soup, [css]))
    assert time.monotonic() - t0 < 0.5
    assert "display_none" in [t for t, _ in H.hidden_techniques(soup.find("span"), sheet)]
    assert not H.hidden_techniques(soup.find("div"), sheet)


# ---------- AR6: 레드팀 R1 약점(font-size 0%·초성 축약·단독 유사문자) ----------
@pytest.mark.parametrize("html,want", [
    ('<span style="font-size:0%">토토사이트 추천</span>', "OFFSCREEN"), ('<span style="font:0/0 a">토토사이트 추천</span>', "OFFSCREEN"),
    ('<span style="font-size:5%">토토사이트 추천</span>', "OFFSCREEN"),
    ('<p>ㅌㅌ 사이트 추천</p>', "JAMO"), ('<p>ㅋㅈㄴ 보너스 코드</p>', "JAMO"), ('<p>ㅂㅋㄹ 추천</p>', "JAMO"),
    ('<p>ㅇㅈㄴㅇㅌ 가입</p>', "JAMO"), ('<p>ㅁㅌㄱㅈ 완료</p>', "JAMO"), ('<p>ㅋㅈㄴ</p>', "JAMO"),
    ('<p>саsino 추천</p>', "HOMOGLYPH"), ('<p>т0т0 사이트</p>', "HOMOGLYPH"), ('<p>cas1no 입장</p>', "HOMOGLYPH"),
    ('<p>βaccarat</p>', "HOMOGLYPH"), ('<p>ｂet365 입장</p>', "HOMOGLYPH"), ('<p>ѕlоt 머신</p>', "HOMOGLYPH"), ('<p>s1ot 머신</p>', "HOMOGLYPH"),
])
def test_r1_weak_categories_detected(html, want):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert want in {c for f in fs for c in f.official}, [(f.location, f.official) for f in fs]


@pytest.mark.parametrize("html", [
    '<span style="font-size:80%">토토사이트 광고 신고 안내 단속</span>', '<p>ㅌㅌ 재밌다</p>', '<p>ㅋㅋㅋ ㅎㅎ ㄱㄱ ㅊㅊ 감사</p>',
    '<p>한글 자음: ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ</p>', '<p>초성 퀴즈 3번: ㅋㅈㄴ (힌트: 도박장)</p>',
    '<p>Добро пожаловать в Москву</p>', '<p>Казино Москва 2026 туризм</p>', '<p>문의 02-7070-1234, 1577-0101</p>',
    '<p>time slot 10:00</p>', '<p>2026년 10월 1일 (３월부터)</p>', '<div style="display:none">Available slots: 10:00</div>',
])
def test_r1_hard_negatives(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert not any(f.official for f in fs), [(f.location, f.official) for f in fs]


def test_cloaking_runs_after_max_pages_reached():
    """크롤이 max_pages 로 끝나도(pages_fetched >= max_pages) 클로킹 점검은 시간 예산만 보고 계속 요청해야 한다."""
    import threading, time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from iad.cloak import check_cloaking
    from iad.crawler import Crawler, CrawlConfig
    hits = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D102
            pass

        def do_GET(self):
            hits.append(self.headers.get("User-Agent", ""))
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(b"<html><body><p>ok</p></body></html>")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        c = Crawler(base + "/a.html", CrawlConfig(delay=0, max_pages=1, allowed_hosts=("127.0.0.1",)))
        pages = list(c.crawl())
        assert c.pages_fetched >= 1 and not c._budget_left()
        n0 = len(hits)
        check_cloaking(c, pages, [], "127.0.0.1", 10, lambda m: None)
    finally:
        srv.shutdown()
    assert len(hits) - n0 >= 2 and any("Yeti" in u for u in hits)


# ---------- AR7: 평문 키워드 없는 유사문자 치환 단어(스크립트 혼용 1급 신호) ----------
@pytest.mark.parametrize("text", ["саѕіnо 입장", "bеt 365", "ѕlоtѕ", "wіn 보너스", "роkеr 룸", "ＴＯＴＯ 사이트", "ＢＥＴ 추천", "t0t0",
                                  "b3t 추천", "c@$ino", "Ꮯasino", "ꭲoto 사이트", "lоan 상담", "ｍｅｇａ－ＢＥＴ 첫충 30％"])
def test_mixed_script_homoglyph_detected(text):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body><p>{text}</p></body></html>"), "ex.go.kr")
    assert "HOMOGLYPH" in {c for f in fs for c in f.official}, text


@pytest.mark.parametrize("text", ["ＷＩＮ－ＷＩＮ 협약 체결", "ＴＶ 방송 ＰＣ 지원", "covid19 안내", "Казино Москва закрыто", "Добро пожаловать",
                                  "iPhone 15 Pro", "win10 설치", "카지노 bar 안내", "Ｗｉｎｄｏｗｓ 업데이트", "α-test 결과", "β버전 출시",
                                  "alphabet song", "sports day 2026", "Tibet trip"])
def test_mixed_script_hard_negatives(text):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body><p>{text}</p></body></html>"), "ex.go.kr")
    assert not any(f.official for f in fs), [(f.location, f.official) for f in fs]


# ---------- AR7: 겹침 이중 보고 ----------
def test_overlap_reporting_rules():
    html = ('<html><body>'
            '<span class="a" style="display:none;color:#fff">토토사이트 안전놀이터</span>'                  # 은닉끼리 겹침 → OFFSCREEN 하나만
            '<span class="b" style="opacity:0;position:absolute;left:-9999px">바카라 온라인카지노</span>'   # → OFFSCREEN(지배)
            '<span class="c" style="color:#fff">ㅌㅗㅌㅗ ㅅㅏㅇㅣㅌㅡ 가입코드 777</span>'                 # 은닉 + 난독화 → 둘 다
            '<span class="d" style="display:none">ｃａｓｉｎｏ 바카라 보증업체</span>'                     # 은닉 + 난독화 → 둘 다
            '</body></html>')
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=html), "ex.go.kr")
    by = {f.location: set(f.official) for f in fs if f.official}
    assert by["span.a"] == {"OFFSCREEN"} and by["span.b"] == {"OFFSCREEN"}
    assert by["span.c"] == {"TRANSPARENT", "JAMO"} and by["span.d"] == {"OFFSCREEN", "HOMOGLYPH"}
    off = build_official(fs)
    units = {(o["location"], o["technique"]) for o in off}
    assert ("span.c", "TRANSPARENT") in units and ("span.c", "JAMO") in units and len(off) == 6


# ---------- AR9: OFFSCREEN 일반형 ----------
@pytest.mark.parametrize("html,code", [
    ('<span style="position:absolute;left:12000px">토토사이트 추천</span>', "OFFSCREEN"),
    ('<span style="position:fixed;top:99999px">토토사이트 추천</span>', "OFFSCREEN"),
    ('<div style="overflow:hidden;height:100px;position:relative"><p style="position:absolute;top:300px">토토사이트 추천</p></div>', "OFFSCREEN"),
    ('<span style="position:absolute;clip-path:inset(100%)">토토사이트 추천</span>', "OFFSCREEN"),
    ('<span style="position:absolute;clip:rect(0,0,0,0)">토토사이트 추천</span>', "OFFSCREEN"),
    ('<span style="position:absolute;width:1px;height:1px;overflow:hidden">토토사이트 추천</span>', "OFFSCREEN"),
    ('<div style="transform:scale(0)">토토사이트 추천</div>', "OFFSCREEN"),
    ('<div style="max-height:0;overflow:hidden">토토사이트 추천</div>', "OFFSCREEN"),
    ('<div hidden>토토사이트 추천</div>', "OFFSCREEN"),
    ('<style>.pos{position:absolute}.far{left:-9999px}</style><span class="pos far">토토사이트 추천</span>', "OFFSCREEN"),
])
def test_offscreen_general_forms(html, code):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert code in {c for f in fs for c in f.official}, [(f.location, f.official) for f in fs]


@pytest.mark.parametrize("html", [
    '<span style="position:absolute;left:300px">토토사이트 광고 단속 안내</span>',                       # 화면 안
    '<div style="overflow:hidden;height:500px;position:relative"><p style="position:absolute;top:100px">토토사이트 단속 안내</p></div>',
    '<div style="max-height:0;overflow:hidden"><p>대관료: 시간당 2만원</p></div>',
    '<span class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden">본문 바로가기</span>',
    '<div hidden><a href="/about">기관소개</a></div>',
])
def test_offscreen_general_hard_negatives(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert not any(f.official for f in fs), [(f.location, f.official) for f in fs]



# ---------- B1: 같은 요소의 color = 자기 background (클래스 규칙·외부 CSS·단축 속성) ----------
@pytest.mark.parametrize("css,cls", [
    (".x{color:#ffffff;background:#ffffff}", "x"), (".x{color:#FFF;background-color:#FFF}", "x"), (".x{color:white;background:white}", "x"),
    (".x{color:#000;background:#000 none repeat scroll 0 0}", "x"), (".x{color:rgb(255,255,255);background:rgb(255, 255, 255) url(a.png)}", "x"),
    (".x{color:#eee}.x{background:#eee}", "x"), ("p.x{color:#fff !important}.x{background:#fff}", "x"),
    ("@media screen{.x{color:#ffffff;background:#ffffff}}", "x"), (".x{color:#ffffff;background:#ffffff}", "x y"),
])
def test_transparent_same_element_background(css, cls):
    html = f'<html><head><style>{css}</style></head><body><div style="background:#222"><p class="{cls}">토토사이트 안전놀이터</p></div></body></html>'
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=html), "ex.go.kr")
    assert any("TRANSPARENT" in f.official and f.location.startswith("div > p.x") for f in fs), [(f.location, f.official) for f in fs]


def test_transparent_external_css_end_to_end(tmp_path):
    """외부 CSS(localhost 절대 경로 href 포함)로 color=background 를 준 요소가 TRANSPARENT 로 나와야 한다."""
    from iad.testbed import pick_port, serve
    from iad.crawler import CrawlConfig
    from iad.scan import scan
    port = pick_port(0)
    (tmp_path / "s.css").write_text(".x{color:#ffffff;background:#ffffff}\n")
    (tmp_path / "index.html").write_text(f'<html><head><meta charset="utf-8"><link rel="stylesheet" href="http://localhost:{port}/s.css"></head>'
                                         f'<body><p class="x">토토사이트 안전놀이터</p></body></html>', encoding="utf-8")
    srv = serve(tmp_path, port)
    try:
        res = scan(f"http://127.0.0.1:{port}/index.html", CrawlConfig(delay=0, allowed_hosts=("127.0.0.1", "localhost"), cloak_pages=0),
                   out_dir=tmp_path / "out", result_dir=tmp_path / "out", log=lambda m: None, write_report=False)
    finally:
        srv.shutdown()
    assert any("TRANSPARENT" in f.official and f.location == "p.x" for f in res.findings), [(f.location, f.official) for f in res.findings]



# ---------- B2: 숨김(외부 CSS 클래스) + 자모 분해 → OFFSCREEN 과 JAMO 두 finding, 같은 location ----------
@pytest.mark.parametrize("html", [
    '<style>.h-dn{display:none}</style><p class="h-dn">ㅂㅏㅋㅏㄹㅏ ㅌㅗㅌㅗ</p>',
    '<style>.h-dn{display:none}</style><p class="h-dn"><b>ㅂㅏㅋㅏㄹㅏ ㅌㅗㅌㅗ</b> 추천</p>',
    '<p class="h-dn" style="position:absolute;left:-9999px">정상 안내 <span>ㅂㅏㅋㅏㄹㅏ ㅌㅗㅌㅗ</span></p>',
    '<style>.h-dn{display:none}</style><p class="h-dn">ｃａｓｉｎｏ 바카라 보증업체</p>',
])
def test_hidden_plus_obfuscation_double_finding_same_location(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    by = {f.location: set(f.official) for f in fs if f.official}
    assert list(by) == ["p.h-dn"], by
    codes = by["p.h-dn"]
    assert "OFFSCREEN" in codes and (codes & {"JAMO", "HOMOGLYPH"}), codes
    units = {(o["location"], o["technique"]) for o in build_official(fs)}
    assert len(units) == 2 and all(loc == "p.h-dn" for loc, _ in units)



# ---------- B3: 첫가끝 조합형(NFD) 한글 키워드는 JAMO ----------
def test_nfd_conjoining_jamo_is_jamo_not_homoglyph():
    import unicodedata
    nfd = unicodedata.normalize("NFD", "카지노 바카라")
    assert nfd != "카지노 바카라" and all(0x1100 <= ord(c) <= 0x11FF for c in nfd.replace(" ", ""))
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body><p>안내 {nfd} 추천 코드</p></body></html>"), "ex.go.kr")
    codes = {c for f in fs for c in f.official}
    assert codes == {"JAMO"}, [(f.location, f.official) for f in fs]
    hidden = analyze_page(Page(url="http://ex.go.kr/p", html=f'<html><body><h1>행복시청 공지사항</h1><p>정상 안내문입니다.</p><p style="display:none">{unicodedata.normalize("NFD", "토토사이트 추천")}</p></body></html>'), "ex.go.kr")
    assert {c for f in hidden for c in f.official} == {"OFFSCREEN", "JAMO"}
    assert match_keywords_levels(unicodedata.normalize("NFD", "카지노"))["gambling"][0][2] == "JAMO"


def test_nfd_whole_page_is_encoding_not_obfuscation():
    import unicodedata
    page = unicodedata.normalize("NFD", "<html><body><h1>행복시청 공지</h1><p>도박 중독 예방 상담 1336 안내문입니다.</p><p>불법 토토사이트 광고 단속 결과</p></body></html>")
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=page), "ex.go.kr")
    assert not any(f.official for f in fs), [(f.location, f.official) for f in fs]



# ---------- B4: IDN 호모그래프 도메인 ----------
def test_idn_homograph_rules():
    from iad.links import is_idn_homograph
    assert is_idn_homograph("ѕо.invalid") and is_idn_homograph("βο.invalid") and is_idn_homograph("www.саsino-vip.com")
    assert is_idn_homograph("xn--80ak6aa92e.com")          # аррӏе.com
    assert not is_idn_homograph("москва.рф") and not is_idn_homograph("행복시.한국") and not is_idn_homograph("παράδειγμα.ελ")
    assert not is_idn_homograph("kk8282.top") and not is_idn_homograph("www.mois.go.kr")


@pytest.mark.parametrize("html,loc", [
    ('<p>토토사이트 추천 <a href="http://ѕо.invalid/x">바로가기</a></p>', "p > a"),
    ('<p style="display:none">안전놀이터 βο.invalid</p>', "p"),
    ('<p>카지노 <a href="http://www.саsino-vip.com">입장</a></p>', "p > a"),
    ('<div style="display:none"><a href="http://ѕо.invalid">바카라</a></div>', "div"),
])
def test_idn_homograph_is_homoglyph(html, loc):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert any(f.location == loc and "HOMOGLYPH" in f.official for f in fs), [(f.location, f.official) for f in fs]


@pytest.mark.parametrize("html", [
    '<p>토토사이트 단속 <a href="http://москва.рф">모스크바시</a></p>', '<p>한글도메인 <a href="http://행복시.한국">행복시</a> 안내</p>',
    '<p>자매도시 <a href="http://москва.рф">Москва</a></p>', '<p>국제교류 <a href="http://ѕо.invalid">자매도시</a></p>',   # 키워드 없음
])
def test_idn_homograph_negatives(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert not any("HOMOGLYPH" in f.official for f in fs), [(f.location, f.official) for f in fs]


# ---------- B5: 텍스트 없는 이미지 배너 광고 ----------
def test_random_and_rotating_domain_rules():
    from iad.links import random_label_rule
    assert random_label_rule("k3j9x0qpa7zmv2lsd8ygh4bnt1w")[0] == "link.random_domain"
    assert random_label_rule("qzxkvbnmptrw")[0] == "link.random_domain"
    assert random_label_rule("iabn101")[0] == "link.rotating_domain" and random_label_rule("nicelink22")[0] == "link.rotating_domain"
    for ok in ("happycity-partner", "visitkorea", "naver", "samsung", "kookmin", "seoulculture", "koreaexim"):
        assert random_label_rule(ok) is None, ok


@pytest.mark.parametrize("html", [
    '<a href="https://k3j9x0qpa7zmv2lsd8ygh4bnt1w.invalid/x"><img alt="배너광고" src="b.png"></a>',
    '<a href="https://iabn101.invalid/"><img alt="" src="b.png"></a>',
    '<a href="https://t.me/free_toto"><img alt="이벤트" src="b.png"></a>',
    '<a href="https://some-partner.invalid/" style="background-image:url(b.png)" title="바카라 이벤트 광고"></a>',
    '<a href="https://nicelink22.invalid/"><img alt="바로가기" src="b.png"></a>',
])
def test_image_banner_ad_detected(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert any("IMAGE_BANNER_AD" in f.extra_names for f in fs), [(f.location, f.extra_names, f.score) for f in fs]
    assert not any(f.official for f in fs)   # result.json 4종에는 안 넣는다


@pytest.mark.parametrize("html", [
    '<a href="https://www.gov.kr"><img alt="정부24 배너" src="b.png"></a>',
    '<a href="https://www.mois.go.kr"><img alt="행정안전부 광고" src="b.png"></a>',
    '<a href="/event/2026"><img alt="가을 축제 이벤트 배너" src="b.png"></a>',
    '<a href="https://www.happycity-partner.com/"><img alt="행복시 문화재단 홈페이지" src="b.png"></a>',
    '<a href="https://www.visitkorea.or.kr/"><img alt="한국관광공사 배너" src="b.png"></a>',
    '<a href="https://www.samsungfoundation.org/"><img alt="재단 홈페이지" src="b.png"></a>',
])
def test_image_banner_normal_not_reported(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert not fs, [(f.location, f.extra_names, f.score) for f in fs]


# ---------- B6: 요소 자신의 background = color (외부 CSS) + 약한 키워드 2개 ----------
def test_self_background_transparent_with_weak_keyword_pair():
    from iad.crawler import Crawler, CrawlConfig
    c = Crawler("http://ex.go.kr/board/view", CrawlConfig(allowed_hosts=()))
    c.css_cache["http://ex.go.kr/assets/board.css"] = ".t-same{color:#ffffff;background:#ffffff;}"
    html = '<html><head><link rel=stylesheet href=/assets/board.css></head><body><div class="article-body"><p>공고합니다.</p><span class="leak-t1 t-same">슬롯 카지노</span></div></body></html>'
    page = Page(url="http://ex.go.kr/board/view", html=html)
    page.css_texts = c.stylesheets(page, BeautifulSoup(html, "lxml"))
    fs = analyze_page(page, "ex.go.kr")
    hit = [f for f in fs if "TRANSPARENT" in f.official]
    assert hit and hit[0].location == "div.article-body > span.leak-t1.t-same", [(f.location, f.official, f.extra_names) for f in fs]
    assert any(o["technique"] == "TRANSPARENT" for o in build_official(fs))


@pytest.mark.parametrize("html", [
    '<style>.t-same{color:#fff;background:#fff}</style><span class="t-same">문의 안내 02-000-0000</span>',       # 키워드 없음
    '<style>.t-same{color:#fff;background:#fff}</style><span class="t-same">강원랜드 카지노 관광 안내</span>',   # 약한 키워드 하나
    '<style>.btn{background:#1e4fa3;color:#fff}.btn:hover{background:#fff;color:#1e4fa3}</style><a class="btn" href="/x">슬롯 예약 카지노 관광</a>',  # 반전 hover 는 의사클래스
    '<div style="background:#fff"><p style="color:#222">슬롯 카지노 단속 안내</p></div>',                       # 흰 박스 안 일반 글자색
])
def test_self_background_negatives(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert not any(f.official for f in fs), [(f.location, f.official) for f in fs]


# ---------- 조정안 A: 은닉 + 중위 키워드 + 광고 유도 보조어 ----------
@pytest.mark.parametrize("html,code", [
    ('<span class="hidden-link" style="position:absolute;left:-9999px">무료 슬롯 체험 바로가기</span>', "OFFSCREEN"),
    ('<span style="display:none">슬롯 가입 쿠폰 지급</span>', "OFFSCREEN"),
    ('<span style="color:#fff">카지노 입장 코드 777</span>', "TRANSPARENT"),
    ('<span style="font-size:0">토토 추천 주소</span>', "OFFSCREEN"),
    ('<span style="opacity:0">포커 실시간 배당</span>', "TRANSPARENT"),
])
def test_inducement_gate_positive(html, code):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert code in {c for f in fs for c in f.official}, [(f.location, f.official, f.score) for f in fs]


@pytest.mark.parametrize("html", [
    '<div style="display:none">강원랜드 카지노 관광 안내</div>', '<div style="display:none">슬롯머신 규제 현황</div>',
    '<div style="display:none">카지노 체험 프로그램 안내 바로가기</div>', '<div style="display:none">카지노 관련 정책 토론회 참가 신청 바로가기</div>',
    '<a class="skip" style="position:absolute;left:-9999px" href="#c">본문 바로가기</a>', '<span style="display:none">주메뉴 바로가기</span>',
    '<div style="display:none">도박 예방 교육 무료 체험 프로그램 1336</div>', '<p>슬롯 가입 쿠폰 지급</p>',   # 평문은 게이트 대상 아님
])
def test_inducement_gate_negative(html):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert not any(f.official for f in fs), [(f.location, f.official, f.score) for f in fs]


# ---------- 조정안 B-②: 한글 음절 안 영문·숫자 시각 치환 ----------
@pytest.mark.parametrize("text", ["ㅋr지노 추천", "ㅂrㅋrㄹr 코드", "스ㅍ0츠토토 가입", "토Eㅗ 사이트 추천", "ㅌㅗEㅗ 추천", "카지L ㅗ 입장", "안전놀0ㅣ터 추천"])
def test_korean_leet_homoglyph(text):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body><p>{text}</p></body></html>"), "ex.go.kr")
    assert "HOMOGLYPH" in {c for f in fs for c in f.official}, (text, [(f.location, f.official) for f in fs])
    hits = match_keywords_levels(text)
    assert any(lv == "HOMOGLYPH" for hs in hits.values() for _, _, lv in hs)


@pytest.mark.parametrize("text", ["카카오TV 생중계", "e편한세상 입주 안내", "LG전자 서비스센터", "T맵 길안내", "Hi서울 페스티벌", "SK텔레콤 KT LGU+ 요금",
                                  "CJ대한통운 택배", "A형 독감 주의", "오늘의 TOP10 뉴스", "문의 02-7070-1234", "2026년 10월 1일", "COVID-19 예방접종"])
def test_korean_leet_negatives(text):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body><p>{text}</p></body></html>"), "ex.go.kr")
    assert not fs, (text, [(f.location, f.official, f.extra_names) for f in fs])


# ---------- 조정안 C: 오프셋 -300px·-100%, 고명도 배경 색차 18 ----------
@pytest.mark.parametrize("style,tech", [
    ("position:absolute;left:-300px", "offscreen"), ("text-indent:-300px", "offscreen"), ("text-indent:-100%", "offscreen"),
    ("position:absolute;left:-100%", "offscreen"), ("text-indent:-100vw", "offscreen"), ("position:relative;margin-left:-300px", "offscreen"),
    ("height:0;overflow:hidden", "tiny_size"), ("width:0;overflow:hidden", "tiny_size"), ("font-size:0.05rem", "font_size_zero"), ("font-size:0.5pt", "font_size_zero"),
])
def test_offscreen_thresholds_relaxed(style, tech):
    soup = BeautifulSoup(f'<html><body><span style="{style}">x</span></body></html>', "lxml")
    assert tech in [t for t, _ in H.hidden_techniques(soup.find("span"), {})]


@pytest.mark.parametrize("style", ["position:absolute;left:-200px", "text-indent:-50%", "position:absolute;left:-99%", "margin-left:-200px",
                                   "text-indent:-2em", "position:relative;top:-100px"])
def test_offscreen_thresholds_not_too_loose(style):
    soup = BeautifulSoup(f'<html><body><span style="{style}">x</span></body></html>', "lxml")
    assert not H.hidden_techniques(soup.find("span"), {})


def test_transparent_high_luminance_tolerance():
    assert H.colors_close("ffffff", "f0f0f0") and H.colors_close("fafafa", "ededed") and H.colors_close("000000", "121212")
    assert not H.colors_close("ffffff", "e0e0e0") and not H.colors_close("888888", "999999") and not H.colors_close("ffffff", "dddddd")
    html = '<table><tr><td style="background:#f0f0f0"><span>납부 안내</span><span style="color:#ffffff">안전놀이터 먹튀검증</span></td></tr></table>'
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert any("TRANSPARENT" in f.official for f in fs)
    neg = '<div style="background:#f0f0f0"><p style="color:#666">토토사이트 광고 단속 안내 1336</p><p style="color:#eee">회색 글씨 안내문</p></div>'
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{neg}</body></html>"), "ex.go.kr")
    assert not any(f.official for f in fs)


# ---------- COV2: POST 폼 게시판 재현 ----------
def test_extract_form_posts_patterns():
    from iad.crawler import Crawler, CrawlConfig
    c = Crawler("http://ex.go.kr/board/list.do", CrawlConfig(allowed_hosts=()))
    html = '''<html><body>
    <form name="frm" method="post" action="/board/view.do"><input type="hidden" name="nttId"><input type="hidden" name="bbsId" value="B01"></form>
    <form id="frm2" method="post" action="/cmt/list.do"><input type="hidden" name="seq"></form>
    <a href="#none" onclick="fn_egov_select_notice('1024'); return false;">글1</a>
    <a href="javascript:fn_egov_select_notice('1180')">글2</a>
    <a href="#" onclick="goCmt(77)">댓글</a>
    <a href="#" onclick="goView('55')">상세</a>
    <a href="#" onclick="alert('x')">무시</a>
    <script>
    function fn_egov_select_notice(nttId) { document.frm.nttId.value = nttId; document.frm.action = "/board/view.do"; document.frm.submit(); }
    function goCmt(seq) { $("#seq").val(seq); $("#frm2").submit(); }
    function goView(id) { location.href = "/news/view.do?id=" + id; }
    </script></body></html>'''
    soup = BeautifulSoup(html, "lxml")
    got = c.extract_form_posts(Page(url="http://ex.go.kr/board/list.do", html=html), soup)
    by = {d: (a, data, m) for d, a, data, m in got}
    assert by["http://ex.go.kr/board/view.do?nttId=1024"] == ("http://ex.go.kr/board/view.do", {"nttId": "1024", "bbsId": "B01"}, "post")
    assert "http://ex.go.kr/board/view.do?nttId=1180" in by
    assert by["http://ex.go.kr/cmt/list.do?seq=77"][1] == {"seq": "77"}
    assert by["http://ex.go.kr/news/view.do?id=55"] == ("http://ex.go.kr/news/view.do?id=55", {}, "get")
    assert len(got) == 4


def test_post_board_end_to_end(tmp_path):
    """onclick → hidden input → POST 로만 열리는 게시글의 은닉 광고를 수집·탐지하고 url 은 action?nttId=N 으로 적는다."""
    from iad.testbed import generate, pick_port, serve
    from iad.crawler import CrawlConfig
    from iad.scan import scan
    port = pick_port(0)
    generate(tmp_path, port)
    srv = serve(tmp_path, port)
    try:
        res = scan(f"http://127.0.0.1:{port}/dev/egov/list.do", CrawlConfig(delay=0, allowed_hosts=("127.0.0.1", "localhost"), cloak_pages=0, depth=2),
                   out_dir=tmp_path / "out", result_dir=tmp_path / "out", log=lambda m: None, write_report=False)
    finally:
        srv.shutdown()
    urls = {f.page_url for f in res.findings if f.official}
    assert f"http://127.0.0.1:{port}/dev/egov/view.do?nttId=3" in urls and f"http://127.0.0.1:{port}/dev/egov/view.do?nttId=5" in urls
    assert {c for f in res.findings for c in f.official} >= {"OFFSCREEN", "JAMO"}


# ---------- 아르곤 2차 검토 중 '이미 충족' 항목의 회귀 고정 ----------
@pytest.mark.parametrize("html,code", [
    ('<a href="/x">ｍｅｇａ－ＢＥＴ 신규 30％ 지급</a>', "HOMOGLYPH"), ('<a href="/x">ＶＩＰ－ＳＬＯＴ 가입 이벤트</a>', "HOMOGLYPH"),   # B-① 전각 영문 도박어
    ('<span>ㅋ ㅏ ㅈ ㅣ ㄴ ㅗ 보너스</span>', "JAMO"), ('<span class="blind">카ㅈㅣ노 보너스 바ㅋㅏ라 코드</span>', "JAMO"),          # #7 공백·혼합 자모
    ('<div class="article-body"><p>불법도박 예방 안내 1336</p><p>ｍｅｇａ－ＢＥＴ 카지노 쿠폰</p></div>', "HOMOGLYPH"),         # D/#10 이웃 문단 행정어
    ('<style>.article-body .blind-text{display:none}</style><div class="article-body"><p class="blind-text">토토사이트 추천</p></div>', "OFFSCREEN"),  # #8 후손 결합자
    ('<style>span[class*="hide"]{opacity:0}</style><span class="xhide">바카라 추천 코드</span>', "TRANSPARENT"),                     # #8 속성 부분일치
    ('<span style="display:inline-block;width:80px;overflow:hidden;text-indent:-300px">사설토토 첫충</span>', "OFFSCREEN"),           # #4
    ('<div style="height:0;overflow:hidden">불법 카지노 바카라</div>', "OFFSCREEN"), ('<span style="font-size:0.05rem">사설토토</span>', "OFFSCREEN"),  # #5
])
def test_argon_round2_already_covered(html, code):
    fs = analyze_page(Page(url="http://ex.go.kr/p", html=f"<html><body>{html}</body></html>"), "ex.go.kr")
    assert code in {c for f in fs for c in f.official}, [(f.location, f.official) for f in fs]


def test_spec_example_locations_reproduced():
    """요강 붙임4 예시 4건과 같은 DOM 에서 우리 location 이 예시 문자열과 같은 요소를 가리키는지(문자열 자체도 f_001·f_003·f_004 와 동일)."""
    html = ('<html><body><div class="notice-board"><p>공지</p><span class="visually-hidden" style="display:none">ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드 LUCKY7</span></div>'
            '<div class="article-body"><p class="desc">정상 <span style="color:#fff">먹튀검증 안전놀이터 상담 텔레그램 @promo_777</span></p></div>'
            '<div class="board-list"><table>' + "".join(f'<tr><td class="title"><a href="/v?id={i}">공지 {i}</a></td></tr>' for i in range(1, 7)) +
            '<tr><td class="title"><a href="/v?id=7">ｍｅｇａ－ＢＥＴ 첫충 30％ 지급</a></td></tr></table></div></body></html>')
    fs = analyze_page(Page(url="http://ex.go.kr/board/view?id=1024", html=html), "ex.go.kr")
    locs = {c: f.location for f in fs for c in f.official}
    assert locs["JAMO"] == "div.notice-board > span.visually-hidden" and locs["OFFSCREEN"] == "div.notice-board > span.visually-hidden"
    assert locs["TRANSPARENT"] == "div.article-body > p.desc > span"
    soup = BeautifulSoup(html, "lxml")
    # f_002 는 예시가 'div.board-list > tr:nth-child(7) > td.title > a' (table 생략·nth-child). 우리 선택자가 같은 a 를 가리켜야 한다.
    ours = soup.select(locs["HOMOGLYPH"])
    theirs = soup.select("div.board-list tr:nth-child(7) > td.title > a")
    assert len(ours) == 1 and ours == theirs
    assert "tbody" not in locs["HOMOGLYPH"]   # 브라우저 DOM(tbody 삽입)과 파서 DOM 양쪽에서 해석되게 table 과 tr 사이는 자손 결합자
    # f_004 iframe 접두어
    fr = analyze_page(Page(url="http://ex.go.kr/widget/notice", html='<html><body><div class="wrap"><span class="hidden-link" style="display:none">무료 슬롯 체험 바로가기</span></div></body></html>',
                           is_iframe=True, top_url="http://ex.go.kr/board/view?id=1180", frame_prefix='iframe[src="http://ex.go.kr/widget/notice"] >>> '), "ex.go.kr")
    assert [f.location for f in fr if f.official] == ['iframe[src="http://ex.go.kr/widget/notice"] >>> div.wrap > span.hidden-link']


# ---------- P0-1: 결과 파일 보장(중간 기록·종료 신호·시간 예산) ----------
def _slow_site(tmp_path, n=30, delay=0.4):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D102
            pass

        def do_GET(self):
            import time as _t
            _t.sleep(delay)
            i = int(self.path.rsplit("=", 1)[-1]) if "=" in self.path else 0
            links = "".join(f'<a href="/p?i={k}">글 {k}</a>' for k in range(1, n + 1))
            ad = '<span style="display:none">토토사이트 안전놀이터</span>' if i % 3 == 1 else ""
            body = f"<html><body><div class='b'>{links}{ad}</div></body></html>".encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_time_budget_stops_and_result_written(tmp_path):
    from iad.crawler import CrawlConfig
    from iad.scan import scan
    import time as _t
    srv = _slow_site(tmp_path)
    try:
        t0 = _t.monotonic()
        res = scan(f"http://127.0.0.1:{srv.server_port}/p?i=0", CrawlConfig(delay=0, allowed_hosts=("127.0.0.1",), cloak_pages=0, time_budget_sec=2.0, max_pages=100),
                   out_dir=tmp_path, result_dir=tmp_path, log=lambda m: None, write_report=False)
        elapsed = _t.monotonic() - t0
    finally:
        srv.shutdown()
    assert elapsed < 6 and "시간 예산" in res.stopped_reason
    data = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert data["meta"]["elapsed_sec"] >= 2 and data["findings"] and data["meta"]["finished_at"]


def test_sigterm_leaves_valid_result_files(tmp_path):
    """스캔 중 SIGTERM 으로 죽여도 result.json 이 유효 JSON 으로 남아야 한다(평가 30분 강제 종료 대비)."""
    import os, signal, subprocess, sys, time as _t
    srv = _slow_site(tmp_path, n=50, delay=0.5)
    code = f"""
import sys; sys.path.insert(0, {str(SRC)!r})
from iad.crawler import CrawlConfig
from iad.scan import scan
scan("http://127.0.0.1:{srv.server_port}/p?i=0", CrawlConfig(delay=0, allowed_hosts=("127.0.0.1",), cloak_pages=0, time_budget_sec=600, max_pages=500),
     out_dir={str(tmp_path)!r}, result_dir={str(tmp_path)!r}, log=lambda m: None, write_report=False)
"""
    try:
        proc = subprocess.Popen([sys.executable, "-c", code])
        _t.sleep(4)
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        srv.shutdown()
    for name in ("result.json", "result_extra.json"):
        data = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert set(data) == {"meta", "findings"} and data["meta"]["entry_url"].endswith("/p?i=0")
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))["findings"], "SIGTERM 전까지의 4종 검출이 기록되어야 함"
    assert not list(tmp_path.glob("result*.tmp*"))


# ---------- P0-3: 실사이트 잡음 ----------
@pytest.mark.parametrize("html", [
    '<form class="search"><input type="text" name="q" value="ѕо.invalid 토토"><input type="hidden" name="bbsId" value="B1"></form>',   # 폼 컨트롤
    '<div style="display:none"><ul class="lnb">' + "".join(f'<li><a href="/m{i}">메뉴{i}</a></li>' for i in range(12)) + '<li><a href="https://cloud.redwhistle.org/x">신고</a></li></ul></div>',  # 접힌 메뉴 + 외부 1개
    '<div><!-- [data-hwpjson]{ "documentPr": {"s1":"ot", "x": "야", "y": "한" } } --></div>',   # 에디터 메타데이터
    '<div><!-- 불법도박 신고 안내: 도박 광고 발견 시 1336 으로 신고하세요 --></div>',           # 행정 문맥 주석
    '<script>var menu=\'<a href="/sub/01">\' + encodeURIComponent("%ED%95%9C%EA%B8%80") + \'</a>\'; $("#gnb").html(menu); document.getElementById("x").innerHTML = menu;</script>',  # 정상 jQuery 템플릿
    '<script>var s = "%3Cdiv%20class%3D%22wrap%22%3E%ED%96%89%EC%A0%95%EC%95%88%EC%A0%84%EB%B6%80%3C%2Fdiv%3E"; document.write(unescape(s));</script>',  # 내부 UI 문자열 인코딩
])
def test_realworld_noise_not_reported(html):
    fs = analyze_page(Page(url="http://www.mois.go.kr/p", html=f"<html><body>{html}</body></html>"), "mois.go.kr")
    assert not fs, [(f.location, f.official, f.extra_names, f.score) for f in fs]


def test_realworld_set_passes():
    import eval as ev
    rw = ev.evaluate_realworld()
    assert rw is not None, "fixtures/realworld/manifest.json 없음"
    summary = ev.realworld_summary(rw)
    print(summary)
    assert not rw["official_fp"], "4종 오탐: " + summary
    assert rw["etc_count"] <= ev.RW_MAX_ETC, "ETC 상한 초과: " + summary
    assert rw["cpu_per_page"] <= ev.RW_MAX_CPU_PER_PAGE, "쪽당 CPU 초과: " + summary
    assert rw["pass"], summary


# ---------- P1-1: 정적 추가 신호(ETC 전용) ----------
def _etc(html, base="mois.go.kr"):
    fs = analyze_page(Page(url=f"http://www.{base}/p", html=html), base)
    assert all(not f.official for f in fs), [(f.location, f.official) for f in fs]
    return [n for f in fs for n in f.extra_names]


def test_head_keyword_injection_etc_only():
    assert "HEAD_KEYWORD_INJECTION" in _etc('<html><head><title>토토사이트 추천 안전놀이터 가입코드</title></head><body><p>공지</p></body></html>')
    assert "HEAD_KEYWORD_INJECTION" in _etc('<html><head><title>행정안전부</title><meta name="keywords" content="카지노사이트, 바카라사이트 추천, 슬롯 보너스 입금"></head><body><p>공지</p></body></html>')


@pytest.mark.parametrize("html", [
    '<html><head><title>불법도박 신고센터 안내 - 사행산업통합감독위원회</title><meta name="description" content="불법 도박 신고 및 단속 안내"></head><body><p>x</p></body></html>',
    '<html><head><title>행정안전부 공지사항</title><meta property="og:title" content="2026년 지방재정 공시"></head><body><p>x</p></body></html>',
])
def test_head_normal_not_reported(html):
    assert _etc(html) == []


def test_foreign_gambling_terms():
    assert "FOREIGN_GAMBLING" in _etc('<html><body><p>situs judi slot gacor togel maxwin hari ini</p></body></html>')
    assert _etc('<html><body><p>Judicial review of the prejudice standard; Togo delegation visit.</p></body></html>') == []
    assert _etc('<html><body><p>カジノ 관광 산업 동향 보고</p></body></html>') == []


def test_one_char_link():
    assert "ONE_CHAR_LINK" in _etc('<html><body><p>안내 <a href="http://kr-bet777.top/">.</a> 문의</p></body></html>')
    assert _etc('<html><body><p><a href="https://www.korea.kr/">›</a></p></body></html>') == []
    assert _etc('<html><body><p><a href="https://example.com/x">·</a></p></body></html>') == []


# ---------- P1-2: 브라우저 단계(Edge/Chrome headless --dump-dom, ETC 전용) ----------
_STATIC_INJECT = ('<html><head><meta charset="utf-8"></head><body><h1>공지사항</h1>'
                  '<script>document.write(atob("PGRpdiBzdHlsZT0iZGlzcGxheTpub25lIj48YSBocmVmPSJodHRwOi8va3ItYmV0Nzc3LnRvcCI+7Yag7Yag7IKs7J207Yq4IOy2lOyynCDslYjsoITrhoDsnbTthLA8L2E+PC9kaXY+"));</script>'
                  '</body></html>')
_INJECTED = '<div style="display:none"><a href="http://kr-bet777.top">토토사이트 추천 안전놀이터</a></div>'
_STATIC_SAME = '<html><head><meta charset="utf-8"></head><body><p>안내</p><script>document.getElementById("x").innerHTML = "<b>공지</b>";</script></body></html>'


def _fake_browser(tmp_path: Path) -> str:
    fake = tmp_path / "fakebrowser.py"
    fake.write_text(
        "import sys, time\n"
        "url = sys.argv[-1]\n"
        "assert '--dump-dom' in sys.argv and any(a.startswith('--user-data-dir=') for a in sys.argv)\n"
        "if url.endswith('slow.html'):\n    time.sleep(30)\n"
        "if url.endswith('fail.html'):\n    sys.exit(1)\n"
        "if url.endswith('inject.html'):\n"
        f"    sys.stdout.buffer.write({_STATIC_INJECT!r}.replace('</body>', {_INJECTED!r} + '</body>').encode('utf-8'))\n"
        "else:\n"
        f"    sys.stdout.buffer.write({_STATIC_SAME!r}.encode('utf-8'))\n", encoding="utf-8")
    return str(fake)


def test_browser_stage_fake_browser(tmp_path, monkeypatch):
    from iad import browser as B
    monkeypatch.setenv("IAD_BROWSER", _fake_browser(tmp_path))
    monkeypatch.setattr(B, "PER_PAGE_TIMEOUT", 2.0)
    pages = [Page(url="http://ex.go.kr/inject.html", html=_STATIC_INJECT),
             Page(url="http://ex.go.kr/same.html", html=_STATIC_SAME),
             Page(url="http://ex.go.kr/slow.html", html=_STATIC_SAME),
             Page(url="http://ex.go.kr/fail.html", html=_STATIC_SAME),
             Page(url="http://ex.go.kr/clean.html", html="<html><body><p>스크립트 없음</p></body></html>")]
    assert B.is_suspicious_page(_STATIC_INJECT) and not B.is_suspicious_page(pages[-1].html)
    static = analyze_page(pages[0], "ex.go.kr")
    assert not any(f.official for f in static)   # 정적으로는 주입 결과를 볼 수 없다(스크립트 ETC 만)
    t0 = __import__("time").monotonic()
    out, note = B.browser_stage(pages, static, "ex.go.kr", lambda: 100.0, lambda m: None)
    assert __import__("time").monotonic() - t0 < 15, note
    assert len(out) == 1 and out[0].page_url == "http://ex.go.kr/inject.html", [(f.location, f.extra_names) for f in out]
    f = out[0]
    assert not f.official and "DYNAMIC_INJECTION" in f.extra_names and f.location.startswith("div") and any("kr-bet777.top" in u for u in f.links)
    assert "2쪽 렌더" in note and "2쪽 실패" in note, note


def test_browser_stage_fails_closed(tmp_path, monkeypatch):
    from iad import browser as B
    monkeypatch.setenv("IAD_BROWSER", str(tmp_path / "no-such-browser"))
    out, note = B.browser_stage([Page(url="http://ex.go.kr/a", html=_STATIC_INJECT)], [], "ex.go.kr", lambda: 100.0, lambda m: None)
    assert out == [] and "없음" in note
    assert B.dump_dom(str(tmp_path / "no-such-browser"), "http://127.0.0.1:9/") is None


def test_scan_browser_stage_goes_to_result_extra_only(tmp_path, monkeypatch):
    from iad.testbed import pick_port, serve
    from iad.crawler import CrawlConfig
    from iad.scan import scan
    (tmp_path / "fb").mkdir(exist_ok=True)
    monkeypatch.setenv("IAD_BROWSER", _fake_browser(tmp_path / "fb"))
    port = pick_port(0)
    (tmp_path / "inject.html").write_text(_STATIC_INJECT, encoding="utf-8")
    srv = serve(tmp_path, port)
    try:
        res = scan(f"http://127.0.0.1:{port}/inject.html", CrawlConfig(delay=0, allowed_hosts=("127.0.0.1", "localhost"), cloak_pages=0),
                   out_dir=tmp_path / "out", result_dir=tmp_path / "out", log=lambda m: None, write_report=False)
    finally:
        srv.shutdown()
    official = json.loads((tmp_path / "out" / "result.json").read_text(encoding="utf-8"))["findings"]
    extra = json.loads((tmp_path / "out" / "result_extra.json").read_text(encoding="utf-8"))["findings"]
    assert official == []
    assert any(e["extra_finding"] == "DYNAMIC_INJECTION" or "DYNAMIC_INJECTION" in e["extra_finding"] for e in extra), extra
    assert "1쪽 렌더" in res.browser_note


_LIVE = None
try:
    import os as _os
    if not _os.environ.get("IAD_BROWSER"):
        from iad.browser import find_browser as _fb
        _LIVE = _fb()
except Exception:
    _LIVE = None


@pytest.mark.skipif(not _LIVE, reason="Edge/Chrome 없음")
def test_browser_stage_live_chrome(tmp_path, monkeypatch):
    """실제 브라우저로 document.write 주입을 회수한다(설치된 PC 에서만)."""
    from iad import browser as B
    from iad.testbed import pick_port, serve
    monkeypatch.delenv("IAD_BROWSER", raising=False)
    port = pick_port(0)
    (tmp_path / "inject.html").write_text(_STATIC_INJECT, encoding="utf-8")
    srv = serve(tmp_path, port)
    try:
        url = f"http://127.0.0.1:{port}/inject.html"
        html = B.dump_dom(_LIVE, url)
        assert html and "kr-bet777.top" in html, (html or "")[:300]
        out, note = B.browser_stage([Page(url=url, html=_STATIC_INJECT)], [], "127.0.0.1", lambda: 60.0, lambda m: None)
    finally:
        srv.shutdown()
    assert out and "DYNAMIC_INJECTION" in out[0].extra_names and not out[0].official, note


def test_browser_stage_dom_normalization_is_not_injection(tmp_path, monkeypatch):
    """Chrome 이 <tbody> 를 끼워 경로가 달라져도 정적 HTML 에 이미 있는 내용은 동적 주입이 아니다."""
    from iad import browser as B
    static = ('<html><head><meta charset="utf-8"><style>.t{color:#fff;background:#fff}</style></head><body>'
              '<table><tr><td class="t">토토사이트 추천 안전놀이터 <a href="http://kr-bet777.top">바로가기</a></td></tr></table>'
              '<div id="x"></div><script>document.getElementById("x").innerHTML = "<b>공지</b>";</script></body></html>')
    rendered = static.replace("<table><tr>", "<table><tbody><tr>").replace("</tr></table>", "</tr></tbody></table>").replace('<div id="x"></div>', '<div id="x"><b>공지</b></div>')
    fake = tmp_path / "fb.py"
    fake.write_text(f"import sys\nsys.stdout.buffer.write({rendered!r}.encode('utf-8'))\n", encoding="utf-8")
    monkeypatch.setenv("IAD_BROWSER", str(fake))
    page = Page(url="http://ex.go.kr/t.html", html=static)
    static_fs = analyze_page(page, "ex.go.kr")
    assert any("TRANSPARENT" in f.official for f in static_fs)
    out, note = B.browser_stage([page], static_fs, "ex.go.kr", lambda: 60.0, lambda m: None)
    assert out == [], [(f.location, f.extra_names, f.evidence_text) for f in out]


# ---------- R8: GUI 최소 폭(820)에서 상단 라벨·체크박스가 잘리지 않는다 ----------
def test_gui_labels_fit_at_min_width():
    import tkinter as tk
    import run_gui
    try:
        app = run_gui.App()
    except tk.TclError as e:          # 디스플레이 없는 러너
        pytest.skip(f"tk 디스플레이 없음: {e}")
    try:
        app.geometry("820x600")
        for _ in range(3):
            app.update_idletasks()
            app.update()
        top = app.winfo_children()[0]
        bad = []
        for frame in top.winfo_children():
            if not frame.winfo_children():
                continue
            fw = frame.winfo_width()
            for w in frame.winfo_children():
                if w.winfo_x() + w.winfo_reqwidth() > fw + 1:
                    bad.append((w.cget("text") if "text" in w.keys() else type(w).__name__, w.winfo_x(), w.winfo_reqwidth(), fw))
        assert not bad, bad
        assert app.static_note.cget("wraplength") > 40 if hasattr(app, "static_note") else True
    finally:
        app.destroy()


# ---------- R9: 테스트베드 서버는 클라이언트 조기 종료(WinError 10053 등)에 트레이스백을 찍지 않는다 ----------
def test_testbed_server_quiet_on_client_disconnect(tmp_path, capsys):
    from iad.testbed import TestbedServer, pick_port, serve
    srv = serve(tmp_path, pick_port(0))
    try:
        assert isinstance(srv, TestbedServer)
        for exc in (ConnectionAbortedError(10053, "WinError 10053"), ConnectionResetError(), BrokenPipeError()):
            try:
                raise exc
            except OSError:
                srv.handle_error(None, ("127.0.0.1", 1))
        assert capsys.readouterr().err == ""
        try:
            raise ValueError("진짜 오류")
        except ValueError:
            srv.handle_error(None, ("127.0.0.1", 1))
        assert "진짜 오류" in capsys.readouterr().err   # 다른 예외는 기존대로 출력
    finally:
        srv.shutdown()


def test_crawler_connection_error_is_one_line():
    from iad.crawler import Crawler, CrawlConfig
    port = __import__("iad.testbed", fromlist=["pick_port"]).pick_port(0)   # 아무도 안 듣는 포트
    c = Crawler(f"http://127.0.0.1:{port}/a.html", CrawlConfig(delay=0, timeout=1, allowed_hosts=("127.0.0.1",)))
    page = c.fetch(f"http://127.0.0.1:{port}/a.html", 0)
    assert page.error and page.error.startswith("요청 실패: ") and "\n" not in page.error


# ---------- R10: Windows 내장 OCR 단계(맥에서는 가짜 실행기로 명령 구성·인코딩·파싱·타임아웃·실패 폴백 검증) ----------
_FAKE_OCR = '''import sys, os, json, base64, time
args = sys.argv[1:]
assert args[:6] == ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand"][:5] + [args[5]], args
script = base64.b64decode(args[5]).decode("utf-16-le")
assert "OcrEngine" in script and "[Console]::OutputEncoding" in script and "\\ufeff" not in script
paths = json.load(open(os.environ["IAD_OCR_LIST"], encoding="utf-8"))
mode = os.environ.get("FAKE_OCR_MODE", "ok")
if mode == "slow":
    time.sleep(30)
if mode == "fail":
    sys.exit(1)
if mode == "noengine":
    print('{"error":"no_engine"}'); sys.exit(2)
sys.stdout.buffer.write("\\ufeff".encode("utf-8"))   # BOM 이 섞여도 파싱되어야 한다
for i, p in enumerate(paths):
    data = open(p, "rb").read()
    assert data[:4] == b"\\x89PNG", p
    text = "토토사이트 추천 안전놀이터 가입코드" if i % 2 == 0 else "불법도박 예방 캠페인 신고 1336"
    sys.stdout.buffer.write((json.dumps({"i": i, "lang": "ko", "text": text}, ensure_ascii=False) + "\\n").encode("utf-8"))
'''


def _ocr_page(port: int = 1) -> Page:
    from iad.testbed import BANNER_AD_PNG_B64, BANNER_CAMPAIGN_PNG_B64
    html = (f'<html><body><p>소식지</p><a id="ad1" href="event/notice.html"><img alt="" src="data:image/png;base64,{BANNER_AD_PNG_B64}"></a>'
            f'<a id="ok1" href="about.html"><img alt="캠페인 배너" src="data:image/png;base64,{BANNER_CAMPAIGN_PNG_B64}"></a>'
            f'<a href="x.html"><img alt="" src="data:,"></a><img alt="로고" src="logo.png"></body></html>')
    return Page(url="http://ex.go.kr/post/banner.html", html=html)


def test_ocr_fake_runner_end_to_end(tmp_path, monkeypatch):
    from iad import ocr as O
    fake = tmp_path / "fake_ocr.py"
    fake.write_text(_FAKE_OCR, encoding="utf-8")
    monkeypatch.setenv("IAD_OCR_EXE", str(fake))
    monkeypatch.setenv("FAKE_OCR_MODE", "ok")
    page = _ocr_page()
    cands = O._candidates(BeautifulSoup(page.html, "lxml"), page.url)
    assert [c[0].get("id") for c in cands] == ["ad1", "ok1"], cands   # data:, 빈 이미지·로고는 후보 아님
    static = analyze_page(page, "ex.go.kr")
    out, note = O.ocr_stage([page], static, "ex.go.kr", None, None, lambda: 100.0, lambda m: None)
    assert len(out) == 1 and 'id="ad1"' in out[0].html and "IMAGE_TEXT_AD" in out[0].extra_names and not out[0].official, (note, [(f.location, f.extra_names) for f in out])
    assert BeautifulSoup(page.html, "lxml").select_one(out[0].location).get("id") == "ad1"   # 캠페인 배너(ok1)는 행정 문맥으로 제외
    assert any(e.rule == "ocr.image_text" and "OCR ko" in e.detail for e in out[0].evidence)
    assert "광고 판정 1" in note


@pytest.mark.parametrize("mode,expect", [("slow", "타임아웃"), ("fail", "타임아웃"), ("noengine", "엔진 없음")])
def test_ocr_fallbacks_are_one_line(tmp_path, monkeypatch, mode, expect):
    from iad import ocr as O
    fake = tmp_path / "fake_ocr.py"
    fake.write_text(_FAKE_OCR, encoding="utf-8")
    monkeypatch.setenv("IAD_OCR_EXE", str(fake))
    monkeypatch.setenv("FAKE_OCR_MODE", mode)
    monkeypatch.setattr(O, "PER_IMAGE_SEC", 0.5)
    monkeypatch.setattr(O, "STAGE_BUDGET", 6.0)
    logs: list[str] = []
    out, note = O.ocr_stage([_ocr_page()], [], "ex.go.kr", None, None, lambda: 100.0, logs.append)
    assert out == [] and expect in note, note
    assert all("\n" not in m for m in logs)


def test_ocr_skipped_without_windows(monkeypatch):
    from iad import ocr as O
    monkeypatch.delenv("IAD_OCR_EXE", raising=False)
    if sys.platform != "win32":
        assert O.powershell_path() is None
        assert O.ocr_stage([_ocr_page()], [], "ex.go.kr", None, None, lambda: 100.0, lambda m: None) == ([], "Windows OCR 없음(생략)")
    cmd, env = O.build_command("powershell.exe", "list.json")
    assert cmd[1:6] == ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand"] and env["IAD_OCR_LIST"] == "list.json"
    assert __import__("base64").b64decode(cmd[6]).decode("utf-16-le").lstrip().startswith("$ErrorActionPreference")
