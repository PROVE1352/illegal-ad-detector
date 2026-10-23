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
    assert loc == "div.notice-board > table.board-list > tr:nth-of-type(2) > td.title > a"
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


def test_euc_kr_decode():
    from iad.crawler import decode_html

    class R:  # noqa: D401
        content = "<html><head><meta charset=euc-kr></head><body>고수익알바</body></html>".encode("cp949")
        headers = {"content-type": "text/html"}
    txt, enc = decode_html(R())
    assert "고수익알바" in txt and enc == "cp949"
