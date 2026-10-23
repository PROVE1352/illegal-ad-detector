"""자체완결 HTML 리포트(한국어, 작업지시서 수준) + CSV + JSON.

- 요약 카드(건수·4종·우선순위·영역별), 필터·정렬·검색, 행마다 조치 가이드·신고처·defang URL·SHA-256 지문
- 처리 상태(미처리/조치중/완료)·담당 메모는 브라우저 localStorage 에 지문 키로 저장(파일을 다시 열어도 유지)
- '작업지시서 보기' = 페이지별로 묶은 인쇄용 화면(window.print)
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .models import Finding
from .triage import enrich

TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>불법광고 탐지 작업지시서</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f7f8fa;--fg:#1d2330;--card:#fff;--line:#dde2ea;--hi:#c62828;--mid:#ef6c00;--lo:#2e7d32;--acc:#1e4fa3;--urg:#7b1fa2}
body{margin:0;font-family:"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;background:var(--bg);color:var(--fg);font-size:14px}
header{background:var(--acc);color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
header h1{margin:0;font-size:19px}header p{margin:4px 0 0;opacity:.9;font-size:13px}
header button{background:#fff;color:var(--acc);border:0;border-radius:6px;padding:7px 12px;font-weight:700;cursor:pointer;margin-left:6px}
main{padding:16px 24px;max-width:1500px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.card b{display:block;font-size:22px}.card span{color:#667;font-size:12px}
.areas{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}
.areas span{background:#e8eefc;border-radius:12px;padding:3px 10px;font-size:12px;cursor:pointer}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;align-items:center}
select,input,textarea{padding:5px 7px;border:1px solid var(--line);border-radius:6px;font-size:13px;font-family:inherit}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line)}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
th{background:#eef1f6;cursor:pointer;white-space:nowrap;position:sticky;top:0;z-index:1}
.p-긴급{color:var(--urg);font-weight:700}.p-높음{color:var(--hi);font-weight:700}.p-보통{color:#555}
.r-높음{color:var(--hi);font-weight:700}.r-중간{color:var(--mid);font-weight:700}.r-낮음{color:var(--lo)}
.tag{display:inline-block;background:#e8eefc;color:var(--acc);border-radius:4px;padding:1px 6px;margin:1px;font-size:12px}
.tag.off{background:#fde7e7;color:var(--hi)}.tag.area{background:#eef7ea;color:var(--lo)}
.loc{font-family:ui-monospace,Consolas,monospace;font-size:12px;word-break:break-all}
.fp{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#667}
details summary{cursor:pointer;color:var(--acc)}
pre{white-space:pre-wrap;word-break:break-all;background:#f1f3f7;padding:8px;border-radius:6px;font-size:12px;max-height:220px;overflow:auto}
ul.ev{margin:6px 0;padding-left:18px}ul.ev li.neg{color:#667}
ol.steps{margin:4px 0;padding-left:18px}
.copy{border:1px solid var(--line);background:#fff;border-radius:4px;font-size:11px;padding:1px 5px;cursor:pointer;margin-left:4px}
.status-done td{opacity:.55}
img.shot{max-width:400px;border:1px solid var(--line);margin-top:6px}
footer{color:#667;padding:16px 24px;font-size:12px}
#order{display:none}
#order .page{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-bottom:12px;page-break-inside:avoid}
#order h3{margin:0 0 6px;font-size:15px}#order .item{border-top:1px dashed var(--line);padding:8px 0}
#order .item .loc{display:block;margin:2px 0}
.hidden{display:none}
@media print{header button,.tools,#table-view,.areas{display:none!important}#order{display:block!important}body{background:#fff}main{padding:0}}
</style></head><body>
<header><div><h1>공공 웹사이트 불법광고 탐지 작업지시서</h1><p id="meta"></p></div>
<div><button onclick="toggleView()" id="viewbtn">작업지시서 보기</button><button onclick="window.print()">인쇄/PDF</button><button onclick="exportJson()">상태 내보내기(JSON)</button></div></header>
<main>
<div class="cards" id="cards"></div>
<div class="areas" id="areas"></div>
<div id="table-view">
<div class="tools">
 <label>우선순위 <select id="f-pri"><option value="">전체</option><option>긴급</option><option>높음</option><option>보통</option></select></label>
 <label>영역 <select id="f-area"><option value="">전체</option></select></label>
 <label>분류 <select id="f-cat"><option value="">전체</option></select></label>
 <label>기법 <select id="f-tech"><option value="">전체</option></select></label>
 <label>페이지 <select id="f-page"><option value="">전체</option></select></label>
 <label>상태 <select id="f-status"><option value="">전체</option><option>미처리</option><option>조치중</option><option>완료</option></select></label>
 <label><input type="checkbox" id="f-off"> 요강 4종만</label>
 <label>검색 <input id="f-q" placeholder="텍스트·URL·선택자·도메인"></label>
 <span id="count"></span>
</div>
<table><thead><tr>
<th data-k="priority">우선순위</th><th data-k="area">영역</th><th data-k="official">기법/유형</th><th data-k="category">분류</th>
<th data-k="page_url">페이지</th><th data-k="location">위치(CSS 선택자)</th><th>근거 텍스트</th><th>조치</th><th>상태/메모</th></tr></thead>
<tbody id="rows"></tbody></table>
</div>
<div id="order"></div>
</main>
<footer>result.json(요강 4종) / result_extra.json(추가 탐지)은 구동 파일 폴더에 생성됩니다. 본 리포트는 두 파일의 합집합이며, 링크는 실수 클릭 방지를 위해 defang(hxxp, [.]) 표기를 병기합니다.
처리 상태·메모는 이 브라우저(localStorage)에 지문(SHA-256) 기준으로 저장됩니다.</footer>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const m=D.meta;const F=D.findings;
const SKEY='iad-status-'+(m.entry_url||'');
let STATE={};try{STATE=JSON.parse(localStorage.getItem(SKEY)||'{}')}catch(e){STATE={}}
function saveState(){try{localStorage.setItem(SKEY,JSON.stringify(STATE))}catch(e){}}
function st(f){return STATE[f.fingerprint]||{status:'미처리',memo:''}}
document.getElementById('meta').textContent=`진입 URL: ${m.entry_url} · 시작 ${m.started_at} · 완료 ${m.finished_at} · 소요 ${m.elapsed_sec}s · 페이지 ${m.pages}개` + (m.stopped_reason?` · ${m.stopped_reason}`:'');
const cnt=(k,v)=>F.filter(f=>f[k]===v).length;
const off=F.reduce((a,f)=>a+f.official.length,0);
function cards(){
 const done=F.filter(f=>st(f).status==='완료').length;
 document.getElementById('cards').innerHTML=[
 ['탐지 건수',F.length],['요강 4종 검출',off],['긴급',cnt('priority','긴급')],['높음',cnt('priority','높음')],['보통',cnt('priority','보통')],
 ['처리 완료',`${done}/${F.length}`],['페이지',m.pages],['소요(초)',m.elapsed_sec]].map(([k,v])=>`<div class="card"><b>${v}</b><span>${k}</span></div>`).join('');
 const byArea={};F.forEach(f=>byArea[f.area]=(byArea[f.area]||0)+1);
 document.getElementById('areas').innerHTML=Object.entries(byArea).sort((a,b)=>b[1]-a[1]).map(([a,n])=>`<span onclick="document.getElementById('f-area').value='${esc(a)}';render()">${esc(a)} ${n}</span>`).join('');
}
function fill(id,vals){const s=document.getElementById(id);[...new Set(vals)].sort().forEach(v=>{const o=document.createElement('option');o.textContent=v;s.appendChild(o);});}
fill('f-area',F.map(f=>f.area));fill('f-cat',F.map(f=>f.category));fill('f-tech',F.flatMap(f=>f.official.concat(f.extra_names)));fill('f-page',F.map(f=>f.page_url));
let sortK='priority',sortDir=1;
const PORD={'긴급':0,'높음':1,'보통':2};
function guideHtml(f){return f.guide.map(g=>`<div><b>${esc(g.name)}</b> — ${esc(g.summary)}<ol class="steps">${g.steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol></div>`).join('')+`<div><small>신고처: ${esc(f.contact)}</small></div>`;}
function copy(btn){const t=btn.dataset.v||'';if(navigator.clipboard){navigator.clipboard.writeText(t).then(()=>{btn.textContent='복사됨';setTimeout(()=>btn.textContent='복사',900)}).catch(()=>{})}else{const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}catch(e){}ta.remove();btn.textContent='복사됨';setTimeout(()=>btn.textContent='복사',900)}}
function setStatus(fp,v){STATE[fp]=Object.assign(st({fingerprint:fp}),{status:v});saveState();cards();render(false)}
function setMemo(fp,v){STATE[fp]=Object.assign(st({fingerprint:fp}),{memo:v});saveState()}
function filtered(){
 const pr=document.getElementById('f-pri').value,ar=document.getElementById('f-area').value,c=document.getElementById('f-cat').value,t=document.getElementById('f-tech').value,p=document.getElementById('f-page').value,s=document.getElementById('f-status').value,o=document.getElementById('f-off').checked,q=document.getElementById('f-q').value.toLowerCase();
 let rows=F.filter(f=>(!pr||f.priority===pr)&&(!ar||f.area===ar)&&(!c||f.category===c)&&(!t||f.official.includes(t)||f.extra_names.includes(t))&&(!p||f.page_url===p)&&(!s||st(f).status===s)&&(!o||f.official.length)&&(!q||(f.evidence_text+f.page_url+f.location+f.snippet+f.links.join(' ')).toLowerCase().includes(q)));
 rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(sortK==='priority'){x=PORD[x];y=PORD[y]}if(Array.isArray(x)){x=x.join();y=y.join()}return (x>y?1:x<y?-1:0)*sortDir;});
 return rows;
}
function render(focus=true){
 const rows=filtered();
 document.getElementById('count').textContent=`${rows.length}건 표시`;
 document.getElementById('rows').innerHTML=rows.map(f=>{const s=st(f);return `<tr class="status-${s.status==='완료'?'done':'open'}">
 <td class="p-${f.priority}">${f.priority}<br><small class="r-${f.risk}">${f.risk} ${f.score}</small></td><td><span class="tag area">${esc(f.area)}</span></td>
 <td>${f.official.map(o=>`<span class="tag off">${o}</span>`).join('')}${f.extra_names.map(o=>`<span class="tag">${esc(o)}</span>`).join('')}</td><td>${esc(f.category)}</td>
 <td><a href="${esc(f.page_url)}" target="_blank" rel="noopener">${esc(f.page_url)}</a><button class="copy" data-v="${esc(f.page_url)}" onclick="copy(this)">복사</button><br><small class="loc">${esc(f.defanged_url)}</small>${f.frame_url?`<br><small>iframe: ${esc(f.frame_url)}</small>`:''}</td>
 <td class="loc">${esc(f.location)}<button class="copy" data-v="${esc(f.location)}" onclick="copy(this)">복사</button><br><span class="fp">SHA-256 ${f.fingerprint.slice(0,16)}…</span></td>
 <td>${esc(f.evidence_text.slice(0,200))}${f.links.length?`<br><small class="loc">링크: ${f.defanged_links.map(esc).join(', ')}</small>`:''}</td>
 <td><details><summary>조치 가이드</summary>${guideHtml(f)}</details><details><summary>근거 ${f.evidence.length}개</summary><ul class="ev">${f.evidence.map(e=>`<li class="${e.weight<0?'neg':''}">${esc(e.detail)} <small>(${e.weight>0?'+':''}${e.weight})</small></li>`).join('')}</ul><pre>${esc(f.html)}</pre>${f.screenshot?`<img class="shot" src="${esc(f.screenshot)}">`:''}</details></td>
 <td><select onchange="setStatus('${f.fingerprint}',this.value)">${['미처리','조치중','완료'].map(v=>`<option ${s.status===v?'selected':''}>${v}</option>`).join('')}</select><br><textarea rows="2" cols="14" placeholder="담당/메모" onchange="setMemo('${f.fingerprint}',this.value)">${esc(s.memo)}</textarea></td></tr>`}).join('');
 renderOrder(rows);
}
function renderOrder(rows){
 const byPage={};rows.forEach(f=>(byPage[f.page_url]=byPage[f.page_url]||[]).push(f));
 document.getElementById('order').innerHTML=`<p>작성 ${new Date().toLocaleString('ko-KR')} · 대상 ${Object.keys(byPage).length}페이지 ${rows.length}건 · 진입 URL ${esc(m.entry_url)}</p>`+Object.entries(byPage).map(([u,fs])=>`<div class="page"><h3>${esc(u)}</h3><small class="loc">${esc(fs[0].defanged_url)}</small>`+fs.map((f,i)=>{const s=st(f);return `<div class="item"><b>${i+1}. [${f.priority}] ${esc(f.area)} · ${f.official.concat(f.extra_names).map(esc).join('+')} · ${esc(f.category)}</b> <small>(${s.status}${s.memo?' · '+esc(s.memo):''})</small>
 <span class="loc">위치: ${esc(f.location)}</span><span>근거: ${esc(f.evidence_text.slice(0,160))}</span>${f.links.length?`<br><small class="loc">링크: ${f.defanged_links.map(esc).join(', ')}</small>`:''}
 ${guideHtml(f)}<span class="fp">지문 ${f.fingerprint}</span></div>`}).join('')+'</div>').join('');
}
function toggleView(){const o=document.getElementById('order'),t=document.getElementById('table-view'),b=document.getElementById('viewbtn');const on=o.style.display==='block';o.style.display=on?'none':'block';t.style.display=on?'block':'none';b.textContent=on?'작업지시서 보기':'표로 돌아가기';}
function exportJson(){const out=F.map(f=>Object.assign({id:f.fingerprint,url:f.page_url,location:f.location,technique:f.official.concat(f.extra_names).join('+')},st(f)));const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{type:'application/json'}));a.download='iad_status.json';a.click();}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=1}render();});
['f-pri','f-area','f-cat','f-tech','f-page','f-status','f-off'].forEach(id=>document.getElementById(id).onchange=()=>render());
document.getElementById('f-q').oninput=()=>render();cards();render();
</script></body></html>
"""


