"""`--demo`: 내장 테스트베드(가짜 공공기관 사이트)를 로컬에서 띄우고 → 스캔 → result.json/리포트 생성 → 브라우저로 연다.

네트워크는 127.0.0.1 만 쓴다(allowed_hosts 가드). 사이트는 iad.testbed 가 임시 폴더에 생성하므로 exe 에 데이터 파일이 필요 없다.
"""
from __future__ import annotations

import json
import tempfile
import webbrowser
from collections.abc import Callable
from pathlib import Path

from .crawler import CrawlConfig
from .official import run_dir
from .scan import ScanResult, scan
from .testbed import generate, pick_port, serve


def run_demo(log: Callable[[str], None] | None = None, result_dir: Path | None = None, open_browser: bool = True,
             site: str = "dev", stop_flag: Callable[[], bool] | None = None) -> ScanResult:
    log = log or (lambda m: None)
    root = Path(tempfile.mkdtemp(prefix="iad_demo_site_"))
    port = pick_port(0)
    data = generate(root, port)
    httpd = serve(root, port)
    entry = f"http://127.0.0.1:{port}/{site}/index.html"
    out = result_dir or (run_dir() / "demo")
    labels = [l for l in data["labels"] if l["set"] == site]
    n_off = sum(1 for l in labels if l["technique"] != "ETC")
    log(f"데모 사이트 생성: {root / site}  (4종 정답 {n_off}건, 추가 유형 {len(labels) - n_off}건 심어 둠)")
    log(f"데모 서버: {entry}")
    try:
        res = scan(entry, CrawlConfig(delay=0.0, timeout=5, allowed_hosts=("127.0.0.1", "localhost")),
                   out_dir=out, result_dir=out, log=log, stop_flag=stop_flag)
    finally:
        httpd.shutdown()
    found_off = sum(len(f.official) for f in res.findings)
    log(f"데모 결과: 4종 {found_off}건 검출 (정답 {n_off}건), 추가 {sum(1 for f in res.findings if f.extra_names)}건 · "
        f"result.json → {res.result_json}")
    (out / "demo_labels.json").write_text(json.dumps({"entry_url": entry, "labels": labels}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    if open_browser and res.report_html:
        try:
            webbrowser.open(res.report_html.resolve().as_uri())
        except Exception as e:  # 브라우저 없는 환경
            log(f"리포트 자동 열기 실패: {e!r}")
    return res
