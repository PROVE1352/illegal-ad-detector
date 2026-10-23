"""숨김 기법 탐지: 인라인 style, <style>/외부 CSS 시트(단순 선택자 + 명시도·!important 캐스케이드), 속성, 크기, 색상 일치 등.

시트 해석 범위(정적):
- 선택자: 태그/클래스/ID/속성/후손·자식 결합자 등 soupsieve 가 해석하는 것. 의사클래스(:hover 등)는 건너뛴다.
- @media: print 전용 블록은 무시, 그 외(screen/all/조건부)는 내용을 그대로 적용. @font-face/@keyframes 등은 무시.
- 캐스케이드: (!important, 명시도, 선언 순서) 오름차순으로 덮어쓰기. 인라인 style 은 시트의 일반 선언보다 우선,
  시트의 !important 보다는 뒤.
- 상속: display:none·offscreen·opacity·font-size·color 는 '그 스타일이 걸린 요소' 를 숨김 요소로 보고 자손을 포함해 판정한다
  (analyzer 가 요소 단위로 호출). 배경색은 조상으로 올라가며 가장 가까운 값을 쓴다(배경 이미지면 '알 수 없음').
"""
from __future__ import annotations

import re
from functools import lru_cache

from bs4 import BeautifulSoup, Tag

_DECL = re.compile(r"([a-zA-Z\-]+)\s*:\s*([^;]+)")
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_TAG_TOKEN = re.compile(r"(?:^|[\s>+~(])([a-zA-Z][\w-]*)")

NAMED_COLORS = {
    "white": "ffffff", "black": "000000", "red": "ff0000", "blue": "0000ff", "transparent": "transparent",
    "gray": "808080", "grey": "808080", "silver": "c0c0c0", "yellow": "ffff00", "green": "008000", "lime": "00ff00",
    "navy": "000080", "maroon": "800000", "purple": "800080", "orange": "ffa500", "pink": "ffc0cb", "brown": "a52a2a",
    "whitesmoke": "f5f5f5", "snow": "fffafa", "ivory": "fffff0", "ghostwhite": "f8f8ff", "aliceblue": "f0f8ff",
    "lightgray": "d3d3d3", "lightgrey": "d3d3d3", "gainsboro": "dcdcdc", "darkgray": "a9a9a9", "darkgrey": "a9a9a9",
    "dimgray": "696969", "dimgrey": "696969", "beige": "f5f5dc", "linen": "faf0e6", "seashell": "fff5ee",
    "floralwhite": "fffaf0", "mintcream": "f5fffa", "azure": "f0ffff", "lavender": "e6e6fa", "honeydew": "f0fff0",
    "oldlace": "fdf5e6", "cornsilk": "fff8dc", "lemonchiffon": "fffacd", "lightyellow": "ffffe0", "lightcyan": "e0ffff",
    "lavenderblush": "fff0f5", "mistyrose": "ffe4e1", "papayawhip": "ffefd5", "antiquewhite": "faebd7",
    "currentcolor": "currentcolor", "inherit": "inherit", "initial": "initial", "unset": "unset",
}

# 숨김 판정에 쓰는 속성만 시트에서 추린다(대형 사이트 CSS 의 select 비용 절감)
RELEVANT_PROPS = {
    "display", "visibility", "opacity", "font-size", "font", "position", "left", "top", "right", "bottom", "inset",
    "text-indent", "transform", "translate", "margin", "margin-left", "margin-top", "margin-right", "margin-bottom",
    "clip", "clip-path", "color", "background", "background-color", "background-image", "width", "height", "overflow",
}
MAX_RULES = 20000
NEAR_TOLERANCE = 10
_SIMPLE_SEL = re.compile(r"^(?P<tag>[a-zA-Z][\w-]*)?(?P<cls>(?:\.[\w-]+)+)?(?P<id>#[\w-]+)?$")   # 글자색-배경색 채널별 차이가 이 값 이하면 '사실상 같은 색'(대비 매우 낮음)


# ---------- 선언 파싱 ----------
def parse_style(style: str | None) -> dict[str, str]:
    """인라인 style → {속성: 값}. !important 표시는 제거(인라인은 어차피 최우선)."""
    out: dict[str, str] = {}
    for prop, val, _imp in _parse_decls(style):
        out[prop] = val
    return out


