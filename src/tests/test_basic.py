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
    "color:#999", "color:#f0f0f0", "transform:translate(-50%,-50%)", "margin-left:-20px", "left:-9999px",  # position 없음
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
