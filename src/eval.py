"""하네스: 로컬 http.server 로 fixtures 를 띄우고 도구를 돌려 공식 채점을 흉내 낸다.

채점 단위 = url + location + technique (요강 붙임4). location 은 선택자 문자열이 아니라
'같은 요소를 가리키는지'로 판정한다(선택자를 DOM 에서 해석해 요소 id 비교).

실행:  uv run python eval.py        (src/ 에서)
       uv run --project src python src/eval.py   (프로젝트 루트에서)
출력:  src/EVAL_RESULT.md, src/eval_result.json
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
try:
    import bs4, lxml, requests  # noqa: F401,E401
except ImportError:  # 프로젝트 루트에서 `uv run python src/eval.py` 로 실행된 경우 src/ 의 환경으로 재실행
    import os
    import shutil
    uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
    os.execv(uv, ["uv", "run", "--project", str(HERE), "python", __file__, *sys.argv[1:]])
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "fixtures"))

from bs4 import BeautifulSoup  # noqa: E402

from gen_fixtures import generate, pick_port, serve  # noqa: E402
from iad.crawler import CrawlConfig  # noqa: E402
from iad.scan import scan  # noqa: E402

FIXTURES = HERE / "fixtures"
OFFICIAL = ("HOMOGLYPH", "JAMO", "TRANSPARENT", "OFFSCREEN")


# ---------- location 해석 ----------
_SOUPS: dict[Path, BeautifulSoup] = {}


def url_to_file(url: str, root: Path) -> Path | None:
    from urllib.parse import parse_qsl
    from iad.testbed import query_variant
    u = urlparse(url)
    p = unquote(u.path).lstrip("/")
    f = root / p
    if u.query:   # 폼 게시판 표시 URL(view.do?nttId=3) → 정적 변형 파일
        alt = query_variant(str(f), dict(parse_qsl(u.query)))
        if alt and Path(alt).is_file():
            return Path(alt)
    return f if f.is_file() else None


def load_soup(f: Path) -> BeautifulSoup:
    if f not in _SOUPS:
        raw = f.read_bytes()
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            txt = raw.decode("cp949", errors="replace")
        _SOUPS[f] = BeautifulSoup(txt, "lxml")
    return _SOUPS[f]


def resolve(url: str, location: str, root: Path, bot: bool = False) -> tuple[str | None, str | None, str]:
    """(doc 상대경로, element_id, 상태). 상태: ok / 특정불가(n) / 파일없음 / 선택자오류. bot=True 면 '.bot' 변형 문서로 해석."""
    f = url_to_file(url, root)
    if f is None:
        return None, None, "파일없음"
    if bot and (f.parent / (f.name + ".bot")).is_file():
        f = f.parent / (f.name + ".bot")
    parts = [s.strip() for s in location.split(" >>> ")]
    for seg in parts[:-1]:
        m = re.match(r'iframe\[src="([^"]+)"\]', seg)
        if not m:
            return None, None, "iframe 세그먼트 형식 오류"
        soup = load_soup(f)
        # 해당 src 의 iframe 이 실제로 이 문서에 있는지 확인
        found = False
        for fr in soup.find_all("iframe", src=True):
            from urllib.parse import urljoin
            if urljoin(url, str(fr["src"])) == m.group(1):
                found = True
                break
        if not found:
            return None, None, "iframe 없음"
        url = m.group(1)
        f = url_to_file(url, root)
        if f is None:
            return None, None, "iframe 파일없음"
    soup = load_soup(f)
    try:
        els = soup.select(parts[-1])
    except Exception:
        return None, None, "선택자오류"
    if len(els) != 1:
        return None, None, f"특정불가({len(els)})"
    el = els[0]
    rel = str(f.relative_to(root)).replace("\\", "/").removesuffix(".bot")
    _LAST_EL[0] = el
    return rel, el.get("id"), "ok"


_LAST_EL: list = [None]


def related_ids(el) -> set[str]:
    """요소 자신·조상·자손의 id 집합(추가 탐지의 느슨한 매칭용)."""
    ids = set()
    if el is None:
        return ids
    if el.get("id"):
        ids.add(el["id"])
    for a in el.parents:
        if getattr(a, "get", None) and a.get("id"):
            ids.add(a["id"])
    for d in el.find_all(True):
        if d.get("id"):
            ids.add(d["id"])
    return ids


def evaluate_set(name: str, labels: list[dict], decoys: list[str], root: Path, port: int, depth: int,
                 max_pages: int) -> dict:
    entry = f"http://127.0.0.1:{port}/{name}/index.html"
    out_dir = Path(tempfile.mkdtemp(prefix=f"iad_eval_{name}_"))
    logs: list[str] = []
    t0 = time.monotonic()
    res = scan(entry, CrawlConfig(depth=depth, max_pages=max_pages, delay=0.0, timeout=5,
                                  allowed_hosts=("127.0.0.1", "localhost"), browser=False),   # 하네스는 결정적·오프라인(브라우저 단계는 별도 테스트)
               out_dir=out_dir, result_dir=out_dir, log=logs.append, write_report=True)
    elapsed = time.monotonic() - t0
    official = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))["findings"]
    extra = json.loads((out_dir / "result_extra.json").read_text(encoding="utf-8"))["findings"]

    def key(doc: str, eid: str | None, tech: str) -> tuple:
        return (doc, eid, tech)

    labels = [l for l in labels if not l.get("platform") or l["platform"] == sys.platform]   # OS 전용 라벨(Windows OCR)은 그 OS 에서만
    gold_off = {key(f"{name}/{l['doc']}", l["element_id"], l["technique"]): l for l in labels if l["technique"] in OFFICIAL}
    gold_etc = {key(f"{name}/{l['doc']}", l["element_id"], "ETC"): l for l in labels if l["technique"] == "ETC"}

    # ---- result.json (공식) ----
    tp_keys: set[tuple] = set()
    fps: list[dict] = []
    unresolved: list[dict] = []
    seen_units: set[tuple] = set()
    for fnd in official:
        unit = (fnd["url"], fnd["location"], fnd["technique"])
        if unit in seen_units:
            continue
        seen_units.add(unit)
        doc, eid, status = resolve(fnd["url"], fnd["location"], root)
        if status != "ok":
            unresolved.append({**fnd, "status": status})
            fps.append({**fnd, "reason": status})
            continue
        k = key(doc, eid, fnd["technique"])
        if k in gold_off:
            tp_keys.add(k)
        else:
            reason = "정답 요소지만 기법 불일치" if any(kk[:2] == k[:2] for kk in gold_off) else "라벨 없음(오탐)"
            fps.append({**fnd, "reason": reason, "doc": doc, "element_id": eid})
    n_units = len(seen_units)
    tp = len(tp_keys)
    precision = tp / n_units if n_units else 0.0
    recall = tp / len(gold_off) if gold_off else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    per_tech = {}
    for t in OFFICIAL:
        g = [k for k in gold_off if k[2] == t]
        per_tech[t] = {"gold": len(g), "hit": sum(1 for k in g if k in tp_keys),
                       "recall": round(sum(1 for k in g if k in tp_keys) / len(g), 3) if g else None}
    missed = [gold_off[k] for k in gold_off if k not in tp_keys]

    # ---- result_extra.json ----
    etc_hit: set[tuple] = set()
    etc_fp: list[dict] = []
    for fnd in extra:
        cloak = "CLOAKING" in fnd.get("extra_finding", "")
        doc, eid, status = resolve(fnd["url"], fnd["location"], root, bot=cloak)
        if status != "ok":
            etc_fp.append({**fnd, "reason": status})
            continue
        rel_ids = related_ids(_LAST_EL[0])
        hits = [kk for kk in gold_etc if kk[0] == doc and kk[1] in rel_ids]
        if hits:
            etc_hit.update(hits)
        elif any(kk[0] == doc and kk[1] in rel_ids for kk in gold_off):
            continue  # 4종 정답 요소를 ETC 로도 보고한 것은 오탐으로 안 봄
        else:
            etc_fp.append({**fnd, "reason": "라벨 없음", "doc": doc, "element_id": eid})
    etc_missed = [gold_etc[k] for k in gold_etc if k not in etc_hit]
    decoy_hits = [f for f in fps + etc_fp if any(f.get("doc", "") == f"{name}/{d}" for d in decoys)]

    return {
        "set": name, "entry_url": entry, "pages_crawled": len(res.pages), "elapsed_sec": round(elapsed, 2),
        "tool_elapsed_sec": res.elapsed,
        "official": {"gold": len(gold_off), "reported_units": n_units, "tp": tp, "fp": n_units - tp,
                     "precision(정확도)": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
                     "per_technique": per_tech, "false_positives": fps, "missed": missed, "unresolved": unresolved},
        "extra": {"gold": len(gold_etc), "reported": len(extra), "hit": len(etc_hit),
                  "recall": round(len(etc_hit) / len(gold_etc), 3) if gold_etc else None,
                  "false_positives": etc_fp, "missed": etc_missed},
        "decoy_hits": decoy_hits, "out_dir": str(out_dir),
    }


REALWORLD = HERE / "fixtures" / "realworld"
RW_MAX_ETC = 9          # 실사이트 정상 세트: ETC 는 한 자릿수
RW_MAX_CPU_PER_PAGE = 1.0   # 맥 M시리즈 실측 0.22s, Windows CI 러너 편차를 감안해 쪽당 1.0s(실측값은 EVAL_RESULT 에 기록)


def evaluate_realworld() -> dict | None:
    """실사이트 정상 세트(1회 수집한 공개 공공 페이지 + 외부 CSS)를 오프라인 분석: 4종 0건·ETC 상한·쪽당 CPU 상한이 통과 조건."""
    man_path = REALWORLD / "manifest.json"
    if not man_path.is_file():
        return None
    from iad.analyzer import analyze_page
    from iad.models import Page
    man = json.loads(man_path.read_text(encoding="utf-8"))
    base = urlparse(man["entry_url"]).hostname or ""
    base = base.removeprefix("www.")
    official: list[dict] = []
    extra: list[dict] = []
    cpu = 0.0
    for m in man["pages"]:
        page = Page(url=m["url"], html=(REALWORLD / "pages" / m["file"]).read_text(encoding="utf-8"))
        page.css_texts = [(REALWORLD / "css" / f).read_text(encoding="utf-8") for f in m["css"]]
        t = time.process_time()
        fs = analyze_page(page, base)
        cpu += time.process_time() - t
        for f in fs:
            row = {"url": f.page_url, "location": f.location, "evidence_text": f.evidence_text[:80], "score": f.score}
            if f.official:
                official.append({**row, "technique": "+".join(f.official)})
            elif f.extra_names:
                extra.append({**row, "extra_finding": "+".join(f.extra_names)})
    n = max(len(man["pages"]), 1)
    passed = not official and len(extra) <= RW_MAX_ETC and cpu / n <= RW_MAX_CPU_PER_PAGE
    failed = [c for c, ok in (("official_fp=0", not official), (f"etc<={RW_MAX_ETC}", len(extra) <= RW_MAX_ETC),
                              (f"cpu/page<={RW_MAX_CPU_PER_PAGE}", cpu / n <= RW_MAX_CPU_PER_PAGE)) if not ok]
    return {"set": "realworld", "entry_url": man["entry_url"], "pages": len(man["pages"]), "official_fp": official, "extra": extra,
            "etc_count": len(extra), "cpu_per_page": round(cpu / n, 3), "cpu_total": round(cpu, 2), "pass": passed, "failed": failed}


def realworld_summary(rw: dict) -> str:
    """실패 원인을 한눈에: 어떤 조건이 깨졌는지, ETC 상위 5개, 쪽당 CPU."""
    top = "; ".join(f"{e['extra_finding']} @ {e['location'][-60:]}" for e in rw["extra"][:5]) or "-"
    fp = "; ".join(f"{e['technique']} @ {e['location'][-60:]}" for e in rw["official_fp"][:5]) or "-"
    return (f"pass={rw['pass']} failed={rw['failed']} official_fp={len(rw['official_fp'])} [{fp}] "
            f"etc_count={rw['etc_count']} (max {RW_MAX_ETC}) top5=[{top}] cpu_per_page={rw['cpu_per_page']}s (max {RW_MAX_CPU_PER_PAGE}, total {rw['cpu_total']}s)")


def md_report(results: list[dict], meta: dict) -> str:
    L = [f"# 평가 결과 ({meta['timestamp']})", "",
         f"- 명령: `uv run python src/eval.py` · 깊이 {meta['depth']} · 최대 {meta['max_pages']}페이지 · 포트 {meta['port']}",
         "- 채점 단위: url + location + technique (요강 붙임4). location 은 DOM 에서 해석해 같은 요소인지 비교.",
         "- 정확도 = 정탐 / result.json 전체 검출 단위(요강 '정답 추출 정확도' 정의와 동일).", ""]
    L += ["| 세트 | 정답 | 검출 | 정탐 | 오탐 | 정확도 | 재현율 | F1 | 페이지 | 소요(초) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        o = r["official"]
        L.append(f"| {r['set']} | {o['gold']} | {o['reported_units']} | {o['tp']} | {o['fp']} | {o['precision(정확도)']} | "
                 f"{o['recall']} | {o['f1']} | {r['pages_crawled']} | {r['elapsed_sec']} |")
    L += ["", "## 기법별 재현율 (result.json)", "", "| 세트 | " + " | ".join(OFFICIAL) + " |", "|---|" + "---|" * len(OFFICIAL)]
    for r in results:
        pt = r["official"]["per_technique"]
        L.append(f"| {r['set']} | " + " | ".join(f"{pt[t]['hit']}/{pt[t]['gold']}" for t in OFFICIAL) + " |")
    L += ["", "## 추가 탐지 (result_extra.json, 본심사용)", "", "| 세트 | ETC 정답 | 보고 | 적중 | 재현율 | 오탐(라벨 없음) |", "|---|---|---|---|---|---|"]
    for r in results:
        e = r["extra"]
        L.append(f"| {r['set']} | {e['gold']} | {e['reported']} | {e['hit']} | {e['recall']} | {len(e['false_positives'])} |")
    rw = meta.get("realworld")
    if rw:
        L += ["", "## 실사이트 정상 세트 (fixtures/realworld, 오프라인)", "",
              f"- 출처: {rw['entry_url']} ({rw['pages']}쪽, 1회 수집) · 통과 조건: 4종 0건 · ETC ≤{RW_MAX_ETC} · 쪽당 CPU ≤{RW_MAX_CPU_PER_PAGE}s",
              f"- 결과: 4종 {len(rw['official_fp'])}건 · ETC {len(rw['extra'])}건 · 쪽당 CPU {rw['cpu_per_page']}s(합계 {rw['cpu_total']}s, time.process_time, 이 머신 실측) → **{'PASS' if rw['pass'] else 'FAIL'}**"]
        for f in rw["official_fp"]:
            L.append(f"  - [4종 오탐] {f['technique']} `{f['location']}` — “{f['evidence_text']}”")
        for f in rw["extra"]:
            L.append(f"  - [ETC] {f['extra_finding']} `{f['location'][-80:]}` — “{f['evidence_text']}”")
    for r in results:
        L += ["", f"## {r['set']} 상세", ""]
        o = r["official"]
        L.append(f"### result.json 오탐 {len(o['false_positives'])}건")
        for f in o["false_positives"]:
            L.append(f"- [{f['technique']}] {f['url'].split('/', 3)[-1]} `{f['location']}` — {f['reason']} — “{f['evidence_text'][:60]}”")
        L.append(f"### result.json 미탐 {len(o['missed'])}건")
        for m in o["missed"]:
            L.append(f"- [{m['technique']}] {m['doc']} #{m['element_id']} ({m['category']})")
        L.append(f"### result_extra.json 미탐 {len(r['extra']['missed'])}건")
        for m in r["extra"]["missed"]:
            L.append(f"- [{m['extra_name']}] {m['doc']} #{m['element_id']}")
        L.append(f"### result_extra.json 오탐 {len(r['extra']['false_positives'])}건")
        for f in r["extra"]["false_positives"]:
            L.append(f"- {f['url'].split('/', 3)[-1]} `{f['location']}` — {f.get('extra_finding', '')[:60]} — “{f['evidence_text'][:60]}”")
        L.append(f"### 정상 문서(오탐 유도) 적중: {len(r['decoy_hits'])}건")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--max-pages", type=int, default=300)
    ap.add_argument("--sets", default="dev,holdout")
    a = ap.parse_args(argv)
    port = pick_port(a.port)
    root = FIXTURES
    if port != a.port:
        root = Path(tempfile.mkdtemp(prefix="iad_fixtures_"))
        print(f"포트 {a.port} 사용 중 → {port} 로 임시 생성: {root}")
    data = generate(root, port)
    httpd = serve(root, port)
    try:
        results = []
        for name in a.sets.split(","):
            labels = [l for l in data["labels"] if l["set"] == name]
            results.append(evaluate_set(name, labels, data["decoys"][name], root, port, a.depth, a.max_pages))
    finally:
        httpd.shutdown()
    meta = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "depth": a.depth, "max_pages": a.max_pages, "port": port}
    rw = evaluate_realworld()
    if rw:
        meta["realworld"] = rw
    (HERE / "eval_result.json").write_text(json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    md = md_report(results, meta)
    (HERE / "EVAL_RESULT.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
