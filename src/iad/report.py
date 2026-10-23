"""자체완결 HTML 리포트(한국어, 필터·정렬·근거 펼치기) + CSV + JSON."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .models import Finding

TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>불법광고 탐지 리포트</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f7f8fa;--fg:#1d2330;--card:#fff;--line:#dde2ea;--hi:#c62828;--mid:#ef6c00;--lo:#2e7d32;--acc:#1e4fa3}
body{margin:0;font-family:"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;background:var(--bg);color:var(--fg);font-size:14px}
header{background:var(--acc);color:#fff;padding:16px 24px}header h1{margin:0;font-size:20px}header p{margin:6px 0 0;opacity:.9}
main{padding:16px 24px;max-width:1400px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.card b{display:block;font-size:22px}.card span{color:#667}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;align-items:center}
select,input{padding:6px 8px;border:1px solid var(--line);border-radius:6px;font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line)}
th,td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
th{background:#eef1f6;cursor:pointer;white-space:nowrap;position:sticky;top:0}
.r-높음{color:var(--hi);font-weight:700}.r-중간{color:var(--mid);font-weight:700}.r-낮음{color:var(--lo)}
.tag{display:inline-block;background:#e8eefc;color:var(--acc);border-radius:4px;padding:1px 6px;margin:1px;font-size:12px}
.tag.off{background:#fde7e7;color:var(--hi)}
.loc{font-family:ui-monospace,Consolas,monospace;font-size:12px;word-break:break-all}
details summary{cursor:pointer;color:var(--acc)}
pre{white-space:pre-wrap;word-break:break-all;background:#f1f3f7;padding:8px;border-radius:6px;font-size:12px;max-height:220px;overflow:auto}
ul.ev{margin:6px 0;padding-left:18px}ul.ev li.neg{color:#667}
img.shot{max-width:400px;border:1px solid var(--line);margin-top:6px}
footer{color:#667;padding:16px 24px;font-size:12px}
</style></head><body>
<header><h1>공공 웹사이트 불법광고 탐지 리포트</h1><p id="meta"></p></header>
<main>
<div class="cards" id="cards"></div>
<div class="tools">
 <label>위험도 <select id="f-risk"><option value="">전체</option><option>높음</option><option>중간</option><option>낮음</option></select></label>
 <label>분류 <select id="f-cat"><option value="">전체</option></select></label>
 <label>기법 <select id="f-tech"><option value="">전체</option></select></label>
 <label>페이지 <select id="f-page"><option value="">전체</option></select></label>
 <label>검색 <input id="f-q" placeholder="텍스트·URL·선택자"></label>
 <span id="count"></span>
</div>
<table><thead><tr>
<th data-k="risk">위험도</th><th data-k="score">점수</th><th data-k="category">분류</th><th data-k="official">요강 기법</th>
<th data-k="page_url">페이지</th><th data-k="location">위치(CSS)</th><th>근거 텍스트</th><th>상세</th></tr></thead>
<tbody id="rows"></tbody></table>
</main>
<footer>result.json(요강 4종) / result_extra.json(추가 탐지)은 구동 파일 폴더에 생성됩니다. 본 리포트는 두 파일의 합집합입니다.</footer>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const m=D.meta;
document.getElementById('meta').textContent=`진입 URL: ${m.entry_url} · 시작 ${m.started_at} · 완료 ${m.finished_at} · 소요 ${m.elapsed_sec}s · 페이지 ${m.pages}개` + (m.stopped_reason?` · ${m.stopped_reason}`:'');
const F=D.findings;
const cnt=k=>F.filter(f=>f.risk===k).length;
const off=F.reduce((a,f)=>a+f.official.length,0);
document.getElementById('cards').innerHTML=[
 ['탐지 건수',F.length],['요강 4종 검출',off],['높음',cnt('높음')],['중간',cnt('중간')],['낮음',cnt('낮음')],
 ['페이지',m.pages],['소요(초)',m.elapsed_sec]].map(([k,v])=>`<div class="card"><b>${v}</b><span>${k}</span></div>`).join('');
function fill(id,vals){const s=document.getElementById(id);[...new Set(vals)].sort().forEach(v=>{const o=document.createElement('option');o.textContent=v;s.appendChild(o);});}
fill('f-cat',F.map(f=>f.category));fill('f-tech',F.flatMap(f=>f.official.concat(f.extra_names)));fill('f-page',F.map(f=>f.page_url));
let sortK='score',sortDir=-1;
function render(){
 const r=document.getElementById('f-risk').value,c=document.getElementById('f-cat').value,t=document.getElementById('f-tech').value,p=document.getElementById('f-page').value,q=document.getElementById('f-q').value.toLowerCase();
 let rows=F.filter(f=>(!r||f.risk===r)&&(!c||f.category===c)&&(!t||f.official.includes(t)||f.extra_names.includes(t))&&(!p||f.page_url===p)&&(!q||(f.evidence_text+f.page_url+f.location+f.snippet).toLowerCase().includes(q)));
 const ord={'높음':3,'중간':2,'낮음':1};
 rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(sortK==='risk'){x=ord[x];y=ord[y]}if(Array.isArray(x)){x=x.join();y=y.join()}return (x>y?1:x<y?-1:0)*sortDir;});
 document.getElementById('count').textContent=`${rows.length}건 표시`;
 document.getElementById('rows').innerHTML=rows.map(f=>`<tr>
 <td class="r-${f.risk}">${f.risk}</td><td>${f.score}</td><td>${esc(f.category)}</td>
 <td>${f.official.map(o=>`<span class="tag off">${o}</span>`).join('')}${f.extra_names.map(o=>`<span class="tag">${esc(o)}</span>`).join('')}</td>
 <td><a href="${esc(f.page_url)}" target="_blank">${esc(f.page_url)}</a>${f.frame_url?`<br><small>iframe: ${esc(f.frame_url)}</small>`:''}</td>
 <td class="loc">${esc(f.location)}</td><td>${esc(f.evidence_text.slice(0,200))}</td>
 <td><details><summary>근거 ${f.evidence.length}개</summary><ul class="ev">${f.evidence.map(e=>`<li class="${e.weight<0?'neg':''}">${esc(e.detail)} <small>(${e.weight>0?'+':''}${e.weight})</small></li>`).join('')}</ul>
 ${f.links.length?`<div>링크: ${f.links.map(l=>`<span class="loc">${esc(l)}</span>`).join(', ')}</div>`:''}
 <pre>${esc(f.html)}</pre>${f.screenshot?`<img class="shot" src="${esc(f.screenshot)}">`:''}</details></td></tr>`).join('');
}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=-1}render();});
['f-risk','f-cat','f-tech','f-page'].forEach(id=>document.getElementById(id).onchange=render);
document.getElementById('f-q').oninput=render;render();
</script></body></html>
"""


