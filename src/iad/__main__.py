"""CLI: python -m iad --url URL [--depth N] [--max-pages N] [--out DIR] [--result-dir DIR] [--render]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .crawler import CrawlConfig
from .scan import scan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="iad", description="공공 웹사이트 불법광고 탐지 도구")
    p.add_argument("--url", required=True, help="진입 URL 1개")
    p.add_argument("--depth", type=int, default=3, help="탐색 깊이(기본 3)")
    p.add_argument("--max-pages", type=int, default=300, help="최대 페이지 수(기본 300)")
    p.add_argument("--delay", type=float, default=0.3, help="요청 간격 초(기본 0.3)")
    p.add_argument("--timeout", type=float, default=10.0, help="요청 타임아웃 초")
    p.add_argument("--time-budget", type=float, default=1200, help="전체 시간 예산 초(기본 1200=20분)")
    p.add_argument("--out", default=None, help="리포트(report.html/csv/json) 폴더. 기본: result.json 폴더")
    p.add_argument("--result-dir", default=None, help="result.json 생성 폴더. 기본: 구동 파일 폴더")
    p.add_argument("--robots", action="store_true", help="robots.txt 존중")
    p.add_argument("--no-external-iframe", action="store_true", help="외부 도메인 iframe 수집 안 함")
    p.add_argument("--render", action="store_true", help="playwright(msedge) 렌더 비교·스크린샷 시도")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = CrawlConfig(depth=args.depth, max_pages=args.max_pages, delay=args.delay, timeout=args.timeout,
                      respect_robots=args.robots, follow_external_iframes=not args.no_external_iframe,
                      time_budget_sec=args.time_budget)
    log = (lambda m: None) if args.quiet else (lambda m: print(m, flush=True))
    res = scan(args.url, cfg, out_dir=Path(args.out) if args.out else None,
               result_dir=Path(args.result_dir) if args.result_dir else None, log=log, render=args.render)
    n_off = sum(len(f.official) for f in res.findings)
    print(f"\n완료: 페이지 {len(res.pages)}개, 탐지 {len(res.findings)}건(요강 4종 {n_off}건), {res.elapsed:.1f}초")
    print(f"result.json: {res.result_json}\nresult_extra.json: {res.result_extra_json}\nreport: {res.report_html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
