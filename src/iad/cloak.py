"""클로킹 탐지(AR1): 같은 URL 을 일반 브라우저 UA 와 검색엔진 봇 UA(Yeti/Googlebot)·네이버 검색 Referer 로 다시 받아
응답 차이를 본다. 봇에게만 보이는 불법 키워드·외부 링크·숨김 요소나 봇/검색 유입에만 일어나는 외부 리다이렉트는
result_extra.json 에 ETC(CLOAKING_*) 로 보고한다. (일반 응답의 DOM 에 없는 요소라 4종(result.json)에는 넣지 않는다.)
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from urllib.parse import urljoin

import requests

from .analyzer import analyze_page
from .crawler import Crawler, decode_html
from .links import host_of, is_same_site, is_trusted
from .models import Evidence, Finding, Page

PROFILES: list[tuple[str, dict[str, str]]] = [
    ("Yeti+네이버검색", {"User-Agent": "Mozilla/5.0 (compatible; Yeti/1.1; +https://naver.me/spd)",
                     "Referer": "https://search.naver.com/search.naver?query=%EA%B3%B5%EC%A7%80%EC%82%AC%ED%95%AD"}),
    ("Googlebot", {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                   "Referer": "https://www.google.com/"}),
]   # Referer 만 다른 경우(검색 유입 클로킹)는 첫 프로필이 함께 덮는다


def _external_hosts(findings: list[Finding]) -> set[str]:
    hosts: set[str] = set()
    for f in findings:
        for u in f.links:
            h = host_of(u)
            if h and not is_trusted(h):
                hosts.add(h)
    return hosts


def check_cloaking(crawler: Crawler, pages: list[Page], normal_findings: list[Finding], base_host: str,
                   max_pages: int, log: Callable[[str], None]) -> list[Finding]:
    """pages 중 최상위(iframe 아님)·오류 없음·얕은 순으로 max_pages 개를 골라 프로필별로 다시 받아 비교한다."""
    out: list[Finding] = []
    cands = [p for p in pages if p.html and not p.error and not p.is_iframe and not p.external]
    # 우선순위: 진입 페이지 → 경로(디렉터리)별 첫 페이지(템플릿 단위 변조를 넓게 훑음) → 나머지 수집 순서
    # 나머지는 디렉터리별로 돌아가며(라운드로빈) 골라 한 게시판이 상한(기본 20쪽)을 독차지하지 않게 한다
    by_dir: dict[str, list[Page]] = {}
    for p in cands:
        by_dir.setdefault(p.url.split("?", 1)[0].rsplit("/", 1)[0], []).append(p)
    queues = list(by_dir.values())
    first = [q.pop(0) for q in queues]
    rest: list[Page] = []
    while any(queues):
        for q in queues:
            if q:
                rest.append(q.pop(0))
    targets = (first + rest)[:max_pages]
    if not targets:
        return out
    by_url: dict[str, list[Finding]] = {}
    for f in normal_findings:
        by_url.setdefault(f.page_url, []).append(f)
    sess = requests.Session()
    sess.headers["Accept-Language"] = "ko-KR,ko;q=0.9"
    n_req = 0
    t_start = crawler.started or time.monotonic()
    for page in targets:
        # 크롤이 max_pages 로 끝난 뒤에도 돌아야 하므로 시간 예산만 본다(페이지 수 상한과 무관)
        if time.monotonic() - t_start > crawler.cfg.time_budget_sec or getattr(crawler, "_stop", False):
            log("클로킹 점검: 시간 예산 소진으로 중단")
            break
        normal = by_url.get(page.report_url, [])
        normal_locs = {f.location for f in normal}
        normal_hosts = _external_hosts(normal)
        for name, headers in PROFILES:
            if crawler.cfg.allowed_hosts is not None and host_of(page.url) not in crawler.cfg.allowed_hosts:
                return out
            hdrs = {"User-Agent": crawler.session.headers.get("User-Agent", ""), **headers}
            try:
                if crawler.cfg.delay > 0:
                    time.sleep(crawler.cfg.delay)
                resp = sess.get(page.url, headers=hdrs, timeout=crawler.cfg.timeout, allow_redirects=False, stream=True)
                n_req += 1
                status = resp.status_code
                loc = resp.headers.get("location", "")
                if 300 <= status < 400:
                    resp.close()
                    target = urljoin(page.url, loc)
                    if loc and not is_same_site(target, base_host):
                        f = _redirect_finding(page, name, status, target)
                        out.append(f)
                        log(f"  클로킹: {name} 요청에만 외부 리다이렉트 {status} → {target[:80]} ({page.url})")
                    continue
                ctype = resp.headers.get("content-type", "")
                if ctype and "html" not in ctype and "xml" not in ctype:
                    resp.close()
                    continue
                resp._content = resp.raw.read(crawler.cfg.max_html_bytes, decode_content=True)  # noqa: SLF001
                html, _enc = decode_html(resp)
            except requests.RequestException:
                continue
            if not html or html == page.html:
                continue
            bot_page = replace(page, html=html, css_texts=list(page.css_texts))
            bot_findings = analyze_page(bot_page, base_host)
            new = [f for f in bot_findings if f.location not in normal_locs]
            new_hosts = _external_hosts(bot_findings) - normal_hosts
            if not new and not new_hosts:
                continue
            for f in new:
                tags = [f"CLOAKING_{c}" for c in f.official] + [f"CLOAKING_{n}" for n in f.extra_names] or ["CLOAKING"]
                f.official = []                      # 봇 전용 DOM 이라 4종(result.json)에는 올리지 않는다
                f.extra_names = list(dict.fromkeys(tags))
                f.evidence.insert(0, Evidence("cloak.bot_only", f"{name} 요청 응답에만 존재하는 요소(일반 UA 응답에는 없음)", 3.0, "hidden"))
                f.score = round(f.score + 3.0, 2)
                f.risk = "높음"
                f.evidence_text = f"[{name} 응답에만 존재] " + f.evidence_text
                out.append(f)
            if new_hosts and not new:
                f = Finding(page_url=page.report_url, css_path="body", tag="body", snippet="", html="", location="body",
                            evidence_text=f"[{name} 응답에만 존재] 외부 도메인 링크 {len(new_hosts)}개: " + ", ".join(sorted(new_hosts))[:400],
                            links=sorted(new_hosts), category="의심 링크", risk="높음", extra_names=["CLOAKING_EXTERNAL_LINKS"])
                f.add("cloak.bot_only_links", f"{name} 요청 응답에만 외부 링크 {len(new_hosts)}개", 4.0, "link")
                f.score = 4.0
                out.append(f)
            log(f"  클로킹: {name} 응답에서만 탐지 {len(new)}건, 신규 외부 도메인 {len(new_hosts)}개 ({page.url})")
    log(f"클로킹 점검: 페이지 {len(targets)}개 × 프로필 {len(PROFILES)} = 요청 {n_req}회, 탐지 {len(out)}건")
    return out


def _redirect_finding(page: Page, name: str, status: int, target: str) -> Finding:
    f = Finding(page_url=page.report_url, css_path="html", tag="html", snippet="", html="", location="html",
                evidence_text=f"[{name} 요청에만] HTTP {status} 리다이렉트 → {target}", links=[target],
                category="의심 링크", risk="높음", extra_names=["CLOAKING_REDIRECT"])
    f.add("cloak.redirect", f"{name} 요청에만 외부 리다이렉트 {status} → {target[:80]}", 5.0, "script")
    f.score = 5.0
    return f
