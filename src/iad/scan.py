"""탐지 파이프라인: 크롤 → 분석 → (선택) 렌더 비교 → result.json/result_extra.json + 리포트."""
from __future__ import annotations

import atexit
import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .analyzer import analyze_page
from .crawler import CrawlConfig, Crawler
from .links import host_of
from .models import Finding, Page
from .official import KST, resolve_result_dir, write_results


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
    browser_note: str = ""          # 브라우저(Edge/Chrome headless) 단계 상태 한 줄
    ocr_note: str = ""              # OCR 단계 상태 한 줄
    result_dir_note: str = ""       # 결과 폴더 폴백 안내 한 줄
    official_finished: datetime | None = None   # result.json 확정 시각(4종 수집·분석 종료)

    @property
    def elapsed(self) -> float:
        return (self.finished - self.started).total_seconds()


class _Checkpoint:
    """result.json/result_extra.json 중간 기록기. 메인 스레드면 SIGINT/SIGTERM(/SIGBREAK) 핸들러와 atexit 를 건다(GUI 작업 스레드면 atexit 만)."""

    MIN_INTERVAL = 2.0

    def __init__(self, res: ScanResult, entry_url: str, result_dir: Path | None, log: Callable[[str], None]) -> None:
        self.res, self.entry_url, self.log = res, entry_url, log
        self.result_dir, fell_back = resolve_result_dir(result_dir)
        if fell_back:
            self.log(f"결과 폴더에 쓸 수 없어 {self.result_dir} 에 result.json 을 기록합니다")
        res.result_dir_note = f"결과 폴더(폴백): {self.result_dir}" if fell_back else ""
        self.last = 0.0
        self.paths: tuple[Path, Path] | None = None
        self.official_frozen = False
        self.prev_handlers: dict[int, object] = {}
        self._lock = threading.Lock()
        self._done = False

    def write(self, force: bool = False, final: bool = False) -> tuple[Path, Path]:
        now = time.monotonic()
        if not force and now - self.last < self.MIN_INTERVAL and self.paths:
            return self.paths
        with self._lock:
            if self._done and not final:
                return self.paths  # type: ignore[return-value]
            self.res.finished = datetime.now(KST)
            try:
                self.paths = write_results(self.res.findings, self.entry_url, self.res.started, self.res.finished, self.result_dir,
                                           official=not self.official_frozen)
            except Exception as e:  # 디스크 문제여도 스캔은 계속
                self.log(f"  결과 파일 기록 실패: {e!r}")
                try:   # 폴더가 도중에 막혔으면(USB 분리 등) 폴백 폴더로 한 번 더
                    d, fb = resolve_result_dir(None)
                    if fb and d != self.result_dir:
                        self.result_dir = d
                        self.paths = write_results(self.res.findings, self.entry_url, self.res.started, self.res.finished, d,
                                                   official=not self.official_frozen)
                        self.log(f"  결과 폴더를 {d} 로 바꿔 기록했습니다")
                except Exception:
                    pass
            self.last = now
            if final:
                self._done = True
        return self.paths  # type: ignore[return-value]

    def freeze_official(self) -> None:
        """공식 4종 수집·분석이 끝난 시점에 result.json 을 확정 기록(meta.finished_at·elapsed_sec 는 이 시점).
        이후 클로킹·브라우저·OCR 단계는 ETC 전용이라 result_extra.json 과 리포트만 갱신한다(검출 시간 보호)."""
        with self._lock:
            self.res.finished = datetime.now(KST)
            self.res.official_finished = self.res.finished
            try:
                self.paths = write_results(self.res.findings, self.entry_url, self.res.started, self.res.finished, self.result_dir)
                self.official_frozen = True
            except Exception as e:
                self.log(f"  결과 파일 기록 실패: {e!r}")
            self.last = time.monotonic()

    def install_handlers(self, handler) -> None:
        atexit.register(self._atexit)
        if threading.current_thread() is not threading.main_thread():
            return
        for name in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                self.prev_handlers[sig] = signal.signal(sig, handler)
            except (ValueError, OSError):
                pass

    def uninstall(self) -> None:
        for sig, prev in self.prev_handlers.items():
            try:
                signal.signal(sig, prev)  # type: ignore[arg-type]
            except (ValueError, OSError, TypeError):
                pass
        self.prev_handlers.clear()
        try:
            atexit.unregister(self._atexit)
        except Exception:
            pass

    def _atexit(self) -> None:
        if not self._done:
            try:
                self.write(force=True, final=True)
            except Exception:
                pass


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
    log(f"탐지 시작: {entry_url} (깊이 {cfg.depth}, 최대 {cfg.max_pages}페이지, 간격 {cfg.delay}s, 시간 예산 {int(cfg.time_budget_sec)}s)")
    t0 = time.monotonic()
    deadline = t0 + cfg.time_budget_sec

    # ---- 결과 파일 보장: 시작 직후 빈 결과를 쓰고, 페이지마다(최소 2초 간격) 원자적으로 갱신, 종료 신호·프로세스 종료 시 마지막 기록 ----
    checkpoint = _Checkpoint(res, entry_url, result_dir, log)
    checkpoint.write(force=True)
    externally_stopped = {"flag": False}

    def _on_signal(signum, _frame):
        externally_stopped["flag"] = True
        crawler.stop()
        res.stopped_reason = f"종료 신호({signum}) 수신 — 지금까지의 결과를 기록"
        checkpoint.write(force=True)

    checkpoint.install_handlers(_on_signal)

    def _over_budget() -> bool:
        return time.monotonic() > deadline or externally_stopped["flag"] or bool(stop_flag and stop_flag())

    try:
        for page in crawler.crawl():
            if _over_budget():
                crawler.stop()
                if not res.stopped_reason:
                    res.stopped_reason = f"시간 예산 {int(cfg.time_budget_sec)}초 초과로 중단"
            res.pages.append(page)
            if time.monotonic() > deadline:   # 분석 중이던 페이지도 예산 초과면 더 분석하지 않는다
                break
            try:
                found = analyze_page(page, host_of(page.url) if page.external else base_host)
            except Exception as e:  # 한 페이지 실패가 전체를 멈추지 않게
                log(f"  분석 오류 {page.url}: {e!r}")
                found = []
            if found:
                n_off = sum(len(f.official) for f in found)
                log(f"  → 탐지 {len(found)}건 (4종 {n_off}건)")
            res.findings.extend(found)
            checkpoint.write()
        res.stopped_reason = res.stopped_reason or crawler.stopped_reason
    except Exception as e:
        log(f"크롤 중단: {e!r}")
        res.stopped_reason = f"오류: {e!r}"
    checkpoint.freeze_official()   # 4종 확정 → result.json 은 여기서 끝(이후 단계는 ETC 전용)
    log(f"4종 수집·분석 완료: 페이지 {len(res.pages)}개, {time.monotonic() - t0:.1f}s — result.json 확정")
    if cfg.cloak_pages > 0 and not _over_budget():
        try:
            from .cloak import check_cloaking
            crawler.cfg.time_budget_sec = max(5.0, deadline - time.monotonic())   # 남은 예산만
            crawler.started = time.monotonic()
            res.findings.extend(check_cloaking(crawler, res.pages, res.findings, base_host, cfg.cloak_pages, log))
            checkpoint.write(force=True)
        except Exception as e:
            log(f"클로킹 점검 생략: {e!r}")
    if cfg.browser and not _over_budget():
        try:
            from .browser import browser_stage
            extra, res.browser_note = browser_stage(res.pages, res.findings, base_host,
                                                    lambda: max(0.0, deadline - time.monotonic()), log)
            res.findings.extend(extra)
            checkpoint.write(force=True)
        except Exception as e:
            log("브라우저 단계를 사용할 수 없어 정적 분석 결과로 계속합니다.")
            logging.getLogger("iad").debug("browser_stage 실패: %s: %s", e.__class__.__name__, e)
            res.browser_note = f"오류로 생략({e.__class__.__name__})"
    elif cfg.browser:
        res.browser_note = "시간 예산 소진으로 생략"
    if cfg.ocr and not _over_budget():
        try:
            from .ocr import ocr_stage
            extra, res.ocr_note = ocr_stage(res.pages, res.findings, base_host, crawler.session, cfg.allowed_hosts,
                                            lambda: max(0.0, deadline - time.monotonic()), log, fetch_timeout=cfg.timeout)
            res.findings.extend(extra)
            if extra or "판정" in res.ocr_note:
                checkpoint.write(force=True)
        except Exception as e:
            log(f"OCR 단계를 사용할 수 없어 정적 결과로 계속합니다({e.__class__.__name__}).")
            res.ocr_note = f"오류로 생략({e.__class__.__name__})"
    elif cfg.ocr:
        res.ocr_note = "시간 예산 소진으로 생략"
    if render and _over_budget():
        render = False
        log("시간 예산이 남지 않아 렌더 비교를 생략합니다.")
    if render:
        try:
            from .render import render_compare
            extra, shots = render_compare(res, base_host, cfg, log)
            res.findings.extend(extra)
            res.render_used = True
        except Exception as e:
            log("렌더 비교를 사용할 수 없어 정적 분석 결과로 계속합니다.")
            logging.getLogger("iad").debug("render_compare 실패: %s: %s", e.__class__.__name__, e)
    res.finished = datetime.now(KST)
    log(f"탐지 완료: 페이지 {len(res.pages)}개, 탐지 {len(res.findings)}건, {time.monotonic() - t0:.1f}s")
    paths = checkpoint.write(force=True, final=True)
    if paths is None:   # 디스크에 전혀 쓸 수 없는 경우에도 스캔 결과 객체는 돌려준다
        log("결과 파일을 어디에도 기록하지 못했습니다(쓰기 불가) — 리포트 생성은 시도합니다")
        paths = (checkpoint.result_dir / "result.json", checkpoint.result_dir / "result_extra.json")
    res.result_json, res.result_extra_json = paths
    checkpoint.uninstall()
    log(f"결과 파일: {res.result_json}")
    if write_report:
        try:
            from .report import write_reports
            res.report_html = write_reports(res, out_dir or res.result_json.parent)
            log(f"리포트: {res.report_html}")
        except Exception as e:
            log(f"리포트 생성 실패: {e.__class__.__name__}: {e}")
    return res
