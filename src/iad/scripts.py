"""스크립트 주입·리다이렉트 탐지: document.write/innerHTML 링크 주입, eval·base64, meta refresh, JS 리다이렉트."""
from __future__ import annotations

import base64
import binascii
import re

from .links import find_urls_in_text, is_same_site

_B64 = re.compile(r"[\"']([A-Za-z0-9+/]{40,}={0,2})[\"']")
_REDIRECT = re.compile(
    r"(?:window\.|document\.|top\.|self\.)?location(?:\.href|\.replace|\.assign)?\s*(?:=|\()\s*[\"']([^\"']+)[\"']", re.I
)
_WRITE = re.compile(r"document\.write(?:ln)?\s*\(", re.I)
_INNER = re.compile(r"\.(?:innerHTML|outerHTML)\s*(?:=|\+=)", re.I)
_INSERT = re.compile(r"insertAdjacentHTML\s*\(|appendChild\s*\(|createElement\s*\(\s*[\"'](?:a|iframe)[\"']", re.I)
_EVAL = re.compile(r"\beval\s*\(|new\s+Function\s*\(|\batob\s*\(|unescape\s*\(|String\.fromCharCode", re.I)


def decode_base64_strings(code: str) -> list[str]:
    out: list[str] = []
    for m in _B64.finditer(code):
        try:
            raw = base64.b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4), validate=False)
            txt = raw.decode("utf-8", errors="ignore")
            if txt and sum(c.isprintable() for c in txt) / max(len(txt), 1) > 0.8:
                out.append(txt)
        except (binascii.Error, ValueError):
            continue
    return out


def analyze_script(code: str, base_host: str) -> tuple[list[tuple[str, str, float]], str]:
    """[(규칙ID, 설명, 가중치)], 디코딩된 추가 텍스트(키워드 검사용)."""
    out: list[tuple[str, str, float]] = []
    code = code or ""
    decoded = decode_base64_strings(code)
    extra = "\n".join(decoded)
    all_text = code + "\n" + extra
    urls = [u for u in find_urls_in_text(all_text) if not is_same_site(u, base_host)]
    has_link_html = bool(re.search(r"<\s*(a|iframe)\b", all_text, re.I))
    if _WRITE.search(code) and (urls or has_link_html):
        out.append(("script.document_write", "document.write 로 외부 링크/iframe 주입", 3.5))
    if _INNER.search(code) and (urls or has_link_html):
        out.append(("script.innerhtml", "innerHTML 로 외부 링크/iframe 주입", 3.5))
    if _INSERT.search(code) and urls:
        out.append(("script.dom_insert", "DOM API 로 외부 링크/iframe 주입", 3))
    if _EVAL.search(code):
        out.append(("script.eval", "eval/atob/Function 등 난독화 실행", 2))
    if decoded:
        out.append(("script.base64", f"base64 문자열 {len(decoded)}개 디코딩됨", 1.5 + (2 if urls else 0)))
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
