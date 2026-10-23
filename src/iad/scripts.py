"""스크립트 주입·리다이렉트 탐지: document.write/innerHTML 링크 주입, eval·base64, meta refresh, JS 리다이렉트."""
from __future__ import annotations

import base64
import binascii
import re

from .links import find_urls_in_text, host_of, is_same_site, is_trusted

_B64 = re.compile(r"[\"']([A-Za-z0-9+/]{40,}={0,2})[\"']")
_REDIRECT = re.compile(
    r"(?:window\.|document\.|top\.|self\.)?location(?:\.href|\.replace|\.assign)?\s*(?:=|\()\s*[\"']([^\"']+)[\"']", re.I
)
_WRITE = re.compile(r"document\.write(?:ln)?\s*\(", re.I)
_INNER = re.compile(r"\.(?:innerHTML|outerHTML)\s*(?:=|\+=)", re.I)
_INSERT = re.compile(r"insertAdjacentHTML\s*\(|appendChild\s*\(|createElement\s*\(\s*[\"'](?:a|iframe)[\"']", re.I)
_EVAL = re.compile(r"\beval\s*\(|new\s+Function\s*\(|\batob\s*\(|unescape\s*\(|String\.fromCharCode", re.I)


_B64_BARE = re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$")


def decode_base64_strings(code: str) -> list[str]:
    out: list[str] = []
    cands = [m.group(1) for m in _B64.finditer(code)]
    if _B64_BARE.match(code.strip()):
        cands.append(code.strip())   # 디코딩 결과가 다시 base64 한 덩어리인 경우(겹 인코딩)
    for cand in cands:
        try:
            raw = base64.b64decode(cand + "=" * (-len(cand) % 4), validate=False)
            txt = raw.decode("utf-8", errors="ignore")
            if txt and sum(c.isprintable() for c in txt) / max(len(txt), 1) > 0.8:
                out.append(txt)
        except (binascii.Error, ValueError):
            continue
    return out


_CHARCODE = re.compile(r"String\.fromCharCode\s*\(([^)]*)\)", re.I)
_HEX_ESC = re.compile(r"\\x([0-9a-f]{2})", re.I)
_UNI_ESC = re.compile(r"\\u([0-9a-f]{4})", re.I)
_PCT = re.compile(r"(?:%(?:u[0-9a-f]{4}|[0-9a-f]{2})){4,}", re.I)
_HEXSTR = re.compile(r"[\"']((?:[0-9a-f]{2}){12,})[\"']", re.I)
_ARR_JOIN = re.compile(r"\[((?:\s*[\"'][^\"']{1,12}[\"']\s*,){3,}\s*[\"'][^\"']{1,12}[\"']\s*)\]\s*\.\s*join\s*\(\s*[\"']{2}\s*\)", re.I)


def _printable(txt: str) -> bool:
    return bool(txt) and sum(c.isprintable() for c in txt) / max(len(txt), 1) > 0.8


def decode_charcodes(code: str) -> list[str]:
    out: list[str] = []
    for m in _CHARCODE.finditer(code):
        nums = re.findall(r"\b\d{1,6}\b", m.group(1))
        if len(nums) >= 4:
            try:
                txt = "".join(chr(int(n)) for n in nums if int(n) < 0x110000)
            except ValueError:
                continue
            if _printable(txt):
                out.append(txt)
    return out


def decode_escapes(code: str) -> list[str]:
    out: list[str] = []
    if len(_HEX_ESC.findall(code)) >= 4 or len(_UNI_ESC.findall(code)) >= 4:
        txt = _HEX_ESC.sub(lambda m: chr(int(m.group(1), 16)), code)
        txt = _UNI_ESC.sub(lambda m: chr(int(m.group(1), 16)), txt)
        if txt != code:
            out.append(txt)
    return out


def decode_percent(code: str) -> list[str]:
    from urllib.parse import unquote
    out: list[str] = []
    for m in _PCT.finditer(code):
        raw = m.group(0)
        txt = re.sub(r"%u([0-9a-f]{4})", lambda mm: chr(int(mm.group(1), 16)), raw, flags=re.I)
        txt = unquote(txt)
        if txt != raw and _printable(txt):
            out.append(txt)
    return out


def decode_hexstrings(code: str) -> list[str]:
    out: list[str] = []
    for m in _HEXSTR.finditer(code):
        try:
            txt = bytes.fromhex(m.group(1)).decode("utf-8", errors="ignore")
        except ValueError:
            continue
        if _printable(txt) and re.search(r"[가-힣a-z]{3}", txt, re.I):
            out.append(txt)
    return out


