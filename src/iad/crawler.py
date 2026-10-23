"""동일 도메인 BFS 크롤러: 게시판 목록/상세/페이지네이션, iframe 추적, robots.txt 옵션, EUC-KR 처리, 시간 예산."""
from __future__ import annotations

import heapq
import re
import time
import urllib.robotparser as robotparser
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .links import LOOPBACK, host_of, is_same_site
from .models import Page

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IllegalAdDetector/0.1 (+public-site-audit)"
SKIP_EXT = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|svg|ico|bmp|pdf|zip|7z|rar|hwp|hwpx|doc|docx|xls|xlsx|ppt|pptx|"
                      r"mp3|mp4|avi|mov|wmv|css|js|json|xml|rss|exe|apk|txt|csv|woff2?|ttf|eot)(?:\?|#|$)", re.I)
SKIP_SEGMENTS = {"logout", "login", "signin", "signout", "download", "filedown", "filedownload", "print", "printpage",
                 "file", "files", "attach", "attachfile"}
SKIP_QUERY_HINTS = re.compile(r"(?:^|[?&])(?:mode|cmd|act|action)=(?:download|print|logout|login|filedown)", re.I)
# 탐색 우선순위 패턴(게시판 상세 > 목록·페이지네이션 > 게시판 영역 > 그 외)
DETAIL_HINTS = re.compile(r"(?:view|read|detail|article|content|cont|show)(?:[./?_-]|$)|(?:[?&](?:nttId|ntt_id|idx|seq|no|id|articleNo|"
                          r"bbsSeq|boardSeq|postId|post_id|docId|dataSid|nttSn|bIdx|b_idx|wr_id|num)=)", re.I)
PAGING_HINTS = re.compile(r"[?&](?:page|pageIndex|pageNo|pageNum|pageunit|cpage|currentPage|curPage|p|pg|start|offset|pageNumber)=\d+", re.I)
BOARD_HINTS = re.compile(r"(?:board|bbs|notice|news|community|forum|comment|reply|cmt|qna|faq|free|guest|post|article|list)", re.I)
_PATH_IN_JS = re.compile(r"[\"'](/[\w\-./%]+\.(?:do|jsp|php|html?|asp|aspx|action|cgi)(?:\?[^\"'\s<>]*)?)[\"']")
_URL_IN_HANDLER = re.compile(r"(?:location(?:\.href|\.replace|\.assign)?\s*(?:=|\()|window\.open\s*\(|open\s*\()\s*[\"']([^\"']+)[\"']", re.I)
_ANY_PATH_IN_HANDLER = re.compile(r"[\"']((?:https?://|/)[^\"'\s<>]+)[\"']")


@dataclass
class CrawlConfig:
    depth: int = 3
    max_pages: int = 300
    delay: float = 0.3
    timeout: float = 10.0
    respect_robots: bool = False
    follow_external_iframes: bool = True
    time_budget_sec: float = 20 * 60     # 요강 타임아웃 30분 → 기본 20분에 중단
    max_html_bytes: int = 3_000_000
    allowed_hosts: tuple[str, ...] | None = None   # 설정 시 이 호스트들만 요청(하네스용 오프라인 가드)
    cloak_pages: int = 40                  # 클로킹 점검(봇 UA·네이버 Referer 재요청)할 최상위 페이지 수(0=끄기), 페이지당 2요청
    fetch_css: bool = True                 # <link rel=stylesheet>(동일 사이트) 수집해 클래스 규칙 해석
    max_css_files: int = 40                # 사이트 전체에서 받을 고유 CSS 파일 수 상한
    max_css_bytes: int = 1_000_000
    ocr: bool = True                       # Windows 내장 OCR 로 배너 이미지 글자 판정(Windows 외·엔진 없음은 자동 생략, ETC 전용)
    browser: bool = True                   # OS 의 Edge/Chrome headless --dump-dom 으로 의심 스크립트 페이지 JS 실행 비교(없으면 자동 생략, ETC 전용)


def normalize_url(url: str) -> str:
    """요강 비교 규칙: #이하 제거, 쿼리 순서 무시, 끝 / 무시, http/https 무시(키로만)."""
    p = urlparse(url)
    query = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
    path = p.path.rstrip("/") or "/"
    return urlunparse(("http", (p.hostname or "").lower(), path, "", query, ""))