def finding_rows(findings: list[Finding]) -> list[dict]:
    rows = []
    for f in findings:
        d = f.to_dict()
        rows.append(d)
    return rows


def write_reports(res, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "entry_url": res.entry_url, "started_at": res.started.isoformat(timespec="seconds"),
        "finished_at": res.finished.isoformat(timespec="seconds"), "elapsed_sec": round(res.elapsed, 1),
        "pages": len(res.pages), "stopped_reason": res.stopped_reason, "render_used": res.render_used,
    }
    rows = finding_rows(res.findings)
    data = json.dumps({"meta": meta, "findings": rows}, ensure_ascii=False).replace("</", "<\\/")
    html_path = out_dir / "report.html"
    html_path.write_text(TEMPLATE.replace("__DATA__", data), encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps({"meta": meta, "findings": rows}, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    with open(out_dir / "report.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["위험도", "점수", "분류", "요강기법", "추가유형", "페이지URL", "iframeURL", "위치(CSS)", "근거텍스트",
                    "근거목록", "링크"])
        for f in res.findings:
            w.writerow([f.risk, f.score, f.category, "|".join(f.official), "|".join(f.extra_names), f.page_url,
                        f.frame_url or "", f.location, f.evidence_text[:300],
                        " ; ".join(f"{e.detail}({e.weight:+})" for e in f.evidence), " ".join(f.links)])
    return html_path


__all__ = ["write_reports", "html"]