def _parse_decls(style: str | None) -> list[tuple[str, str, bool]]:
    if not style:
        return []
    out: list[tuple[str, str, bool]] = []
    for m in _DECL.finditer(style):
        prop = m.group(1).strip().lower()
        val = m.group(2).strip().lower()
        imp = "!important" in val
        val = val.replace("!important", "").strip()
        if prop and val:
            out.append((prop, val, imp))
    return out


# ---------- 색 ----------
def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    h = (h % 360) / 360.0
    s = max(0.0, min(1.0, s))
    l = max(0.0, min(1.0, l))
    if s == 0:
        v = round(l * 255)
        return v, v, v

    def hue(p: float, q: float, t: float) -> float:
        t %= 1.0
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return round(hue(p, q, h + 1 / 3) * 255), round(hue(p, q, h) * 255), round(hue(p, q, h - 1 / 3) * 255)


def parse_color(value: str | None) -> tuple[str, float] | None:
    """CSS 색 → (rrggbb 16진, 알파 0~1). 'transparent' 는 ('transparent', 0). 해석 불가면 None."""
    if not value:
        return None
    v = value.strip().lower()
    if v in NAMED_COLORS:
        h = NAMED_COLORS[v]
        if h == "transparent":
            return "transparent", 0.0
        if h in ("currentcolor", "inherit", "initial", "unset"):
            return None
        return h, 1.0
    m = re.match(r"#([0-9a-f]{3,8})$", v)
    if m:
        h = m.group(1)
        alpha = 1.0
        if len(h) in (3, 4):
            if len(h) == 4:
                alpha = int(h[3] * 2, 16) / 255
            h = "".join(c * 2 for c in h[:3])
        elif len(h) == 8:
            alpha = int(h[6:8], 16) / 255
            h = h[:6]
        elif len(h) != 6:
            return None
        return h, alpha
    m = re.match(r"(rgba?|hsla?)\(([^)]+)\)", v)
    if m:
        fn, inner = m.group(1), m.group(2)
        inner = inner.replace("/", " ").replace(",", " ")
        parts = inner.split()
        if len(parts) < 3:
            return None
        try:
            alpha = 1.0
            if len(parts) >= 4:
                a = parts[3]
                alpha = float(a[:-1]) / 100 if a.endswith("%") else float(a)
            if fn.startswith("rgb"):
                ch = []
                for p in parts[:3]:
                    ch.append(round(float(p[:-1]) * 2.55) if p.endswith("%") else int(float(p)))
                r, g, b = (max(0, min(255, c)) for c in ch)
            else:
                hdeg = float(re.sub(r"(deg|turn|rad)$", "", parts[0]))
                if parts[0].endswith("turn"):
                    hdeg *= 360
                s = float(parts[1].rstrip("%")) / 100
                l = float(parts[2].rstrip("%")) / 100
                r, g, b = _hsl_to_rgb(hdeg, s, l)
            return f"{r:02x}{g:02x}{b:02x}", max(0.0, min(1.0, alpha))
        except ValueError:
            return None
    return None


def norm_color(value: str | None) -> str | None:
    """하위 호환: rrggbb 또는 'transparent'(알파 ≤0.05 포함)."""
    c = parse_color(value)
    if c is None:
        return None
    h, a = c
    if h == "transparent" or a <= 0.05:
        return "transparent"
    return h


def colors_close(a: str, b: str, tol: int = NEAR_TOLERANCE) -> bool:
    if a == b:
        return True
    try:
        ra, ga, ba = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
        rb, gb, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    except ValueError:
        return False
    return max(abs(ra - rb), abs(ga - gb), abs(ba - bb)) <= tol


# ---------- 길이 ----------
def _px(value: str | None, allow_pct: bool = False) -> float | None:
    """px 로 환산(em/rem 은 16px 기준, pt 는 1.333). % 는 allow_pct 일 때만 숫자 그대로."""
    if value is None:
        return None
    v = value.strip()
    m = _NUM.search(v)
    if not m:
        return None
    n = float(m.group())
    unit = v[m.end():].strip().lower()[:3]
    if unit.startswith("%"):
        return n if allow_pct else None
    if unit.startswith(("em", "rem")):
        return n * 16
    if unit.startswith("pt"):
        return n * 4 / 3
    if unit.startswith(("vw", "vh")):
        return n * 10
    return n


