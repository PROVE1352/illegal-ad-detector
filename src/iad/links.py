"""링크 휴리스틱: 의심 TLD, 숫자 도메인, 단축 URL, 텔레그램·오픈채팅, 앵커-도메인 불일치."""
from __future__ import annotations

import re
from urllib.parse import urlparse

SUSPICIOUS_TLDS = {
    "top", "xyz", "icu", "club", "vip", "win", "bet", "casino", "site", "online", "live", "click", "buzz",
    "cc", "tk", "ml", "ga", "cf", "gq", "pw", "ws", "cyou", "rest", "fun", "lol", "monster", "quest",
    "sbs", "bar", "cam", "sex", "xxx", "adult", "porn", "poker", "surf", "cfd", "boats", "hair", "mom",
    "beauty", "skin", "makeup", "zip", "mov", "wang", "men", "loan", "loans", "cash", "money",
}
SHORTENERS = {
    "bit.ly", "han.gl", "me2.do", "vo.la", "url.kr", "tinyurl.com", "goo.gl", "t.co", "is.gd", "cutt.ly",
    "buly.kr", "zrr.kr", "lrl.kr", "c11.kr", "shorturl.at", "rb.gy", "ouo.io", "abit.ly", "muz.so", "asq.kr",
    "tiny.cc", "u.to", "ow.ly", "soo.gd", "hoy.kr", "wo.to", "my.kr", "go.kr.ms",
}
MESSENGERS = ("t.me", "telegram.me", "telegram.dog", "open.kakao.com", "line.me", "wa.me", "api.whatsapp.com")
TRUSTED_SUFFIXES = (".go.kr", ".or.kr", ".ac.kr", ".re.kr", ".mil.kr", ".hs.kr", ".ms.kr", ".es.kr", ".sc.kr",
                    "youtube.com", "youtu.be", "naver.com", "daum.net", "kakao.com", "google.com", "facebook.com",
                    "instagram.com", "twitter.com", "x.com", "blog.naver.com", "gov.kr", "korea.kr")
_DOMAIN_IN_TEXT = re.compile(r"\b((?:[a-z0-9\-]+\.)+(?:kr|com|net|org|" + "|".join(sorted(SUSPICIOUS_TLDS)) + r"))\b", re.I)


def host_of(url: str) -> str:
    try:
        h = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return h.lower().removeprefix("www.")


def registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and parts[-1] == "kr" and parts[-2] in ("co", "or", "go", "ac", "re", "ne", "pe", "ms", "hs", "es", "sc"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def is_trusted(host: str) -> bool:
    return any(host == s.lstrip(".") or host.endswith(s) for s in TRUSTED_SUFFIXES)


def is_same_site(url: str, base_host: str) -> bool:
    h = host_of(url)
    return bool(h) and (h == base_host or h.endswith("." + base_host) or base_host.endswith("." + h))


def analyze_link(href: str, anchor_text: str, base_host: str) -> list[tuple[str, str, float]]:
    """[(규칙ID, 설명, 가중치)]"""
    out: list[tuple[str, str, float]] = []
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return out
    host = host_of(href)
    if not host or is_same_site(href, base_host):
        return out
    if is_trusted(host):
        return out
    reg = registrable(host)
    tld = host.rsplit(".", 1)[-1]
    if tld in SUSPICIOUS_TLDS:
        out.append(("link.suspicious_tld", f"의심 TLD .{tld} ({host})", 2.5))
    label = reg.split(".")[0]
    digits = sum(ch.isdigit() for ch in label)
    if label and (digits >= 3 or (len(label) >= 4 and digits / len(label) >= 0.4)):
        out.append(("link.numeric_domain", f"숫자가 많은 도메인 ({host})", 2))
    if reg in SHORTENERS or host in SHORTENERS:
        out.append(("link.shortener", f"단축 URL ({host})", 2))
    if host in MESSENGERS or any(host.endswith("." + m) for m in MESSENGERS):
        out.append(("link.messenger", f"텔레그램/오픈채팅 링크 ({host})", 3))
    m = _DOMAIN_IN_TEXT.search(anchor_text or "")
    if m:
        text_host = m.group(1).lower().removeprefix("www.")
        if registrable(text_host) != reg:
            w = 3.5 if is_trusted(text_host) else 2.5
            out.append(("link.anchor_mismatch", f"앵커 텍스트 도메인({text_host}) ≠ 실제 링크({host})", w))
    if len(host) > 40:
        out.append(("link.long_host", f"비정상적으로 긴 호스트 ({host[:40]}…)", 1))
    return out


def find_urls_in_text(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\"'<>)\]]+", text or "")
