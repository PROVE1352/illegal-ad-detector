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
    """ETC 는 technique 가 고정이므로 (url, location) 당 1건으로 합치고 유형 이름은 extra_finding 에 나열한다."""
    out: list[dict] = []
    merged: dict[tuple[str, str, str], dict] = {}
    for f in findings:
        names = [n for n in f.extra_names if n]
        if not names:
            continue
        key = _dedupe_key(f.page_url, f.location, "ETC")
        reasons = "; ".join(e.detail for e in f.evidence if e.weight > 0)[:300]
        if key in merged:
            m = merged[key]
            m["_names"] = list(dict.fromkeys(m["_names"] + names))
            continue
        merged[key] = {
            "url": f.page_url, "location": f.location,
            "evidence_text": (f.evidence_text or f.snippet) + (f"  [근거: {reasons}]" if reasons else ""),
            "_names": names, "_cat": f.category, "_risk": f.risk, "_score": f.score,
        }
    for m in merged.values():
        out.append({
            "id": f"f_{len(out) + 1:03d}",
            "url": m["url"],
            "is_violation": True,
            "location": m["location"],
            "evidence_text": m["evidence_text"],
            "technique": "ETC",
            "extra_finding": f"{'+'.join(m['_names'])} / 분류={m['_cat']} / 위험도={m['_risk']} / 점수={m['_score']}",
        })
    return out


def _atomic_write_json(path: Path, obj: dict) -> None:
    """임시 파일에 쓰고 os.replace 로 바꿔치기 — 강제 종료 순간에도 깨진(파싱 불가) result.json 이 남지 않게."""
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fp:   # UTF-8, BOM 없음
        json.dump(obj, fp, ensure_ascii=False, indent=2)
        fp.flush()
        try:
            os.fsync(fp.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def _writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / f".iad-write-test-{os.getpid()}"
        probe.write_bytes(b"ok")
        probe.unlink()
        return True
    except OSError:
        return False


def fallback_dirs() -> list[Path]:
    """결과 폴더 폴백 순서: 현재 작업 폴더 → %LOCALAPPDATA%\\IllegalAdDetector(없으면 사용자 홈/IllegalAdDetector)."""
    out = [Path.cwd()]
    base = os.environ.get("LOCALAPPDATA")
    out.append((Path(base) if base else Path.home()) / "IllegalAdDetector")
    return out


def resolve_result_dir(preferred: Path | None) -> tuple[Path, bool]:
    """(실제로 쓸 폴더, 폴백 여부). 선호 폴더(없으면 exe 폴더)가 쓰기 불가(Program Files·읽기 전용 USB)면 폴백 순서대로 쓰기 시험을 한다."""
    first = Path(preferred) if preferred else run_dir()
    if _writable(first):
        return first, False
    for d in fallback_dirs():
        if d.resolve() != first.resolve() and _writable(d):
            return d, True
    return first, False


def write_results(findings: list[Finding], entry_url: str, started: datetime, finished: datetime,
                  out_dir: Path | None = None, official: bool = True, extra: bool = True,
                  official_meta: dict | None = None) -> tuple[Path, Path]:
    """result.json / result_extra.json 을 원자적으로 쓴다(스캔 중 주기적으로 호출되어 중간 결과를 갱신한다).
    official=False 면 result.json 은 건드리지 않는다(4종 확정 후 ETC 전용 단계가 돌 때)."""
    d = Path(out_dir) if out_dir else run_dir()
    d.mkdir(parents=True, exist_ok=True)
    meta = build_meta(entry_url, started, finished)
    p1 = d / "result.json"
    p2 = d / "result_extra.json"
    if official:
        _atomic_write_json(p1, {"meta": official_meta or meta, "findings": build_official(findings)})
    if extra:
        _atomic_write_json(p2, {"meta": meta, "findings": build_extra(findings)})
    return p1, p2
