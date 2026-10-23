"""브라우저가 없을 때의 대체: 인라인 <script> 를 QuickJS(휠 0.38MB)로 스텁 DOM 위에서 실행해
document.write / innerHTML / insertAdjacentHTML / appendChild / location 대입으로 '쓰인' HTML 을 모은다.

공개 함수
    run_inline_scripts(html, time_limit_s=1.0, mem_mb=64) -> dict
        {"written": [html 조각...], "redirects": [url...], "errors": int, "engine": "quickjs"|None}
quickjs 가 없으면 engine=None, written=[] (호출측은 정적 결과만 사용).

주의: quickjs 바인딩은 time limit 설정 중 Python 콜백 호출을 금지하므로 atob 등은 순수 JS로 둔다.
안전성: 스크립트마다 새 Context, set_time_limit(무한루프 차단), set_memory_limit, set_max_stack_size.
네트워크·파일 API 는 스텁에 없으므로 외부 접근 불가(QuickJS 자체가 I/O 미보유).
"""
from __future__ import annotations

import base64
import json
import re
from html.parser import HTMLParser

try:
    import quickjs  # type: ignore
except ImportError:  # 번들에 없으면 조용히 비활성
    quickjs = None

STUB_JS = r"""
var __out = [], __redir = [], __timers = [];
function __rec(s){ try { __out.push(String(s)); } catch(e){} }
function __El(tag, id){
  this.tagName = (tag||'div').toUpperCase(); this.id = id||''; this.children = []; this.style = {};
  this.attributes = {}; this._html = '';
}
__El.prototype = {
  set innerHTML(v){ this._html = String(v); __rec(v); }, get innerHTML(){ return this._html; },
  set outerHTML(v){ __rec(v); }, get outerHTML(){ return '<'+this.tagName.toLowerCase()+'>'+this._html+'</'+this.tagName.toLowerCase()+'>'; },
  set textContent(v){ this._html = String(v); __rec(v); }, get textContent(){ return this._html; },
  set innerText(v){ this.textContent = v; }, get innerText(){ return this._html; },
  setAttribute: function(k,v){ this.attributes[k]=String(v); if(k==='href'||k==='src') this[k]=String(v); },
  getAttribute: function(k){ return this.attributes[k]===undefined?null:this.attributes[k]; },
  appendChild: function(c){ this.children.push(c); if (c && c.tagName) {
      var a=''; for (var k in c.attributes) a+=' '+k+'="'+c.attributes[k]+'"';
      if (c.href) a+=' href="'+c.href+'"'; if (c.src) a+=' src="'+c.src+'"';
      __rec('<'+c.tagName.toLowerCase()+a+'>'+(c._html||'')+'</'+c.tagName.toLowerCase()+'>'); }
    else if (c && c.data) __rec(c.data); return c; },
  insertBefore: function(c){ return this.appendChild(c); }, prepend: function(c){ return this.appendChild(c); },
  append: function(){ for (var i=0;i<arguments.length;i++) { var c=arguments[i]; if (typeof c==='string') __rec(c); else this.appendChild(c); } },
  insertAdjacentHTML: function(p, h){ __rec(h); }, removeChild: function(c){ return c; }, remove: function(){},
  addEventListener: function(t, f){ if (t==='load'||t==='DOMContentLoaded') __timers.push(f); },
  querySelector: function(){ return new __El('div'); }, querySelectorAll: function(){ return []; },
  getElementsByTagName: function(){ return [new __El('div')]; }, classList: {add:function(){},remove:function(){}}
};
var __body = new __El('body'), __head = new __El('head');
var document = {
  write: function(){ for (var i=0;i<arguments.length;i++) __rec(arguments[i]); },
  writeln: function(){ for (var i=0;i<arguments.length;i++) __rec(arguments[i]); },
  createElement: function(t){ return new __El(t); }, createTextNode: function(t){ return {data:String(t)}; },
  getElementById: function(id){ return new __El('div', id); },
  querySelector: function(){ return new __El('div'); }, querySelectorAll: function(){ return []; },
  getElementsByTagName: function(t){ return [t==='head'?__head:__body]; },
  getElementsByClassName: function(){ return [new __El('div')]; },
  addEventListener: function(t, f){ __timers.push(f); },
  body: __body, head: __head, documentElement: __body, referrer: 'https://www.google.com/', cookie: '',
  readyState: 'complete', title: '', domain: 'localhost'
};
var __loc = { href: 'http://localhost/', hostname: 'localhost', pathname: '/', search: '', protocol: 'http:',
  replace: function(u){ __redir.push(String(u)); }, assign: function(u){ __redir.push(String(u)); } };
var navigator = { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36', language: 'ko-KR', webdriver: false };
var window = this; window.document = document; window.navigator = navigator; window.top = window; window.self = window;
Object.defineProperty(window, 'location', { get: function(){ return __loc; }, set: function(u){ __redir.push(String(u)); } });
Object.defineProperty(document, 'location', { get: function(){ return __loc; }, set: function(u){ __redir.push(String(u)); } });
var screen = { width: 1366, height: 900 }; var innerWidth = 1366, innerHeight = 900;
var localStorage = { getItem: function(){ return null; }, setItem: function(){} }; var sessionStorage = localStorage;
function setTimeout(f){ if (typeof f === 'function') __timers.push(f); else if (typeof f === 'string') __timers.push(function(){ eval(f); }); return __timers.length; }
var setInterval = setTimeout; function clearTimeout(){} var clearInterval = clearTimeout;
var __B64='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function atob(s){ s=String(s).replace(/[^A-Za-z0-9+\/]/g,''); var o='',b=0,n=0;
  for (var i=0;i<s.length;i++){ b=(b<<6)|__B64.indexOf(s.charAt(i)); n+=6; if(n>=8){ n-=8; o+=String.fromCharCode((b>>n)&255); } } return o; }
function btoa(s){ s=String(s); var o='';
  for (var i=0;i<s.length;i+=3){ var c=(s.charCodeAt(i)<<16)|((s.charCodeAt(i+1)||0)<<8)|(s.charCodeAt(i+2)||0);
    o+=__B64.charAt(c>>18&63)+__B64.charAt(c>>12&63)+(i+1<s.length?__B64.charAt(c>>6&63):'=')+(i+2<s.length?__B64.charAt(c&63):'='); } return o; }
var console = { log: function(){}, warn: function(){}, error: function(){} };
function __flush(){ for (var i=0; i<__timers.length && i<200; i++) { try { __timers[i](); } catch(e){} } }
function __result(){ return JSON.stringify({w: __out, r: __redir}); }
"""


