"""선택적 렌더링(playwright, channel="msedge"): 정적 DOM 과 렌더 DOM 의 외부 링크 차이로 동적 주입 탐지, 요소 스크린샷.

playwright 또는 Edge 가 없으면 ImportError/Exception 을 올리고 호출 측에서 조용히 건너뛴다.
"""
from __future__ import annotations

import base64
from collections.abc import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .analyzer import PageAnalyzer
from .links import analyze_link, host_of, is_same_site, is_trusted
from .models import Finding, Page

MAX_RENDER_PAGES = 30


def render_compare(res, base_host: str, cfg, log: Callable[[str], None]) -> tuple[list[Finding], int]:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    extra: list[Finding] = []
    shots = 0
    targets = [p for p in res.pages if p.html and not p.error and not p.is_iframe][:MAX_RENDER_PAGES]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        by_url = {p.url: p for p in targets}
        want_shots = [f for f in res.findings if f.page_url in by_url and not f.is_iframe and f.tag not in ("#comment", "script", "meta")]
        for p in targets:
            try:
                page.goto(p.url, wait_until="networkidle", timeout=15000)
                rendered = page.content()
            except Exception as e:
                log(f"  렌더 실패 {p.url}: {e.__class__.__name__}")
                continue
            static_links = _ext_links(p.html, p.url, base_host)
            dyn_links = _ext_links(rendered, p.url, base_host) - static_links
            if dyn_links:
                rp = Page(url=p.url, html=rendered, depth=p.depth, top_url=p.top_url, frame_prefix=p.frame_prefix)
                an = PageAnalyzer(rp, base_host)
                soup = an.soup
                for a in soup.find_all("a", href=True):
                    href = urljoin(p.url, str(a["href"]))
                    if href in dyn_links:
                        f = an._new(a)
                        f.add("script.dynamic_injection", "렌더 후에만 존재하는 외부 링크(동적 주입)", 3.5, "script")
                        f.techniques.append("dynamic_injection")
                        f.extra_names.append("DYNAMIC_INJECTION")
                        f.links.append(href)
                        for rule, detail, w in analyze_link(href, a.get_text(" "), base_host):
                            f.add(rule, detail, w, "link")
                        cats, _ = an._add_keywords(f, a.get_text(" "), allow_whitelist=False)
                        an._finalize(f, cats)
                extra.extend(an.findings)
                log(f"  동적 주입 링크 {len(dyn_links)}개: {p.url}")
            for f in [x for x in want_shots if x.page_url == p.url][:20]:
                try:
                    loc = page.locator(f.css_path).first
                    if loc.count():
                        png = loc.screenshot(timeout=3000)
                        f.screenshot = "data:image/png;base64," + base64.b64encode(png).decode()
                        shots += 1
                except Exception:
                    continue
        browser.close()
    return extra, shots


def _ext_links(html: str, url: str, base_host: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    out = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(url, str(a["href"]))
        h = host_of(href)
        if h and not is_same_site(href, base_host) and not is_trusted(h):
            out.add(href)
    return out


def render_available() -> bool:
    """playwright 가 import 되는 배포본인지(정적 빌드면 False)."""
    try:
        import importlib.util
        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False