def _lengths(value: str) -> list[float]:
    """'0 0 0 -9999px' 같은 단축 값의 px 길이 목록(% 제외)."""
    out: list[float] = []
    for tok in re.findall(r"-?\d+(?:\.\d+)?(?:px|em|rem|pt|vw|vh)?(?![\w%])", value):
        p = _px(tok)
        if p is not None:
            out.append(p)
    return out


# ---------- 시트 ----------
def _specificity(sel: str) -> tuple[int, int, int]:
    ids = sel.count("#")
    classes = sel.count(".") + sel.count("[")
    tags = len([t for t in _TAG_TOKEN.findall(sel) if t != "*"])
    return ids, classes, tags


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _walk_blocks(css: str, out: list[tuple[str, dict[str, str], dict[str, str]]]) -> None:
    i, n = 0, len(css)
    while i < n and len(out) < MAX_RULES:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j]
        # 블록 앞의 '@import ...;' 같은 문장은 떼어낸다
        prelude = prelude.rsplit(";", 1)[-1].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            ch = css[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        i = k
        if not prelude:
            continue
        if prelude.startswith("@"):
            name = prelude.split(None, 1)[0].lower()
            if name in ("@media", "@supports", "@layer", "@container", "@scope"):
                cond = prelude.lower()
                if name == "@media" and re.search(r"\bprint\b", cond) and not re.search(r"\b(screen|all)\b", cond):
                    continue   # 인쇄 전용 규칙은 화면 숨김이 아니다
                if name == "@media" and re.search(r"\bnot\s+(screen|all)\b", cond):
                    continue
                _walk_blocks(body, out)
            continue   # @font-face, @keyframes, @page 등
        decls = _parse_decls(body)
        if not decls:
            continue
        normal = {p: v for p, v, imp in decls if not imp and _may_hide(p, v)}
        important = {p: v for p, v, imp in decls if imp and _may_hide(p, v)}
        if not normal and not important:
            continue
        for s in prelude.split(","):
            s = s.strip()
            if not s or s.startswith("@"):
                continue
            if ":" in s:
                # ::before/::after 등 가상 요소·:hover 등 상태 의사클래스는 정적 판정에서 제외. :not()/:nth-* 도 보수적으로 제외.
                continue
            out.append((s, normal, important))


def _may_hide(prop: str, val: str) -> bool:
    """숨김 판정에 영향을 줄 수 있는 선언만 남긴다(대형 CSS 의 규칙 수를 줄여 요소 매핑 비용을 낮춘다)."""
    if prop not in RELEVANT_PROPS:
        return False
    # 덮어쓰기(.a{display:none} .a.on{display:block})가 흔한 속성은 값과 무관하게 전부 남긴다(캐스케이드 정확도)
    if prop in ("color", "background", "background-color", "background-image", "position", "overflow", "display",
                "visibility", "opacity", "font-size", "font", "left", "top", "right", "bottom", "inset", "text-indent"):
        return True
    # margin/transform 은 규칙 수가 매우 많고 숨김 용도는 드물어 화면 밖(≤-500px) 값일 때만 남긴다
    if prop in ("margin", "margin-left", "margin-top", "margin-right", "margin-bottom", "transform", "translate"):
        return "-" in val and any(x <= -500 for x in _lengths(val))
    if prop in ("clip", "clip-path"):
        return True
    if prop in ("width", "height"):
        n = _px(val)
        return n is not None and 0 <= n <= 1
    return True


@lru_cache(maxsize=256)
def _rules_from_text(css: str) -> tuple[tuple[str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]], ...]:
    out: list[tuple[str, dict[str, str], dict[str, str]]] = []
    _walk_blocks(_strip_comments(css or ""), out)
    return tuple((s, tuple(n.items()), tuple(i.items())) for s, n, i in out)