def decode_array_join(code: str) -> list[str]:
    out: list[str] = []
    for m in _ARR_JOIN.finditer(code):
        parts = re.findall(r"[\"']([^\"']{1,12})[\"']", m.group(1))
        txt = "".join(parts)
        if _printable(txt):
            out.append(txt)
    return out


DECODERS = (("base64", decode_base64_strings), ("fromCharCode", decode_charcodes), ("escape", decode_escapes),
            ("percent", decode_percent), ("hex", decode_hexstrings), ("array-join", decode_array_join))


def decode_layers(code: str, depth: int = 3) -> tuple[list[str], list[str]]:
    """여러 인코딩을 최대 depth 겹까지 풀어 (디코딩 텍스트 목록, 사용된 방식 목록)을 돌려준다(재분석용)."""
    found: list[str] = []
    methods: list[str] = []
    frontier = [code or ""]
    for _ in range(depth):
        nxt: list[str] = []
        for text in frontier:
            for name, fn in DECODERS:
                for d in fn(text):
                    if d and d not in found and len(found) < 50:
                        found.append(d)
                        nxt.append(d)
                        if name not in methods:
                            methods.append(name)
        frontier = nxt
        if not frontier:
            break
    return found, methods


def analyze_script(code: str, base_host: str) -> tuple[list[tuple[str, str, float]], str]:
    """[(규칙ID, 설명, 가중치)], 디코딩된 추가 텍스트(키워드·링크 재분석용)."""
    out: list[tuple[str, str, float]] = []
    code = code or ""
    decoded, methods = decode_layers(code)
    extra = "\n".join(decoded)
    all_text = code + "\n" + extra
    urls = [u for u in find_urls_in_text(all_text) if not is_same_site(u, base_host) and not is_trusted(host_of(u))]
    from .keywords import match_keywords_levels
    kw = match_keywords_levels(all_text)
    bad = bool(urls) or any(w >= 2.0 for hs in kw.values() for _, w, _ in hs)   # 비신뢰 외부 URL 또는 불법 키워드가 있어야 '주입'
    has_link_html = bool(re.search(r"<\s*(a|iframe)\b[^>]*href=[\"']?https?://", all_text, re.I)) and bad
    # 정상 사이트의 jQuery 템플릿·분석 스크립트(innerHTML 로 내부 메뉴 생성, 인코딩된 UI 문자열)는 근거 가중치를 낮게 둔다
    if _WRITE.search(code) and (urls or has_link_html):
        out.append(("script.document_write", "document.write 로 외부 링크/iframe 주입", 3.5 if bad else 1.0))
    if _INNER.search(code) and (urls or has_link_html):
        out.append(("script.innerhtml", "innerHTML 로 외부 링크/iframe 주입", 3.5 if bad else 1.0))
    if _INSERT.search(code) and urls:
        out.append(("script.dom_insert", "DOM API 로 외부 링크/iframe 주입", 3))
    if _EVAL.search(code) and bad:
        out.append(("script.eval", "eval/atob/Function 등 난독화 실행", 2))
    if decoded:
        hidden_html = bool(re.search(r"<\s*(a|iframe|div|span)\b", extra, re.I)) and bad
        out.append(("script.base64" if methods == ["base64"] else "script.encoded",
                    f"인코딩 문자열 디코딩({'+'.join(methods)}, {len(decoded)}개)" + (" → 외부 링크/불법 키워드 포함" if bad else ""),
                    (1.5 + (2 if (urls or hidden_html) else 0)) if bad else 0.5))
    for m in _REDIRECT.finditer(code):
        target = m.group(1)
        if target.startswith("http") and not is_same_site(target, base_host):
            out.append(("script.js_redirect", f"JS 리다이렉트 → {target[:80]}", 3))
            break
    return out, extra


def analyze_meta_refresh(content: str, base_host: str) -> list[tuple[str, str, float]]:
    m = re.search(r"url\s*=\s*[\"']?([^\"';]+)", content or "", re.I)
    if not m:
        return []
    target = m.group(1).strip()
    if target.startswith("http") and not is_same_site(target, base_host):
        return [("script.meta_refresh", f"meta refresh 외부 리다이렉트 → {target[:80]}", 3)]
    return []
