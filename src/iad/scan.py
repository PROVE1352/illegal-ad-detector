"""탐지 파이프라인: 크롤 → 분석 → (선택) 렌더 비교 → result.json/result_extra.json + 리포트."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .analyzer import analyze_page
from .crawler import CrawlConfig, Crawler
from .links import host_of
from .models import Finding, Page
from .official import KST, write_results


@dataclass
class ScanResult:
    entry_url: str
    started: datetime
    finished: datetime
    pages: list[Page] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    result_json: Path | None = None
    result_extra_json: Path | None = None
    report_html: Path | None = None
    stopped_reason: str = ""
    render_used: bool = False

    @property
    def elapsed(self) -> float:
        return (self.finished - self.started).total_seconds()


def scan(entry_url: str, config: CrawlConfig | None = None, out_dir: Path | None = None,
         result_dir: Path | None = None, log: Callable[[str], None] | None = None,
         render: bool = False, stop_flag: Callable[[], bool] | None = None,
         write_report: bool = True) -> ScanResult:
    """entry_url 1개를 입력받아 전체 탐지를 수행한다.

    result_dir: result.json 생성 폴더(기본: 구동 파일 폴더). out_dir: HTML/CSV/JSON 리포트 폴더(기본: result_dir).
    """
    log = log or (lambda m: None)
    cfg = config or CrawlConfig()
    if not entry_url.startswith(("http://", "https://")):
        entry_url = "http://" + entry_url
    started = datetime.now(KST)
    res = ScanResult(entry_url=entry_url, started=started, finished=started)
    crawler = Crawler(entry_url, cfg, log=log)
    base_host = host_of(entry_url)
    log(f"탐지 시작: {entry_url} (깊이 {cfg.depth}, 최대 {cfg.max_pages}페이지, 간격 {cfg.delay}s)")
    t0 = time.monotonic()
    try:
        for page in crawler.crawl():
            if stop_flag and stop_flag():
                crawler.stop()
            res.pages.append(page)
            try:
                found = analyze_page(page, host_of(page.url) if page.external else base_host)
            except Exception as e:  # 한 페이지 실패가 전체를 멈추지 않게
                log(f"  분석 오류 {page.url}: {e!r}")
                found = []
            if found:
                n_off = sum(len(f.official) for f in found)
                log(f"  → 탐지 {len(found)}건 (4종 {n_off}건)")
            res.findings.extend(found)
        res.stopped_reason = crawler.stopped_reason
    except Exception as e:
        log(f"크롤 중단: {e!r}")
        res.stopped_reason = f"오류: {e!r}"
    if render:
        try:
            from .render import render_compare
            extra, shots = render_compare(res, base_host, cfg, log)
            res.findings.extend(extra)
            res.render_used = True
        except Exception as e:
            log(f"렌더 비교 생략(playwright/Edge 사용 불가): {e.__class__.__name__}")
    res.finished = datetime.now(KST)
    log(f"탐지 완료: 페이지 {len(res.pages)}개, 탐지 {len(res.findings)}건, {time.monotonic() - t0:.1f}s")
    res.result_json, res.result_extra_json = write_results(res.findings, entry_url, res.started, res.finished,
                                                           result_dir)
    log(f"결과 파일: {res.result_json}")
    if write_report:
        from .report import write_reports
        res.report_html = write_reports(res, out_dir or res.result_json.parent)
        log(f"리포트: {res.report_html}")
    return res
