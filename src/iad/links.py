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


_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def is_same_site(url: str, base_host: str) -> bool:
    h = host_of(url)
    if not h:
        return False
    if h in _LOOPBACK and base_host in _LOOPBACK:
        return True   # 로컬 테스트베드: 127.0.0.1 과 localhost 를 같은 사이트로(외부 CSS·링크 수집 누락 방지)
    return h == base_host or h.endswith("." + base_host) or base_host.endswith("." + h)


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


# ---------- IDN 호모그래프 ----------
_CYR = re.compile("[\u0400-\u04ff]")
_GRK = re.compile("[\u0370-\u03ff]")
_LAT = re.compile("[a-z]")
_HOSTLIKE = re.compile(r"(?<![\w@/])((?:[\w\u0400-\u04ff\u0370-\u03ff-]{1,63}\.)+[a-z\u0400-\u04ff\u0370-\u03ff\uac00-\ud7a3]{2,24})(?![\w])", re.I)


def _decode_punycode(host: str) -> str:
    if "xn--" not in host:
        return host
    try:
        return host.encode("ascii").decode("idna")
    except (UnicodeError, ValueError):
        return host


def is_idn_homograph(host: str) -> bool:
    """도메인 레이블에 라틴처럼 보이는 키릴·그리스 문자가 라틴과 섞여 있으면(레이블 안 혼용, 또는 비라틴 레이블 + 라틴 TLD) True.
    호스트 전체가 한 스크립트(москва.рф, παράδειγμα.ελ)거나 한글 IDN(행복시.한국)이면 False."""
    h = _decode_punycode((host or "").lower().strip("."))
    if not h or "." not in h:
        return False
    labels = h.split(".")
    has_lat = any(_LAT.search(l) for l in labels)
    has_conf = any(_CYR.search(l) or _GRK.search(l) for l in labels)
    return has_lat and has_conf


def idn_homograph_hosts(text: str, hosts: list[str]) -> list[str]:
    """href 호스트 목록 + 텍스트 속 도메인 토큰 중 IDN 호모그래프인 것."""
    out: list[str] = []
    for h in hosts:
        if h and is_idn_homograph(h) and h not in out:
            out.append(h)
    for m in _HOSTLIKE.finditer(text or ""):
        cand = m.group(1).lower()
        if is_idn_homograph(cand) and cand not in out:
            out.append(cand)
    return out