def decode_html(resp: requests.Response) -> tuple[str, str]:
    raw = resp.content
    enc = None
    ctype = resp.headers.get("content-type", "")
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    if m:
        enc = m.group(1)
    if not enc:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w\-]+)", raw[:4096], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    cands = []
    if enc:
        e = enc.lower()
        if e in ("euc-kr", "ks_c_5601-1987", "ksc5601", "cp949", "x-windows-949", "ms949"):
            e = "cp949"
        cands.append(e)
    cands += ["utf-8", "cp949"]
    for e in cands:
        try:
            return raw.decode(e), e
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8?"


class Crawler:
    def __init__(self, start_url: str, config: CrawlConfig | None = None,
                 log: Callable[[str], None] | None = None) -> None:
        self.start_url = start_url
        self.cfg = config or CrawlConfig()
        self.log = log or (lambda m: None)
        self.base_host = host_of(start_url)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.session.headers["Accept-Language"] = "ko-KR,ko;q=0.9"
        self.seen: set[str] = set()
        self.pages_fetched = 0
        self.started = 0.0
        self.stopped_reason = ""
        self._stop = False
        self.css_cache: dict[str, str | None] = {}   # 스타일시트 URL → 본문(실패면 None)
        self.post_jobs: dict[str, tuple[str, dict[str, str]]] = {}   # 표시 URL → (action, POST data)
        self._counter = 0
        self._entry_dir = urlparse(start_url).path.rsplit("/", 1)[0] + "/"
        self.robots: robotparser.RobotFileParser | None = None
        if self.cfg.respect_robots:
            self.robots = robotparser.RobotFileParser()
            try:
                self.robots.set_url(urljoin(start_url, "/robots.txt"))
                self.robots.read()
            except Exception:
                self.robots = None

    def stop(self) -> None:
        self._stop = True

    def _allowed(self, url: str) -> bool:
        if self.robots is None:
            return True
        try:
            return self.robots.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def _budget_left(self) -> bool:
        if self._stop:
            self.stopped_reason = "사용자 중단"
            return False
        if time.monotonic() - self.started > self.cfg.time_budget_sec:
            self.stopped_reason = f"시간 예산 {int(self.cfg.time_budget_sec)}초 초과로 중단"
            return False
        if self.pages_fetched >= self.cfg.max_pages:
            self.stopped_reason = f"최대 페이지 {self.cfg.max_pages} 도달"
            return False
        return True

    def fetch(self, url: str, depth: int, parent: str | None = None, is_iframe: bool = False,
              external: bool = False, top_url: str | None = None, frame_prefix: str = "",
              post: tuple[str, dict[str, str]] | None = None) -> Page:
        """post=(action, data) 면 action 에 POST 하고(전자정부 폼 게시판), page.url 은 입력 url(action?식별파라미터 표기)을 유지한다."""
        page = Page(url=url, html="", depth=depth, parent_url=parent, is_iframe=is_iframe, external=external,
                    top_url=top_url, frame_prefix=frame_prefix)
        if self.cfg.allowed_hosts is not None and host_of(url) not in self.cfg.allowed_hosts:
            page.error = "허용되지 않은 호스트(오프라인 가드)"
            return page
        try:
            if self.pages_fetched > 0 and self.cfg.delay > 0:
                time.sleep(self.cfg.delay)
            if post is not None:
                resp = self.session.post(post[0], data=post[1], timeout=self.cfg.timeout, allow_redirects=True, stream=True)
                if resp.status_code >= 400:   # POST 를 안 받는 서버면 같은 파라미터로 GET 재시도
                    resp.close()
                    resp = self.session.get(url, timeout=self.cfg.timeout, allow_redirects=True, stream=True)
            else:
                resp = self.session.get(url, timeout=self.cfg.timeout, allow_redirects=True, stream=True)
            self.pages_fetched += 1
            page.status = resp.status_code
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "xml" not in ctype and ctype:
                resp.close()
                page.error = f"HTML 아님 ({ctype})"
                return page
            resp._content = resp.raw.read(self.cfg.max_html_bytes, decode_content=True)  # noqa: SLF001
            page.html, page.encoding = decode_html(resp)
            if post is None:
                page.url = resp.url or url
        except requests.RequestException as e:
            page.error = f"요청 실패: {e.__class__.__name__}: {e}"
            self.pages_fetched += 1
        return page

    # ---------- 외부 CSS ----------
    _IMPORT = re.compile(r"@import\s+(?:url\()?\s*[\"']?([^\"')\s;]+)[\"']?\s*\)?[^;]*;", re.I)

    def _fetch_css(self, url: str) -> str | None:
        if url in self.css_cache:
            return self.css_cache[url]
        if len(self.css_cache) >= self.cfg.max_css_files:   # 실패한 시도도 세어 깨진 링크가 많은 사이트에서 타임아웃이 쌓이지 않게
            return None
        if self.cfg.allowed_hosts is not None and host_of(url) not in self.cfg.allowed_hosts:
            return None
        text: str | None = None
        try:
            resp = self.session.get(url, timeout=self.cfg.timeout, allow_redirects=True, stream=True)
            if resp.status_code == 200:
                raw = resp.raw.read(self.cfg.max_css_bytes, decode_content=True)
                enc = "utf-8"
                m = re.search(r"charset=([\w\-]+)", resp.headers.get("content-type", ""), re.I)
                if m:
                    enc = m.group(1)
                try:
                    text = raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    text = raw.decode("utf-8", errors="replace")
            resp.close()
        except requests.RequestException:
            text = None
        self.css_cache[url] = text
        return text

    def stylesheets(self, page: Page, soup: BeautifulSoup) -> list[str]:
        """문서의 <link rel=stylesheet>(동일 사이트만) + 그 안의 @import(1단계) 본문을 문서 순서대로."""
        if not self.cfg.fetch_css:
            return []
        out: list[str] = []
        for ln in soup.find_all("link", href=True):
            rel = " ".join(ln.get("rel") or []).lower() if isinstance(ln.get("rel"), list) else str(ln.get("rel", "")).lower()
            if "stylesheet" not in rel:
                continue
            media = str(ln.get("media", "")).lower()
            if media and "print" in media and "screen" not in media and "all" not in media:
                continue
            href = urljoin(page.url, str(ln["href"]).strip())
            if not href.startswith(("http://", "https://")):
                continue
            h = host_of(href)
            # 동일 사이트 CSS 만. 예외: 허용 호스트 목록(하네스)과 로컬 루프백끼리(127.0.0.1 ↔ localhost 로 적힌 href)
            if not is_same_site(href, self.base_host) and not (
                    (self.cfg.allowed_hosts is not None and h in self.cfg.allowed_hosts)
                    or (h in LOOPBACK and self.base_host in LOOPBACK)):
                continue
            css = self._fetch_css(href)
            if not css:
                continue
            for m in self._IMPORT.finditer(css[:20000]):
                sub = urljoin(href, m.group(1))
                if is_same_site(sub, self.base_host):
                    sub_css = self._fetch_css(sub)
                    if sub_css:
                        out.append(sub_css)
            out.append(css)
        return out

    @staticmethod
    def _handler_urls(code: str) -> list[str]:
        """onclick / javascript: 핸들러 안에서 이동 대상으로 보이는 URL·경로를 뽑는다."""
        out = [m.group(1) for m in _URL_IN_HANDLER.finditer(code)]
        if not out:
            out = [m.group(1) for m in _ANY_PATH_IN_HANDLER.finditer(code)]
        return [u for u in out if u and not u.startswith(("#", "javascript:", "mailto:", "tel:"))]

    def extract_links(self, page: Page, soup: BeautifulSoup) -> Iterator[str]:
        for a in soup.find_all(["a", "area"], href=True):
            href = str(a["href"]).strip()
            if not href or href.startswith(("#", "mailto:", "tel:")):
                continue
            if href.lower().startswith("javascript:"):
                for u in self._handler_urls(href):
                    yield urljoin(page.url, u)
                continue
            yield urljoin(page.url, href)
        for el in soup.find_all(attrs={"onclick": True}):
            for u in self._handler_urls(str(el["onclick"])):
                yield urljoin(page.url, u)
        for attr in ("data-href", "data-url", "data-link"):
            for el in soup.find_all(attrs={attr: True}):
                v = str(el[attr]).strip()
                if v and not v.startswith(("#", "javascript:")):
                    yield urljoin(page.url, v)
        for ln in soup.find_all("link", href=True):
            rel = " ".join(ln.get("rel") or []).lower() if isinstance(ln.get("rel"), list) else str(ln.get("rel", "")).lower()
            if rel in ("next", "prev", "canonical"):
                yield urljoin(page.url, str(ln["href"]))
        for m in soup.find_all("meta"):
            if str(m.get("http-equiv", "")).lower() == "refresh":
                mm = re.search(r"url\s*=\s*[\"']?([^\"';]+)", str(m.get("content", "")), re.I)
                if mm:
                    yield urljoin(page.url, mm.group(1).strip())
        # 인라인 스크립트 안의 동일 사이트 경로(JS 로만 이동하는 게시판·댓글 목록 URL), 페이지당 20개까지
        n = 0
        for sc in soup.find_all("script"):
            for mm in _PATH_IN_JS.finditer(sc.get_text() or ""):
                yield urljoin(page.url, mm.group(1))
                n += 1
                if n >= 20:
                    break
            if n >= 20:
                break

    # ---------- 폼(POST) 게시판: onclick="fn_egov_select('1024')" → 스크립트 함수 본문의 '폼 필드 = 인자' 대입 + <form action> 재현 ----------
    _CALL = re.compile(r"([A-Za-z_$][\w$]*)\s*\(([^()]*)\)")
    _ARG = re.compile(r"[\"']([^\"']*)[\"']|(-?\d+)")

    @staticmethod
    def _function_body(scripts: str, name: str) -> tuple[list[str], str] | None:
        m = re.search(r"function\s+" + re.escape(name) + r"\s*\(([^)]*)\)\s*\{", scripts) or \
            re.search(re.escape(name) + r"\s*=\s*function\s*\(([^)]*)\)\s*\{", scripts)
        if not m:
            return None
        params = [p.strip() for p in m.group(1).split(",") if p.strip()]
        i, depth = m.end(), 1
        while i < len(scripts) and depth:
            depth += scripts[i] == "{"
            depth -= scripts[i] == "}"
            i += 1
        return params, scripts[m.end():i - 1]

    def extract_form_posts(self, page: Page, soup: BeautifulSoup) -> list[tuple[str, str, dict[str, str], str]]:
        """[(표시 URL, action URL, 데이터, 메서드)] — 핸들러 호출 인자를 함수 본문의 폼 필드 대입에 대응시켜 요청을 재현한다."""
        forms: list[tuple[str, str, str, dict[str, str]]] = []   # (name/id, method, action, inputs)
        for fm in soup.find_all("form"):
            inputs = {str(i.get("name")): str(i.get("value", "")) for i in fm.find_all(["input", "select", "textarea"]) if i.get("name")}
            forms.append((str(fm.get("name") or fm.get("id") or ""), str(fm.get("method", "get")).lower(),
                          urljoin(page.url, str(fm.get("action") or page.url)), inputs))
        scripts = "\n".join(sc.get_text() or "" for sc in soup.find_all("script"))
        if not scripts.strip():
            return []
        handlers: list[str] = [str(el["onclick"]) for el in soup.find_all(attrs={"onclick": True})]
        for a in soup.find_all("a", href=True):
            h = str(a["href"]).strip()
            if h.lower().startswith("javascript:"):
                handlers.append(h[11:])
        out: list[tuple[str, str, dict[str, str], str]] = []
        seen: set[str] = set()
        cache: dict[str, tuple[list[str], str] | None] = {}
        for hd in handlers[:400]:
            for m in self._CALL.finditer(hd):
                name, raw_args = m.group(1), m.group(2)
                if name in ("return", "if", "alert", "confirm", "void", "open", "focus"):
                    continue
                args = [(g1 if g1 is not None else g2) for g1, g2 in
                        ((mm.group(1), mm.group(2)) for mm in self._ARG.finditer(raw_args))]
                if not args:
                    continue
                if name not in cache:
                    cache[name] = self._function_body(scripts, name)
                fb = cache[name]
                if not fb:
                    continue
                params, body = fb
                pmap = {p: a for p, a in zip(params, args)}
                # location.href = "/board/view.do?nttId=" + nttId  → GET
                gm = re.search(r"[\"']([^\"']*[?&][\w.]+=)[\"']\s*\+\s*(\w+)", body)
                if gm and gm.group(2) in pmap:
                    u = urljoin(page.url, gm.group(1) + str(pmap[gm.group(2)]))
                    if u not in seen:
                        seen.add(u)
                        out.append((u, u, {}, "get"))
                    continue
                assigns: dict[str, str] = {}
                for fm_ in re.finditer(r"(\w+)\.value\s*=\s*(\w+)\s*;", body):
                    if fm_.group(2) in pmap:
                        assigns[fm_.group(1)] = str(pmap[fm_.group(2)])
                for fm_ in re.finditer(r"\$\([\"']#?(\w+)[\"']\)\.val\(\s*(\w+)\s*\)", body):
                    if fm_.group(2) in pmap:
                        assigns[fm_.group(1)] = str(pmap[fm_.group(2)])
                for fm_ in re.finditer(r"\[name=[\"']?(\w+)[\"']?\]\s*\)?\.val\(\s*(\w+)\s*\)", body):
                    if fm_.group(2) in pmap:
                        assigns[fm_.group(1)] = str(pmap[fm_.group(2)])
                if not assigns or not re.search(r"\.submit\s*\(|\.trigger\(\s*[\"']submit", body):
                    continue
                fname = None
                fm2 = re.search(r"document\.(\w+)\.\w+\.value|document\.(\w+)\.submit|\$\([\"']#(\w+)[\"']\)\.submit|getElementById\([\"'](\w+)[\"']\)", body)
                if fm2:
                    fname = next((g for g in fm2.groups() if g), None)
                form = next((f for f in forms if fname and f[0] == fname), None) or (forms[0] if forms else None)
                am = re.search(r"\.action\s*=\s*[\"']([^\"']+)[\"']|attr\(\s*[\"']action[\"']\s*,\s*[\"']([^\"']+)[\"']", body)
                action = urljoin(page.url, (am.group(1) or am.group(2))) if am else (form[2] if form else None)
                if not action or not is_same_site(action, self.base_host):
                    continue
                mm_ = re.search(r"\.method\s*=\s*[\"'](\w+)[\"']", body)
                method = (mm_.group(1) if mm_ else (form[1] if form else "post")).lower()
                data = dict(form[3]) if form else {}
                data.update(assigns)
                display = action.split("#", 1)[0] + ("&" if "?" in action else "?") + urlencode(sorted(assigns.items()))
                if display in seen:
                    continue
                seen.add(display)
                out.append((display, action, data, method))
        return out

    @staticmethod
    def _skip_link(link: str) -> bool:
        p = urlparse(link)
        segs = {seg.lower().split(".")[0] for seg in p.path.split("/") if seg}   # 'login.do' → 'login'
        if segs & SKIP_SEGMENTS:
            return True
        if SKIP_QUERY_HINTS.search("?" + p.query):
            return True
        return False

    def _priority(self, link: str, entry_dir: str) -> int:
        p = urlparse(link)
        same_dir = p.path.startswith(entry_dir)
        full = p.path + ("?" + p.query if p.query else "")
        if same_dir and DETAIL_HINTS.search(full):
            return 0
        if same_dir:
            return 1 if PAGING_HINTS.search(full) else 2
        if DETAIL_HINTS.search(full) or PAGING_HINTS.search(full):
            return 3
        return 4 if BOARD_HINTS.search(full) else 5

    def extract_frames(self, page: Page, soup: BeautifulSoup) -> Iterator[tuple[str, str]]:
        """(절대 src, location 접두어 세그먼트)"""
        for fr in soup.find_all(["iframe", "frame"]):
            src = str(fr.get("src") or "").strip()
            if (not src or src.startswith(("about:", "javascript:", "data:"))) and fr.get("data-src"):
                src = str(fr["data-src"]).strip()   # 지연 로딩 iframe
            if not src or src.startswith(("about:", "javascript:", "data:")):
                continue
            abs_src = urljoin(page.url, src)
            yield abs_src, f'iframe[src="{abs_src}"] >>> '

    def _enqueue(self, queue: list, link: str, depth: int, parent: str) -> None:
        if not link.startswith(("http://", "https://")) or SKIP_EXT.search(link) or self._skip_link(link):
            return
        if not is_same_site(link, self.base_host):
            return
        key = normalize_url(link)
        if key in self.seen:
            return
        self.seen.add(key)
        self._counter += 1
        # 우선순위 큐: (게시판 상세 > 목록·페이지네이션 > 진입 경로 > 다른 영역 상세 > 게시판스러운 영역 > 그 외), 같은 순위면 얕은 깊이·발견 순서
        heapq.heappush(queue, (self._priority(link, self._entry_dir), depth, self._counter, link.split("#", 1)[0], parent))

    def crawl(self) -> Iterator[Page]:
        self.started = time.monotonic()
        self._counter = 0
        self._entry_dir = urlparse(self.start_url).path.rsplit("/", 1)[0] + "/"
        queue: list[tuple[int, int, int, str, str | None]] = [(0, 0, 0, self.start_url, None)]
        self.seen.add(normalize_url(self.start_url))
        while queue and self._budget_left():
            _prio, depth, _n, url, parent = heapq.heappop(queue)
            if not self._allowed(url):
                self.log(f"robots.txt 차단: {url}")
                continue
            job = self.post_jobs.get(url)
            page = self.fetch(url, depth, parent, post=job)
            self.log(f"[{self.pages_fetched}/{self.cfg.max_pages}] d{depth} {page.status} {'POST ' if job else ''}{url}" +
                     (f"  ({page.error})" if page.error else ""))
            soup = BeautifulSoup(page.html, "lxml") if (page.html and not page.error) else None
            if soup is not None:
                page.css_texts = self.stylesheets(page, soup)   # 분석(yield 뒤)이 외부 CSS 를 쓰도록 먼저 수집
            yield page
            if soup is None:
                continue
            # iframe: 같은 도메인은 수집+링크 추적, 외부는 1단계 수집만(플래그)
            yield from self._crawl_frames(page, soup, depth, queue)
            if depth >= self.cfg.depth:
                continue
            for link in self.extract_links(page, soup):
                self._enqueue(queue, link, depth + 1, page.url)
            try:
                for display, action, data, method in self.extract_form_posts(page, soup):
                    if method == "post" and data:
                        self.post_jobs.setdefault(display, (action, data))
                    self._enqueue(queue, display, depth + 1, page.url)
            except Exception as e:  # 폼 재현 실패는 기존 수집에 영향 없음
                self.log(f"  폼 게시판 재현 생략: {e.__class__.__name__}")
        if self.stopped_reason:
            self.log(self.stopped_reason)

    def _crawl_frames(self, page: Page, soup: BeautifulSoup, depth: int, queue: list,
                      nest: int = 0) -> Iterator[Page]:
        if nest > 3:
            return
        for abs_src, seg in self.extract_frames(page, soup):
            if SKIP_EXT.search(abs_src) or not abs_src.startswith(("http://", "https://")):
                continue
            key = "frame:" + normalize_url(abs_src) + "@" + normalize_url(page.report_url)
            if key in self.seen:
                continue
            self.seen.add(key)
            same = is_same_site(abs_src, self.base_host)
            if not same and not self.cfg.follow_external_iframes:
                continue
            if not self._budget_left():
                return
            fp = self.fetch(abs_src, depth + 1, parent=page.url, is_iframe=True, external=not same,
                            top_url=page.report_url, frame_prefix=page.frame_prefix + seg)
            self.log(f"[{self.pages_fetched}/{self.cfg.max_pages}] iframe{' (외부)' if not same else ''} {fp.status} {abs_src}")
            fsoup = BeautifulSoup(fp.html, "lxml") if (fp.html and not fp.error) else None
            if fsoup is not None and same:
                fp.css_texts = self.stylesheets(fp, fsoup)
            yield fp
            if fsoup is None:
                continue
            yield from self._crawl_frames(fp, fsoup, depth + 1, queue, nest + 1)
            if same and depth + 1 < self.cfg.depth:
                for link in self.extract_links(fp, fsoup):
                    self._enqueue(queue, link, depth + 2, fp.url)