def sheet_rules(soup: BeautifulSoup, extra_css: list[str] | None = None) -> list[tuple[str, dict[str, str], dict[str, str]]]:
    """문서의 <style> + 외부 CSS 텍스트(extra_css, 문서 순서대로 앞에 온 것으로 본다)에서 규칙 목록을 만든다.

    반환: [(선택자, 일반 선언, !important 선언)] 선언 순서대로.
    """
    rules: list[tuple[str, dict[str, str], dict[str, str]]] = []
    for css in extra_css or []:
        rules += [(s, dict(n), dict(i)) for s, n, i in _rules_from_text(css)]
    for st in soup.find_all("style"):
        media = str(st.get("media", "")).lower()
        if media and "print" in media and "screen" not in media and "all" not in media:
            continue
        rules += [(s, dict(n), dict(i)) for s, n, i in _rules_from_text(st.get_text() or "")]
    return rules[:MAX_RULES]


def apply_sheet(soup: BeautifulSoup, rules: list) -> dict[int, dict[str, str]]:
    """요소 id(id()) → 시트로 적용된 선언 맵(캐스케이드 적용 후).

    값 맵에는 일반 선언을, '!important' 선언은 '!'+속성 키로 함께 넣어 effective_style 이 인라인 뒤에 다시 덮게 한다.
    """
    applied: dict[int, dict[str, str]] = {}
    ordered = []
    for order, rule in enumerate(rules):
        sel, normal, important = rule[0], rule[1], (rule[2] if len(rule) > 2 else {})
        ordered.append((_specificity(sel), order, sel, normal, important))
    ordered.sort(key=lambda r: (r[0], r[1]))
    if not ordered:
        return applied
    # 단순 선택자(tag / .a.b / #id / tag.a) 는 한 번 만든 색인으로 해석하고, 복합 선택자만 soup.select 로 푼다
    by_class: dict[str, list[Tag]] = {}
    by_id: dict[str, Tag] = {}
    by_tag: dict[str, list[Tag]] = {}
    all_tags: list[Tag] = []
    for el in soup.find_all(True):
        all_tags.append(el)
        by_tag.setdefault(el.name, []).append(el)
        for c in el.get("class") or []:
            by_class.setdefault(c, []).append(el)
        if el.get("id"):
            by_id.setdefault(str(el.get("id")), el)

    def resolve(sel: str) -> list[Tag]:
        m = _SIMPLE_SEL.match(sel)
        if not m:
            try:
                return soup.select(sel)
            except Exception:
                return []
        tag, cls, eid = m.group("tag"), m.group("cls"), m.group("id")
        if eid:
            el = by_id.get(eid[1:])
            cand = [el] if el is not None else []
        elif cls:
            classes = cls.split(".")[1:]
            cand = min((by_class.get(c, []) for c in classes), key=len)
        elif tag:
            cand = by_tag.get(tag.lower(), [])
        else:
            cand = all_tags
        if cls:
            need = set(cls.split(".")[1:])
            cand = [e for e in cand if need <= set(e.get("class") or [])]
        if tag:
            cand = [e for e in cand if e.name == tag.lower()]
        return cand

    cache: dict[str, list[Tag]] = {}
    for _spec, _order, sel, normal, important in ordered:
        if sel not in cache:
            cache[sel] = resolve(sel)
        for el in cache[sel]:
            d = applied.setdefault(id(el), {})
            d.update(normal)
            for p, v in important.items():
                d["!" + p] = v
    return applied


def effective_style(el: Tag, sheet: dict[int, dict[str, str]]) -> dict[str, str]:
    base = sheet.get(id(el), {})
    st = {k: v for k, v in base.items() if not k.startswith("!")}
    st.update(parse_style(el.get("style")))
    for k, v in base.items():
        if k.startswith("!"):
            st[k[1:]] = v
    if el.name == "font" and el.get("color"):
        st.setdefault("color", str(el.get("color")))
    return st


def background_of(el: Tag, sheet: dict[int, dict[str, str]]) -> str | None:
    """가장 가까운 배경색(rrggbb). 배경 이미지·그라데이션만 있으면 None(알 수 없음), 끝까지 없으면 흰색."""
    cur: Tag | None = el
    while cur is not None and isinstance(cur, Tag):
        st = effective_style(cur, sheet)
        bgc = st.get("background-color")
        if bgc:
            c = norm_color(bgc)
            if c and c != "transparent":
                return c
        short = st.get("background")
        if short:
            c = _bg_from_shorthand(short)
            if c and c != "transparent":
                return c
            if c is None and re.search(r"url\(|gradient\(", short):
                return None
        if st.get("background-image") and re.search(r"url\(|gradient\(", st["background-image"]):
            return None
        if cur.name in ("body", "table", "tr", "td", "th") and cur.get("bgcolor"):
            c = norm_color(str(cur.get("bgcolor")))
            if c and c != "transparent":
                return c
        cur = cur.parent if isinstance(cur.parent, Tag) else None
    return "ffffff"


