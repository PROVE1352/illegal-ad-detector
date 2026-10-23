"""숨김 기법 탐지: 인라인 style, <style> 시트(단순 선택자), 속성, 크기, 색상 일치 등."""
from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag

_DECL = re.compile(r"([a-zA-Z\-]+)\s*:\s*([^;]+)")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_NUM = re.compile(r"-?\d+(?:\.\d+)?")

NAMED_COLORS = {
    "white": "ffffff", "black": "000000", "red": "ff0000", "blue": "0000ff", "transparent": "transparent",
    "gray": "808080", "grey": "808080", "silver": "c0c0c0", "yellow": "ffff00", "green": "008000",
}


def parse_style(style: str | None) -> dict[str, str]:
    if not style:
        return {}
    out: dict[str, str] = {}
    for m in _DECL.finditer(style):
        out[m.group(1).strip().lower()] = m.group(2).strip().lower().replace("!important", "").strip()
    return out


def norm_color(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in NAMED_COLORS:
        return NAMED_COLORS[v]
    m = re.match(r"#([0-9a-f]{3,8})$", v)
    if m:
        h = m.group(1)
        if len(h) == 3 or len(h) == 4:
            h = "".join(c * 2 for c in h[:3])
        return h[:6]
    m = re.match(r"rgba?\(([^)]+)\)", v)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        try:
            if len(parts) == 4 and float(parts[3]) == 0:
                return "transparent"
            r, g, b = (int(float(p)) for p in parts[:3])
            return f"{r:02x}{g:02x}{b:02x}"
        except ValueError:
            return None
    return None


def _px(value: str | None) -> float | None:
    if value is None:
        return None
    m = _NUM.search(value)
    if not m:
        return None
    n = float(m.group())
    if value.strip().endswith(("em", "rem")):
        n *= 16
    return n


def sheet_rules(soup: BeautifulSoup) -> list[tuple[str, dict[str, str]]]:
    """<style> 안의 단순 규칙(#id, .class, tag, 복합 단순 선택자)을 추출한다."""
    rules: list[tuple[str, dict[str, str]]] = []
    for st in soup.find_all("style"):
        css = st.get_text() or ""
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        css = re.sub(r"@media[^{]*\{", "", css)  # 미디어쿼리 껍데기 제거(내용은 그대로 평가)
        for m in _RULE.finditer(css):
            sel = m.group(1).strip()
            decls = parse_style(m.group(2))
            if not decls or sel.startswith("@"):
                continue
            for s in sel.split(","):
                s = s.strip()
                if s and ":" not in s:
                    rules.append((s, decls))
    return rules


def apply_sheet(soup: BeautifulSoup, rules: list[tuple[str, dict[str, str]]]) -> dict[int, dict[str, str]]:
    """요소 id(id()) → 시트로 적용된 선언 맵."""
    applied: dict[int, dict[str, str]] = {}
    for sel, decls in rules:
        try:
            matched = soup.select(sel)
        except Exception:
            continue
        for el in matched:
            applied.setdefault(id(el), {}).update(decls)
    return applied


def effective_style(el: Tag, sheet: dict[int, dict[str, str]]) -> dict[str, str]:
    st = dict(sheet.get(id(el), {}))
    st.update(parse_style(el.get("style")))
    # font 태그 속성
    if el.name == "font":
        if el.get("size") in ("0", "1", "-2", "-3"):
            st.setdefault("font-size", "1px")
        if el.get("color"):
            st.setdefault("color", str(el.get("color")))
    return st


def background_of(el: Tag, sheet: dict[int, dict[str, str]]) -> str:
    """가장 가까운 배경색(없으면 흰색)."""
    cur: Tag | None = el
    while cur is not None and isinstance(cur, Tag):
        st = effective_style(cur, sheet)
        bg = norm_color(st.get("background-color") or _bg_from_shorthand(st.get("background")))
        if bg and bg != "transparent":
            return bg
        if cur.name == "body" and cur.get("bgcolor"):
            c = norm_color(str(cur.get("bgcolor")))
            if c:
                return c
        cur = cur.parent if isinstance(cur.parent, Tag) else None
    return "ffffff"


def _bg_from_shorthand(v: str | None) -> str | None:
    if not v:
        return None
    for tok in v.split():
        if norm_color(tok):
            return tok
    return None


def hidden_techniques(el: Tag, sheet: dict[int, dict[str, str]]) -> list[tuple[str, str]]:
    """요소 자체의 숨김 기법 목록 [(기법ID, 설명)]."""
    st = effective_style(el, sheet)
    out: list[tuple[str, str]] = []
    if st.get("display") == "none":
        out.append(("display_none", "display:none"))
    if st.get("visibility") in ("hidden", "collapse"):
        out.append(("visibility_hidden", f"visibility:{st['visibility']}"))
    op = _px(st.get("opacity"))
    if op is not None and op <= 0.05 and "%" not in st.get("opacity", ""):
        out.append(("opacity_zero", f"opacity:{st['opacity']}"))
    fs = _px(st.get("font-size"))
    if fs is not None and 0 <= fs <= 1:
        out.append(("font_size_zero", f"font-size:{st['font-size']}"))
    pos = st.get("position")
    if pos in ("absolute", "fixed", "relative"):
        for k in ("left", "top", "right", "bottom"):
            v = _px(st.get(k))
            if v is not None and v <= -500:
                out.append(("offscreen", f"position:{pos}; {k}:{st[k]}"))
                break
    ti = _px(st.get("text-indent"))
    if ti is not None and ti <= -500:
        out.append(("offscreen", f"text-indent:{st['text-indent']}"))
    w = _px(st.get("width") or el.get("width"))
    h = _px(st.get("height") or el.get("height"))
    if (w is not None and 0 <= w <= 1) or (h is not None and 0 <= h <= 1):
        if el.name == "iframe":
            out.append(("iframe_1x1", f"iframe 크기 {w}x{h}"))
        elif (w is not None and 0 <= w <= 1 and h is not None and 0 <= h <= 1) or st.get("overflow") == "hidden" \
                or (h is not None and 0 <= h <= 1):
            out.append(("tiny_size", f"크기 {w}x{h}px"))
    if st.get("clip") and re.search(r"rect\(\s*0(px)?\s*,?\s*0(px)?\s*,?\s*0(px)?\s*,?\s*0", st["clip"]):
        out.append(("tiny_size", f"clip:{st['clip']}"))
    if st.get("clip-path") in ("inset(100%)", "inset(50%)", "circle(0)", "circle(0px)", "polygon(0 0, 0 0, 0 0)"):
        out.append(("tiny_size", f"clip-path:{st['clip-path']}"))
    color = norm_color(st.get("color"))
    if color:
        if color == "transparent":
            out.append(("color_match", "color:transparent"))
        else:
            bg = background_of(el, sheet)
            if color == bg:
                out.append(("color_match", f"글자색 #{color} = 배경색 #{bg}"))
    if el.has_attr("hidden"):
        out.append(("hidden_attr", "hidden 속성"))
    if el.get("aria-hidden") == "true" and el.name in ("div", "span", "p", "a"):
        out.append(("hidden_attr", "aria-hidden=true"))
    if el.name == "marquee":
        out.append(("marquee", "<marquee> 태그"))
    if el.name == "noscript":
        out.append(("noscript", "<noscript> 안"))
    if el.get("type") == "hidden" and el.name == "input":
        out.append(("hidden_attr", "input type=hidden"))
    return out
