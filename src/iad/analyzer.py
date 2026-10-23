"""페이지 1장을 분석해 Finding 목록을 만든다(정적 분석).

출력 두 갈래:
- official(요강 필수 4종): HOMOGLYPH / JAMO / TRANSPARENT / OFFSCREEN → result.json
- extra(그 외 모든 근거): technique "ETC" → result_extra.json
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from . import hidden as H
from .keywords import CATEGORY_LABEL, LEVEL_PLAIN, admin_context_score, match_keywords_levels, match_whitelist
from .links import analyze_link, find_urls_in_text, host_of, idn_homograph_hosts, is_same_site, is_trusted
from .models import Finding, Page
from .normalize import collapse_spaces, has_composable_jamo, has_homoglyph_chars
from .scripts import analyze_meta_refresh, analyze_script

TEXT_TAGS = {"p", "div", "span", "li", "td", "th", "font", "b", "strong", "em", "i", "u", "small", "h1", "h2",
             "h3", "h4", "h5", "h6", "dd", "dt", "blockquote", "pre", "label", "article", "section", "marquee",
             "center", "s", "strike", "del", "ins", "sup", "sub", "mark", "q", "cite", "address", "figcaption",
             "a", "caption", "summary", "details", "aside", "header", "footer", "nav", "main", "tr", "ul", "ol",
             "table", "tbody", "form", "fieldset", "legend"}
SKIP_TAGS = {"script", "style", "head", "title", "meta", "link", "svg", "path", "html", "noscript", "template"}
BLOCK_TAGS = {"p", "div", "li", "tr", "td", "th", "table", "ul", "ol", "h1", "h2", "h3", "h4", "section", "article",
              "blockquote", "dl", "dd", "dt", "form", "nav", "header", "footer", "pre"}
CONTAINER_TAGS = {"div", "td", "article", "section", "li", "dd", "blockquote", "p", "body"}
HIDDEN_WEIGHT = {
    "display_none": 2.5, "visibility_hidden": 2.5, "opacity_zero": 2.5, "font_size_zero": 2.5, "offscreen": 2.5,
    "tiny_size": 2.5, "iframe_1x1": 3, "color_match": 2.5, "hidden_attr": 2.5, "hidden_attribute": 2.5, "marquee": 1.5, "noscript": 2,
    "html_comment": 2.5,
}
# 요강 4종 매핑. 요강: TRANSPARENT=배경색 동일·opacity:0·color:transparent, OFFSCREEN=font-size 0~1px·position 밖·display:none
OFFICIAL_MAP = {
    "display_none": "OFFSCREEN", "hidden_attribute": "OFFSCREEN", "font_size_zero": "OFFSCREEN", "offscreen": "OFFSCREEN",
    "tiny_size": "OFFSCREEN", "color_match": "TRANSPARENT", "opacity_zero": "TRANSPARENT",
}
# 은닉 기법이 겹칠 때(display:none + color:#fff 등) 보고할 하나를 고르는 지배 순서: 렌더링 자체를 없애는 것 > 화면 밖 > 글자 크기 0 > 잘림 > 투명
HIDE_DOMINANCE = ["display_none", "hidden_attribute", "offscreen", "font_size_zero", "tiny_size", "color_match", "opacity_zero"]


def dominant_official(techs: list[tuple[str, str]]) -> str | None:
    """겹친 은닉 기법 중 지배적인 하나의 요강 코드. 없으면 None."""
    names = {t for t, _ in techs}
    for t in HIDE_DOMINANCE:
        if t in names:
            return OFFICIAL_MAP[t]
    return None
_CONJ_RE = re.compile("[\u1100-\u11ff]")
_SYL_RE = re.compile("[\uac00-\ud7a3]")
THRESHOLD = 3.0
MASS_LINK_MIN = 5
ADMIN_WINDOW = 100          # 행정 문맥 판정 창(키워드 주변 ±자)
ADMIN_EXCLUDE = -2.0        # 창 안 행정 문맥 점수가 이 이하이고 의심 링크·은닉·난독화가 없으면 안내문으로 보고 제외
OFFICIAL_MIN_KEYWORD = 2.0   # 4종에 넣기 위한 최소 키워드 가중치(오탐이 정확도 감점이므로 보수적으로)
OFFICIAL_MIN_SUM = 3.0       # 단일 키워드가 약해도(슬롯 1.5 + 카지노 1.5) 같은 범주 합이 이 값 이상이면 4종 게이트 통과


# ---------- 위치(요강 규칙) ----------
def _segment(el: Tag) -> str:
    classes = [c for c in (el.get("class") or []) if c and re.match(r"^[A-Za-z_\-][\w\-]*$", c)]
    seg = el.name + "".join("." + c for c in classes)
    parent = el.parent
    if isinstance(parent, Tag):
        same_tag = [c for c in parent.find_all(el.name, recursive=False)]
        if not classes:
            if len(same_tag) > 1:
                seg += f":nth-of-type({same_tag.index(el) + 1})"
        else:
            same_cls = [c for c in same_tag if (c.get("class") or []) == (el.get("class") or [])]
            if len(same_cls) > 1:
                seg += f":nth-of-type({same_tag.index(el) + 1})"
    return seg


def location_of(el: Tag, soup: BeautifulSoup | None = None) -> str:
    """요강 규칙: 태그.클래스 를 상위부터 ' > ' 로 연결, 클래스 없으면 nth-of-type. html/body 는 생략."""
    parts: list[str] = []
    cur: Tag | None = el
    while cur is not None and isinstance(cur, Tag) and cur.name not in ("[document]", "html", "body"):
        parts.append(_segment(cur))
        cur = cur.parent if isinstance(cur.parent, Tag) else None
    segs = list(reversed(parts))
    path = ""
    for i, seg in enumerate(segs):
        if i == 0:
            path = seg
            continue
        prev = segs[i - 1]
        # 원본에 tbody 가 없는 table > tr 은 브라우저 DOM 에서 tbody 가 끼므로 자손 결합자(공백)로 적는다(두 DOM 모두에서 같은 요소)
        comb = " " if (prev.split(".")[0].split(":")[0] == "table" and seg.split(".")[0].split(":")[0] == "tr") else " > "
        path += comb + seg
    if not path:
        return el.name
    if soup is not None:
        try:
            if len(soup.select(path)) != 1:
                path = "html > body > " + path
        except Exception:
            pass
    return path


def css_path(el: Tag) -> str:   # 하위 호환
    return location_of(el)


def _snippet(el: Tag, limit: int = 160) -> str:
    txt = collapse_spaces(el.get_text(" "))
    if not txt:
        attrs = " ".join(f"{k}={v}" for k, v in el.attrs.items() if k in ("src", "href", "content", "data"))
        txt = f"<{el.name} {attrs}>".strip()
    return txt[:limit] + ("…" if len(txt) > limit else "")


def _raw_text(el: Tag, limit: int = 500) -> str:
    t = re.sub(r"[ \t\r\n]+", " ", el.get_text(" ")).strip()
    return t[:limit]


def _direct_text(el: Tag) -> str:
    return " ".join(s for s in el.find_all(string=True, recursive=False) if isinstance(s, NavigableString)
                    and not isinstance(s, Comment)).strip()


class PageAnalyzer:
    def __init__(self, page: Page, base_host: str) -> None:
        self.page = page
        self.base_host = base_host
        html = page.html or ""
        if _CONJ_RE.search(html):
            # 페이지 전체가 NFD(첫가끝 분해)로 저장된 경우(맥·일부 CMS)는 인코딩 특성이지 난독화가 아니므로 NFC 로 되돌린다.
            # 정상 음절이 섞인 페이지에서 일부 단어만 분해돼 있으면 그대로 두어 JAMO 로 판정한다.
            n_conj = len(_CONJ_RE.findall(html))
            n_syl = len(_SYL_RE.findall(html))
            if n_syl < n_conj * 0.2:
                html = unicodedata.normalize("NFC", html)
        self.soup = BeautifulSoup(html, "lxml")
        self.sheet = H.apply_sheet(self.soup, H.sheet_rules(self.soup, page.css_texts))
        self.findings: list[Finding] = []
        self.covered: set[int] = set()
        self.obf_owned: set[int] = set()   # 난독화 코드를 자기 위치에 이미 붙인 숨김 요소(자손에는 다시 붙이지 않음)
        title = self.soup.title.get_text(" ") if self.soup.title else ""
        h1 = " ".join(h.get_text(" ") for h in self.soup.find_all(["h1", "h2"])[:3])
        self.page_context = f"{title} {h1}"

    # ---------- 공용 ----------
    def _new(self, el: Tag) -> Finding:
        loc = location_of(el, self.soup)
        return Finding(page_url=self.page.report_url, css_path=loc, tag=el.name, snippet=_snippet(el),
                       html=str(el)[:800], parent_url=self.page.parent_url, is_iframe=self.page.is_iframe,
                       external=self.page.external, location=self.page.frame_prefix + loc,
                       evidence_text=_raw_text(el), frame_url=self.page.url if self.page.is_iframe else None)

    def _add_keywords(self, f: Finding, text: str, allow_whitelist: bool = True) -> tuple[dict[str, float], float]:
        """키워드 근거 추가. (카테고리별 점수, 최대 단일 키워드 가중치)"""
        cats: dict[str, float] = {}
        max_w = 0.0
        for cat, hits in match_keywords_levels(text).items():
            total = 0.0
            for kw, w, lv in hits:
                total += w
                max_w = max(max_w, w)
                label = CATEGORY_LABEL[cat]
                obf = lv != LEVEL_PLAIN
                f.add(f"keyword.{cat}", f"{label} 키워드 '{kw}'" + (f" ({lv} 난독화)" if obf else ""), w, "keyword")
                if obf:
                    f.add("keyword.obfuscated", f"난독화({lv})된 키워드 '{kw}'", 1.5, "keyword")
                    if "obfuscation" not in f.techniques:
                        f.techniques.append("obfuscation")
                    total += 1.5
            cats[cat] = min(total, 8.0)
        if cats and allow_whitelist:
            wl = match_whitelist(text, window=ADMIN_WINDOW)
            obf = any(e.rule == "keyword.obfuscated" for e in f.evidence)
            for kw, w in wl[:6]:
                # 고의 난독화(자모·유사문자·제로폭)가 있으면 정상 문맥 감점을 절반만 적용(난독화된 안내문은 없다)
                f.add("context.whitelist", f"정상 문맥 '{kw}'" + (" (난독화로 감점 절반)" if obf else ""), w / 2 if obf else w, "context")
            if not wl:
                for kw, w in match_whitelist(self.page_context)[:3]:
                    f.add("context.whitelist_page", f"페이지 제목 문맥 '{kw}'", w * 0.5, "context")
        return cats, max_w

    def _add_links(self, f: Finding, el: Tag, text: str) -> None:
        seen: set[str] = set()
        anchors = [el] if el.name == "a" else el.find_all("a", href=True)
        for a in anchors:
            href = urljoin(self.page.url, str(a.get("href", "")))
            if href in seen:
                continue
            seen.add(href)
            if host_of(href) and not is_same_site(href, self.base_host):
                f.links.append(href)
            self._link_rules(f, href, a.get_text(" "))
        for u in find_urls_in_text(text):
            if u in seen:
                continue
            seen.add(u)
            if not is_same_site(u, self.base_host):
                f.links.append(u)
            self._link_rules(f, u, "")

    def _idn_homograph(self, f: Finding, el: Tag | None, text: str) -> None:
        """링크 href·텍스트 속 도메인 레이블에 라틴처럼 보이는 키릴·그리스 문자가 섞여 있으면(IDN 호모그래프) HOMOGLYPH 근거."""
        hosts: list[str] = []
        if el is not None:
            anchors = [el] if el.name == "a" else el.find_all("a", href=True)
            hosts += [host_of(urljoin(self.page.url, str(a.get("href", "")))) for a in anchors]
        hits = idn_homograph_hosts(text, hosts)
        if hits:
            f.add("link.idn_homograph", "도메인에 라틴 유사 키릴·그리스 문자 혼용(IDN 호모그래프): " + ", ".join(hits[:3]), 3.0, "link")
            if "idn_homograph" not in f.techniques:
                f.techniques.append("idn_homograph")

    def _link_rules(self, f: Finding, href: str, anchor_text: str) -> None:
        for rule, detail, w in analyze_link(href, anchor_text, self.base_host):
            f.add(rule, detail, w, "link")
            tech = rule.split(".", 1)[1]
            if tech not in f.techniques:
                f.techniques.append(tech)

    def _finalize(self, f: Finding, cats: dict[str, float]) -> None:
        if self.page.external and not f.has_group("keyword") and not f.has_group("hidden"):
            return  # 외부 iframe 문서 안의 단순 링크는 보고하지 않는다(그 사이트 내부 링크일 뿐)
        content = f.has_group("keyword") or f.has_group("link") or f.has_group("script")
        if not content:
            return
        f.score = round(sum(e.weight for e in f.evidence), 2)
        if f.score < THRESHOLD and not f.official:
            return
        f.risk = "높음" if f.score >= 8 else "중간" if f.score >= 5 else "낮음"
        if cats:
            best = max(cats.items(), key=lambda kv: kv[1])[0]
            f.category = CATEGORY_LABEL[best]
        elif f.has_group("script"):
            f.category = "스크립트 주입"
        else:
            f.category = "의심 링크"
        if not f.official and not f.extra_names:
            f.extra_names = sorted({t for t in f.techniques}) or ["SUSPICIOUS"]
        self.findings.append(f)

    def _cover(self, el: Tag) -> None:
        self.covered.add(id(el))
        for d in el.descendants:
            if isinstance(d, Tag):
                self.covered.add(id(d))

    def _is_covered(self, el: Tag) -> bool:
        return id(el) in self.covered

    # ---------- 단계 ----------
    def run(self) -> list[Finding]:
        self._comments()
        self._meta_refresh()
        self._scripts()
        self._iframes()
        self._noscripts()
        self._elements()
        self._obfuscation_pass()
        self._mass_links()
        return self._merge()

    def _merge(self) -> list[Finding]:
        """같은 location 의 Finding 을 하나로 합친다(근거·기법 합집합)."""
        by_loc: dict[str, Finding] = {}
        for f in self.findings:
            key = f.location + "|" + f.tag
            if key in by_loc:
                g = by_loc[key]
                have = {(e.rule, e.detail) for e in g.evidence}
                for e in f.evidence:
                    if (e.rule, e.detail) not in have:
                        g.evidence.append(e)
                g.techniques = list(dict.fromkeys(g.techniques + f.techniques))
                g.official = list(dict.fromkeys(g.official + f.official))
                g.extra_names = list(dict.fromkeys(g.extra_names + f.extra_names))
                g.links = list(dict.fromkeys(g.links + f.links))
                g.score = round(sum(e.weight for e in g.evidence), 2)
                g.risk = "높음" if g.score >= 8 else "중간" if g.score >= 5 else "낮음"
                if g.category in ("기타", "의심 링크", "스크립트 주입") and f.category not in ("기타", "의심 링크", "스크립트 주입"):
                    g.category = f.category
            else:
                by_loc[key] = f
        out = list(by_loc.values())
        for g in out:
            if g.official:
                g.extra_names = [n for n in g.extra_names if n not in ("SUSPICIOUS", "obfuscation")]
        return out

    def _comments(self) -> None:
        for c in self.soup.find_all(string=lambda s: isinstance(s, Comment)):
            text = str(c)
            if not (find_urls_in_text(text) or re.search(r"<a\s", text, re.I) or match_keywords_levels(text)):
                continue
            parent = c.parent if isinstance(c.parent, Tag) else self.soup
            f = self._new(parent)
            f.tag = "#comment"
            f.html = f"<!--{text[:700]}-->"
            f.evidence_text = re.sub(r"\s+", " ", text).strip()[:500]
            f.snippet = collapse_spaces(re.sub(r"<[^>]+>", " ", text))[:160]
            f.techniques.append("html_comment")
            f.extra_names.append("HTML_COMMENT")
            f.add("hidden.html_comment", "HTML 주석 안의 링크/키워드", HIDDEN_WEIGHT["html_comment"], "hidden")
            inner = BeautifulSoup(text, "lxml")
            cats, _ = self._add_keywords(f, inner.get_text(" "), allow_whitelist=False)
            self._add_links(f, inner, text)
            if f.links or f.has_group("link"):
                f.add("link.in_comment", "주석 안 외부 링크", 1.5, "link")
            self._finalize(f, cats)

    def _noscripts(self) -> None:
        for ns in self.soup.find_all("noscript"):
            inner = BeautifulSoup(ns.decode_contents(), "lxml") if ns.contents else None
            text = (inner.get_text(" ") if inner else ns.get_text(" "))
            raw = ns.decode_contents()
            if not (find_urls_in_text(raw) or re.search(r"<a\s", raw, re.I) or match_keywords_levels(text)):
                continue
            f = self._new(ns)
            f.evidence_text = re.sub(r"\s+", " ", text).strip()[:500] or raw[:500]
            f.techniques.append("noscript")
            f.extra_names.append("NOSCRIPT")
            f.add("hidden.noscript", "<noscript> 안의 링크/키워드", HIDDEN_WEIGHT["noscript"], "hidden")
            cats, _ = self._add_keywords(f, text, allow_whitelist=False)
            if inner:
                self._add_links(f, inner, raw)
            if any(not is_trusted(host_of(u)) for u in f.links) and not f.has_group("keyword"):
                f.add("link.hidden_external", "noscript 안의 외부 링크", 1.5, "link")
            self._cover(ns)
            self._finalize(f, cats)

    def _meta_refresh(self) -> None:
        for m in self.soup.find_all("meta"):
            if str(m.get("http-equiv", "")).lower() == "refresh":
                rules = analyze_meta_refresh(str(m.get("content", "")), self.base_host)
                if rules:
                    f = self._new(m)
                    f.evidence_text = f'<meta http-equiv="refresh" content="{m.get("content")}">'
                    for rule, detail, w in rules:
                        f.add(rule, detail, w, "script")
                    f.techniques.append("meta_refresh")
                    f.extra_names.append("META_REFRESH")
                    target = re.search(r"url\s*=\s*[\"']?([^\"';]+)", str(m.get("content")), re.I)
                    if target:
                        f.links.append(target.group(1).strip())
                        self._link_rules(f, target.group(1).strip(), "")
                    self._finalize(f, {})

    def _scripts(self) -> None:
        for s in self.soup.find_all("script"):
            code = s.get_text() or ""
            if not code.strip():
                continue
            rules, extra = analyze_script(code, self.base_host)
            if not rules:
                continue
            f = self._new(s)
            f.snippet = collapse_spaces(code)[:160]
            f.evidence_text = re.sub(r"\s+", " ", code).strip()[:500]
            for rule, detail, w in rules:
                f.add(rule, detail, w, "script")
                f.techniques.append(rule.split(".", 1)[1])
            f.extra_names.append("SCRIPT_INJECTION")
            if any(r in ("script.base64", "script.encoded") for r, _, _ in rules):
                f.extra_names.append("SCRIPT_DECODED")
            inner = BeautifulSoup(extra, "lxml") if extra else None
            text_for_kw = (inner.get_text(" ") if inner else "") + " " + code
            cats, _ = self._add_keywords(f, text_for_kw, allow_whitelist=False)
            for u in find_urls_in_text(code + "\n" + extra):
                if not is_same_site(u, self.base_host):
                    if u not in f.links:
                        f.links.append(u)
                    self._link_rules(f, u, "")
            self._finalize(f, cats)

    def _iframes(self) -> None:
        for fr in self.soup.find_all(["iframe", "frame", "embed"]):
            src = urljoin(self.page.url, str(fr.get("src", "")))
            f = self._new(fr)
            techs = H.hidden_techniques(fr, self.sheet)
            for anc in fr.parents:
                if isinstance(anc, Tag) and anc.name not in ("body", "html", "[document]"):
                    techs += [(t, f"상위 요소 {anc.name}: {d}") for t, d in H.hidden_techniques(anc, self.sheet)]
            for tech, detail in techs:
                f.add(f"hidden.{tech}", detail, HIDDEN_WEIGHT.get(tech, 2), "hidden")
                if tech not in f.techniques:
                    f.techniques.append(tech)
            if src and host_of(src) and not is_same_site(src, self.base_host):
                f.links.append(src)
                if not is_trusted(host_of(src)):
                    f.add("link.external_iframe", f"외부 도메인 iframe ({host_of(src)})", 1.5, "link")
                    f.techniques.append("external_iframe")
                self._link_rules(f, src, "")
            if f.has_group("hidden") and fr.name == "iframe" and src and not f.has_group("link"):
                f.add("link.hidden_iframe", f"숨긴 iframe → {src[:80]}", 1, "link")
            f.extra_names.append("HIDDEN_IFRAME" if f.has_group("hidden") else "EXTERNAL_IFRAME")
            self._cover(fr)
            self._finalize(f, {})

    def _elements(self) -> None:
        body = self.soup.body or self.soup
        for el in body.descendants:
            if not isinstance(el, Tag) or el.name in SKIP_TAGS or self._is_covered(el):
                continue
            techs = H.hidden_techniques(el, self.sheet)
            if techs:
                self._hidden_block(el, techs)
                continue
            if el.name == "a":
                self._visible_anchor(el)
            elif el.name in TEXT_TAGS:
                self._visible_text(el)

    def _hidden_block(self, el: Tag, techs: list[tuple[str, str]]) -> None:
        self._cover(el)
        text = el.get_text(" ")
        if el.name == "input":
            text = str(el.get("value", ""))
        if not text.strip() and not el.find("a") and not el.find("img"):
            return
        f = self._new(el)
        for tech, detail in techs:
            f.add(f"hidden.{tech}", detail, HIDDEN_WEIGHT.get(tech, 2), "hidden")
            if tech not in f.techniques:
                f.techniques.append(tech)
        cats, max_w = self._add_keywords(f, text, allow_whitelist=False)
        self._add_links(f, el, text)
        self._idn_homograph(f, el, text)
        untrusted = [u for u in f.links if not is_trusted(host_of(u))]
        if untrusted and not f.has_group("keyword"):
            # 접근성 숨김(.sr-only/.blind/skip-link) 안의 공공기관 링크는 정상이므로 비신뢰 도메인 링크만 근거로 삼는다
            f.add("link.hidden_external", f"숨긴 요소 안의 외부 링크 ({host_of(untrusted[0])})", 1.5, "link")
            if "HIDDEN_EXTERNAL_LINK" not in f.extra_names:
                f.extra_names.append("HIDDEN_EXTERNAL_LINK")
        # 요강 4종 판정: 숨김 기법이 4종에 해당하고 불법 키워드가 충분히 강할 때만.
        # 숨긴 탭/아코디언 안의 정상 안내문(카지노 관광 안내 등)은 화이트리스트 문맥이 강하면 제외.
        wl_total = sum(w for _, w in match_whitelist(text))
        obfuscated = "obfuscation" in f.techniques   # 숨김 + 난독화가 겹치면 약한 키워드(카지노 1.5)도 고의성이 충분
        cat_sum = max(cats.values()) if cats else 0.0
        strong = max_w >= OFFICIAL_MIN_KEYWORD or cat_sum >= OFFICIAL_MIN_SUM or (obfuscated and max_w >= 1.0)
        if cats and strong and not (wl_total <= -3 and max_w < 3):
            # 은닉 기법끼리 겹치면 지배적인 하나만(요강: finding 당 technique 1개). 난독화(JAMO/HOMOGLYPH)는
            # _obfuscation_pass 가 같은 location 에 따로 붙여 두 finding 이 된다(채점자가 어느 라벨을 붙였을지 모르므로 둘 다 제출).
            code = dominant_official(techs)
            if code and code not in f.official:
                f.official.append(code)
            # 숨긴 요소 안의 난독화(JAMO/HOMOGLYPH)는 그 숨긴 요소 위치에 함께 붙인다(요강 예시: span.visually-hidden 의 JAMO).
            # 자식 요소에 다시 붙이면 같은 요소가 두 위치로 갈라져 한쪽이 오탐이 되므로 _obfuscation_pass 는 이 요소 아래를 건너뛴다.
            obf_codes, obf_hits, _ = self._obf_codes(text, leaf=not el.find(list(BLOCK_TAGS)))
            for oc in sorted(obf_codes):
                if oc not in f.official:
                    f.official.append(oc)
                    f.add(f"obfuscation.{oc.lower()}", f"{oc} 난독화 키워드: " +
                          ", ".join(f"{k}({lv})" for k, w, lv in obf_hits if lv == oc or lv == LEVEL_PLAIN)[:200], 2.5, "hidden")
                    if oc not in f.techniques:
                        f.techniques.append(oc)
            if obf_codes:
                self.obf_owned.add(id(el))
            if "idn_homograph" in f.techniques and "HOMOGLYPH" not in f.official:
                f.official.append("HOMOGLYPH")
        for tech, _ in techs:
            if tech not in OFFICIAL_MAP:
                name = "HIDDEN_" + tech.upper()
                if name not in f.extra_names:
                    f.extra_names.append(name)
        self._finalize(f, cats)

    def _is_admin_notice(self, f: Finding, text: str) -> bool:
        """행정 안내문 판정: 키워드 주변 ±100자에 예방·단속·신고 등 문맥이 있고, 의심 링크·은닉·난독화가 없다."""
        if not f.has_group("keyword") or f.has_group("link") or f.has_group("hidden") or f.has_group("script"):
            return False
        if any(e.rule == "keyword.obfuscated" for e in f.evidence):
            return False
        return admin_context_score(text, ADMIN_WINDOW) <= ADMIN_EXCLUDE

    BANNER_ALT_HINTS = ("배너", "광고", "이벤트", "banner", "ad", "ads", "event", "프로모션", "promo", "sponsor")

    def _image_banner(self, f: Finding, a: Tag, text: str) -> str:
        """텍스트 없이 이미지(또는 background-image)만 있는 링크 = 배너. 의심 도메인이거나 alt/title 에 배너·광고·이벤트·불법 키워드가
        있으면 IMAGE_BANNER_AD 근거를 붙인다(ETC 전용). 공공기관·신뢰 도메인·동일 사이트 링크는 제외. 반환: alt/title 텍스트."""
        imgs = a.find_all("img")
        st = a.get("style") or ""
        if text.strip() or not (imgs or "background-image" in st or "background:" in st and "url(" in st):
            return ""
        href = urljoin(self.page.url, str(a.get("href", "")))
        host = host_of(href)
        if not host or is_same_site(href, self.base_host) or is_trusted(host):
            return ""
        alt = " ".join(str(i.get("alt", "")) + " " + str(i.get("title", "")) for i in imgs) + " " + str(a.get("title", ""))
        alt_l = alt.lower()
        hint = next((h for h in self.BANNER_ALT_HINTS if h in alt_l), None)
        kw = match_keywords_levels(alt)
        suspicious = f.has_group("link")
        if suspicious or hint or kw:
            why = []
            if suspicious:
                why.append("의심 도메인")
            if hint:
                why.append(f"alt/title '{hint}'")
            if kw:
                why.append("alt/title 불법 키워드")
            f.add("banner.image_only", f"텍스트 없는 이미지 배너 링크 → {host} (" + ", ".join(why) + ")", 2.5, "link")
            if "image_banner" not in f.techniques:
                f.techniques.append("image_banner")
            f.extra_names.append("IMAGE_BANNER_AD")
            if not f.evidence_text.strip():
                f.evidence_text = f"[이미지 배너] alt='{alt.strip()[:120]}' href={href[:200]}"
        return alt

    def _visible_anchor(self, a: Tag) -> None:
        text = a.get_text(" ")
        f = self._new(a)
        self._add_links(f, a, "")
        alt = self._image_banner(f, a, text)
        cats, max_w = self._add_keywords(f, text + " " + str(a.get("title", "")) + " " + alt)
        self._idn_homograph(f, a, text)
        if f.has_group("link") and f.has_group("keyword"):
            f.add("combo.keyword_link", "의심 링크 + 키워드 동시 출현", 1.5, "link")
        if "idn_homograph" in f.techniques and (cats and max_w >= 1.0 or self._parent_has_keyword(a)):
            f.official.append("HOMOGLYPH")
        if self._is_admin_notice(f, text + " " + _direct_text(a.parent) if isinstance(a.parent, Tag) else text):
            return
        self._finalize(f, cats)

    def _parent_has_keyword(self, el: Tag) -> bool:
        """링크 자체엔 키워드가 없어도 같은 블록(부모 p/li/td/div)의 텍스트에 키워드가 있으면 True."""
        par = el.parent
        if isinstance(par, Tag) and par.name in CONTAINER_TAGS | {"span", "li", "td", "th", "dd"}:
            hits = match_keywords_levels(par.get_text(" "))
            return any(w >= 1.0 for hs in hits.values() for _, w, _ in hs)
        return False

    def _visible_text(self, el: Tag) -> None:
        text = _direct_text(el)
        if len(text) < 2:
            return
        f = self._new(el)
        f.evidence_text = text[:500]
        cats, max_w = self._add_keywords(f, text)
        for u in find_urls_in_text(text):
            if not is_same_site(u, self.base_host):
                f.links.append(u)
            self._link_rules(f, u, "")
        self._idn_homograph(f, None, text)
        if f.has_group("link") and f.has_group("keyword"):
            f.add("combo.keyword_link", "의심 링크 + 키워드 동시 출현", 1.5, "link")
        if "idn_homograph" in f.techniques and cats and max_w >= 1.0:
            f.official.append("HOMOGLYPH")
        if self._is_admin_notice(f, text):
            return
        self._finalize(f, cats)

    # ---------- HOMOGLYPH / JAMO ----------
    def _obf_codes(self, text: str, leaf: bool = True) -> tuple[set[str], list[tuple[str, float, str]], dict[str, float]]:
        """텍스트에서 요강 난독화 코드 집합을 구한다."""
        codes: set[str] = set()
        allhits: list[tuple[str, float, str]] = []
        cats: dict[str, float] = {}
        for cat, hits in match_keywords_levels(text).items():
            for kw, w, lv in hits:
                allhits.append((kw, w, lv))
                cats[cat] = cats.get(cat, 0) + w
                if w < 1.0:
                    continue
                if lv in ("JAMO", "HOMOGLYPH"):
                    codes.add(lv)
        if leaf and allhits and max(w for _, w, _ in allhits) >= 2.0:
            # 평문 키워드 + 문자 단서(전각·키릴 / 합성 가능 자모) → 해당 기법으로 본다(요강 예시 ｍｅｇａ－ＢＥＴ 첫충)
            # 블록 자식이 없는 요소(leaf)에서만: 컨테이너 수준에서 날짜 전각숫자와 키워드가 우연히 합쳐지는 오탐 방지
            if has_homoglyph_chars(text):
                codes.add("HOMOGLYPH")
            if has_composable_jamo(text):
                codes.add("JAMO")
        return codes, allhits, cats

    def _obf_codes_nocho(self, text: str, leaf: bool) -> set[str]:
        codes: set[str] = set()
        for cat, hits in match_keywords_levels(text, chosung=False).items():
            for kw, w, lv in hits:
                if w >= 1.0 and lv in ("JAMO", "HOMOGLYPH"):
                    codes.add(lv)
        if leaf and has_composable_jamo(text):
            codes.add("JAMO")
        return codes

    def _obfuscation_pass(self) -> None:
        """HOMOGLYPH/JAMO: 난독화 키워드를 품은 '가장 안쪽' 요소를 위치로 잡는다(숨김 여부 무관)."""
        body = self.soup.body or self.soup
        whole = body.get_text(" ")
        if not self._obf_codes(whole, leaf=True)[0]:
            return  # 페이지 전체에 난독화 단서가 없으면 요소 순회 생략(속도)
        for el in body.find_all(True):
            if el.name in SKIP_TAGS or el.name not in TEXT_TAGS:
                continue
            if el.find_parent(["script", "style", "noscript"]):
                continue
            if self.obf_owned and (id(el) in self.obf_owned or any(id(a) in self.obf_owned for a in el.parents)):
                continue
            text = el.get_text(" ")
            if not text.strip():
                continue
            leaf = not el.find(list(BLOCK_TAGS))
            codes, hits, cats = self._obf_codes(text, leaf)
            if not codes:
                continue
            if "JAMO" in codes and sum(w for _, w in match_whitelist(text, window=ADMIN_WINDOW)) <= -3:
                # 초성 퀴즈·한글 교육 자료: 초성 축약만으로 얻은 JAMO 는 인정하지 않는다
                codes_wo = self._obf_codes_nocho(text, leaf)
                if "JAMO" not in codes_wo:
                    codes.discard("JAMO")
                    if not codes:
                        continue
            # 자식 요소가 같은 코드를 모두 설명하면 자식에게 맡긴다(가장 안쪽 요소 선택)
            child_codes: set[str] = set()
            for ch in el.find_all(True, recursive=False):
                if ch.name in TEXT_TAGS:
                    child_codes |= self._obf_codes(ch.get_text(" "), not ch.find(list(BLOCK_TAGS)))[0]
            own = codes - child_codes
            if not own:
                continue
            f = self._new(el)
            f.evidence_text = _raw_text(el)
            for code in sorted(own):
                f.official.append(code)
                f.add(f"obfuscation.{code.lower()}", f"{code} 난독화 키워드: " +
                      ", ".join(f"{k}({lv})" for k, w, lv in hits if lv == code or lv == LEVEL_PLAIN)[:200], 2.5, "hidden")
                if code not in f.techniques:
                    f.techniques.append(code)
            self._add_keywords(f, text, allow_whitelist=False)
            self._finalize(f, cats)

    def _mass_links(self) -> None:
        body = self.soup.body or self.soup
        anchors = body.find_all("a", href=True)
        groups: dict[int, tuple[Tag, set[str]]] = {}
        for a in anchors:
            href = urljoin(self.page.url, str(a["href"]))
            h = host_of(href)
            if not h or is_same_site(href, self.base_host) or is_trusted(h):
                continue
            container: Tag | None = None
            for p in a.parents:
                if isinstance(p, Tag) and p.name in CONTAINER_TAGS and p.name != "body":
                    container = p
                    break
            if container is None:
                continue
            groups.setdefault(id(container), (container, set()))[1].add(h)
        for container, hosts in groups.values():
            if len(hosts) >= MASS_LINK_MIN:
                f = self._new(container)
                f.add("link.mass_external", f"한 게시글/영역에 외부 도메인 {len(hosts)}개 링크", 3.5, "link")
                f.techniques.append("mass_links")
                f.extra_names.append("MASS_EXTERNAL_LINKS")
                f.links = sorted(hosts)
                cats, _ = self._add_keywords(f, container.get_text(" "))
                self._finalize(f, cats)


def analyze_page(page: Page, base_host: str) -> list[Finding]:
    if page.error or not page.html:
        return []
    return PageAnalyzer(page, base_host).run()