def _bg_from_shorthand(v: str | None) -> str | None:
    if not v:
        return None
    # 함수형 색(rgb(...)) 은 공백을 포함할 수 있어 먼저 찾는다
    m = re.search(r"(rgba?|hsla?)\([^)]*\)", v)
    if m and norm_color(m.group(0)):
        return norm_color(m.group(0))
    for tok in v.split():
        if tok.startswith(("url(", "linear-", "radial-", "repeating-")):
            continue
        c = norm_color(tok)
        if c:
            return c
    return None


def _offscreen_reason(st: dict[str, str]) -> str | None:
    pos = st.get("position")
    if pos in ("absolute", "fixed", "relative", "sticky"):
        for k in ("left", "top", "right", "bottom"):
            v = _px(st.get(k))
            if v is not None and v <= -500:
                return f"position:{pos}; {k}:{st[k]}"
        if st.get("inset"):
            if any(v <= -500 for v in _lengths(st["inset"])):
                return f"position:{pos}; inset:{st['inset']}"
    ti = _px(st.get("text-indent"))
    if ti is not None and ti <= -500:
        return f"text-indent:{st['text-indent']}"
    tf = st.get("transform") or ""
    for m in re.finditer(r"translate(?:3d|x|y)?\(([^)]*)\)", tf):
        if any(v <= -500 for v in _lengths(m.group(1))):
            return f"transform:{tf[:60]}"
    if st.get("translate") and any(v <= -500 for v in _lengths(st["translate"])):
        return f"translate:{st['translate']}"
    for k in ("margin-left", "margin-top", "margin-right", "margin-bottom"):
        v = _px(st.get(k))
        if v is not None and v <= -500:
            return f"{k}:{st[k]}"
    if st.get("margin") and any(v <= -500 for v in _lengths(st["margin"])):
        return f"margin:{st['margin']}"
    return None


def hidden_techniques(el: Tag, sheet: dict[int, dict[str, str]]) -> list[tuple[str, str]]:
    """요소 자체의 숨김 기법 목록 [(기법ID, 설명)]."""
    st = effective_style(el, sheet)
    out: list[tuple[str, str]] = []
    if st.get("display") == "none":
        out.append(("display_none", "display:none"))
    if st.get("visibility") in ("hidden", "collapse"):
        out.append(("visibility_hidden", f"visibility:{st['visibility']}"))
    op_raw = st.get("opacity")
    op = _px(op_raw, allow_pct=True)
    if op is not None:
        if "%" in (op_raw or ""):
            op /= 100
        if op <= 0.05:
            out.append(("opacity_zero", f"opacity:{op_raw}"))
    fs_raw = st.get("font-size")
    if not fs_raw and st.get("font"):
        m = re.search(r"(?<![\w.-])(\d+(?:\.\d+)?(?:px|pt|em|rem))", st["font"])
        fs_raw = m.group(1) if m else None
    fs = _px(fs_raw)
    if fs is not None and 0 <= fs <= 1:
        out.append(("font_size_zero", f"font-size:{fs_raw}"))
    reason = _offscreen_reason(st)
    if reason:
        out.append(("offscreen", reason))
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
    cp = st.get("clip-path", "")
    if cp and (cp in ("inset(100%)", "inset(50%)", "circle(0)", "circle(0px)", "circle(0%)", "polygon(0 0, 0 0, 0 0)")
               or re.match(r"inset\(\s*(100|50)%\s*\)", cp)):
        out.append(("tiny_size", f"clip-path:{cp}"))
    color = norm_color(st.get("color"))
    if color:
        if color == "transparent":
            out.append(("color_match", f"color:{st.get('color')}"))
        else:
            bg = background_of(el, sheet)
            if bg is not None and colors_close(color, bg):
                out.append(("color_match", f"글자색 #{color} ≈ 배경색 #{bg}" if color != bg else f"글자색 #{color} = 배경색 #{bg}"))
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
