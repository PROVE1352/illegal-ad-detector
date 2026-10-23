"""요강(붙임4) 표준 스키마 result.json / result_extra.json 생성."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from . import __version__
from .models import Finding

KST = timezone(timedelta(hours=9))
OFFICIAL_CODES = ("HOMOGLYPH", "JAMO", "TRANSPARENT", "OFFSCREEN")
TOPIC = "TOPIC"   # 요강 예시값 그대로. 표의 "TOPIC(불법광고)"는 설명으로 해석(README 참고)


def run_dir() -> Path:
    """구동 파일이 위치한 폴더: frozen exe 면 exe 폴더, 아니면 현재 작업 폴더."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(os.getcwd())


def iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="seconds")


def build_meta(entry_url: str, started: datetime, finished: datetime) -> dict:
    return {
        "topic": TOPIC,
        "entry_url": entry_url,
        "started_at": iso(started),
        "finished_at": iso(finished),
        "elapsed_sec": round((finished - started).total_seconds(), 3),
        "tool_version": __version__,
    }


def _dedupe_key(url: str, location: str, technique: str) -> tuple[str, str, str]:
    from .crawler import normalize_url
    return normalize_url(url), location.strip(), technique


def build_official(findings: list[Finding]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for f in findings:
        for code in f.official:
            if code not in OFFICIAL_CODES:
                continue
            key = _dedupe_key(f.page_url, f.location, code)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "id": f"f_{len(out) + 1:03d}",
                "url": f.page_url,
                "is_violation": True,
                "location": f.location,
                "evidence_text": f.evidence_text or f.snippet,
                "technique": code,
            })
    return out


def build_extra(findings: list[Finding]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for f in findings:
        names = [n for n in f.extra_names if n]
        if not names:
            continue
        for name in names:
            key = _dedupe_key(f.page_url, f.location, name)
            if key in seen:
                continue
            seen.add(key)
            reasons = "; ".join(e.detail for e in f.evidence if e.weight > 0)[:300]
            out.append({
                "id": f"f_{len(out) + 1:03d}",
                "url": f.page_url,
                "is_violation": True,
                "location": f.location,
                "evidence_text": (f.evidence_text or f.snippet) + (f"  [근거: {reasons}]" if reasons else ""),
                "technique": "ETC",
                "extra_finding": f"{name} / 분류={f.category} / 위험도={f.risk} / 점수={f.score}",
            })
    return out


def write_results(findings: list[Finding], entry_url: str, started: datetime, finished: datetime,
                  out_dir: Path | None = None) -> tuple[Path, Path]:
    d = out_dir or run_dir()
    d.mkdir(parents=True, exist_ok=True)
    meta = build_meta(entry_url, started, finished)
    p1 = d / "result.json"
    p2 = d / "result_extra.json"
    with open(p1, "w", encoding="utf-8", newline="\n") as fp:   # UTF-8, BOM 없음
        json.dump({"meta": meta, "findings": build_official(findings)}, fp, ensure_ascii=False, indent=2)
    with open(p2, "w", encoding="utf-8", newline="\n") as fp:
        json.dump({"meta": meta, "findings": build_extra(findings)}, fp, ensure_ascii=False, indent=2)
    return p1, p2