class _ScriptGrab(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts, self._in, self._buf = [], False, []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            a = dict(attrs)
            typ = (a.get("type") or "text/javascript").lower()
            self._in = "src" not in a and ("javascript" in typ or typ in ("module", "text/ecmascript"))
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in:
            self.scripts.append("".join(self._buf))
            self._in = False

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)


def _py_atob(s: str) -> str:
    try:
        s = re.sub(r"\s", "", s)
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("latin-1")
    except Exception:
        return ""


def _py_btoa(s: str) -> str:
    try:
        return base64.b64encode(s.encode("latin-1")).decode()
    except Exception:
        return ""


def run_inline_scripts(html: str, time_limit_s: float = 1.0, mem_mb: int = 64,
                       max_scripts: int = 200) -> dict:
    res = {"written": [], "redirects": [], "errors": 0, "engine": None}
    if quickjs is None:
        return res
    res["engine"] = "quickjs"
    g = _ScriptGrab()
    try:
        g.feed(html)
    except Exception:
        pass
    for src in g.scripts[:max_scripts]:
        if not src.strip():
            continue
        ctx = quickjs.Context()
        ctx.set_memory_limit(mem_mb * 1024 * 1024)
        ctx.set_max_stack_size(1024 * 1024)
        ctx.eval(STUB_JS)
        ctx.set_time_limit(time_limit_s)  # 스크립트 + 타이머 콜백 합산 CPU 시간 상한
        try:
            ctx.eval(src)
        except Exception:
            res["errors"] += 1  # 미지원 API·문법·타임아웃. 그 전까지 쓰인 것은 아래에서 회수
        try:
            ctx.eval("__flush()")
        except Exception:
            pass
        ctx.set_time_limit(-1)
        try:
            out = json.loads(ctx.eval("__result()"))
            res["written"].extend(x for x in out["w"] if x and x.strip())
            res["redirects"].extend(out["r"])
        except Exception:
            pass
    return res


if __name__ == "__main__":
    import os
    import sys
    import time
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fixtures", "js_inject.html")
    t0 = time.time()
    r = run_inline_scripts(open(p, encoding="utf-8").read())
    print(f"elapsed {time.time() - t0:.2f}s engine={r['engine']} errors={r['errors']}")
    for w in r["written"]:
        print("WRITTEN:", w[:200])
    for u in r["redirects"]:
        print("REDIRECT:", u)