def finding_rows(findings: list[Finding]) -> list[dict]:
    rows = []
    for f in findings:
        d = f.to_dict()
        d.update(enrich(f))
        rows.append(d)
    return rows


def write_reports(res, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "entry_url": res.entry_url, "started_at": res.started.isoformat(timespec="seconds"),
        "finished_at": res.finished.isoformat(timespec="seconds"), "elapsed_sec": round(res.elapsed, 1),
        "pages": len(res.pages), "stopped_reason": res.stopped_reason, "render_used": res.render_used,
        "browser_stage": getattr(res, "browser_note", ""), "ocr_stage": getattr(res, "ocr_note", ""),
    }
    rows = finding_rows(res.findings)
    data = json.dumps({"meta": meta, "findings": rows}, ensure_ascii=False).replace("</", "<\\/")
    html_path = out_dir / "report.html"
    html_path.write_text(TEMPLATE.replace("__DATA__", data), encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps({"meta": meta, "findings": rows}, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    with open(out_dir / "report.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["우선순위", "영역", "위험도", "점수", "분류", "요강기법", "추가유형", "페이지URL", "페이지URL(defang)", "iframeURL",
                    "위치(CSS)", "근거텍스트", "근거목록", "링크(defang)", "조치요약", "신고처", "지문(SHA-256)"])
        for f, r in zip(res.findings, rows):
            w.writerow([r["priority"], r["area"], f.risk, f.score, f.category, "|".join(f.official), "|".join(f.extra_names),
                        f.page_url, r["defanged_url"], f.frame_url or "", f.location, f.evidence_text[:300],
                        " ; ".join(f"{e.detail}({e.weight:+})" for e in f.evidence), " ".join(r["defanged_links"]),
                        " / ".join(f"{g['name']}: {g['summary']} → " + "; ".join(g["steps"]) for g in r["guide"]),
                        r["contact"], r["fingerprint"]])
    return html_path


__all__ = ["write_reports", "html"]
