"""CDP(DevTools Protocol)로 브라우저가 실제 계산한 스타일·위치를 받아 숨김 여부를 판정하는 시제품.

추가 번들 0: websocket 클라이언트를 표준 라이브러리(socket)로 최소 구현했다(텍스트 프레임만).
공개 함수
    probe(url, timeout_s=20.0, settle_ms=1500) -> dict | None
        {"dom": str, "elements": [{"tag","text","href","rect","reasons":[...]}], "partial": bool}
        reasons 값: DISPLAY_NONE, VISIBILITY_HIDDEN, OPACITY_ZERO, TRANSPARENT_TEXT, SAME_COLOR,
                    OFFSCREEN, ZERO_SIZE, TINY_FONT, CLIPPED, BEHIND(z-index 로 다른 요소에 가려짐)
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

from edge_dump import COMMON_FLAGS, _popen_kwargs, _to_url, find_browser, kill_tree


class MiniWS:
    """RFC6455 최소 클라이언트. CDP 는 로컬 ws:// 텍스트 프레임만 쓰므로 충분."""

    def __init__(self, ws_url: str, timeout: float):
        u = urlparse(ws_url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("handshake closed")
            buf += chunk
        head, self._rest = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head[:200])

    def _recv_exact(self, n: int) -> bytes:
        out = self._rest[:n]
        self._rest = self._rest[n:]
        while len(out) < n:
            chunk = self.sock.recv(max(65536, n - len(out)))
            if not chunk:
                raise ConnectionError("closed")
            out += chunk
        if len(out) > n:
            self._rest = out[n:] + self._rest
            out = out[:n]
        return out

    def send(self, text: str) -> None:
        data = text.encode()
        hdr = bytearray([0x81])
        n = len(data)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126); hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127); hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        self.sock.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self) -> str:
        parts = []
        while True:
            b1, b2 = self._recv_exact(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv_exact(8))[0]
            if b2 & 0x80:
                self._recv_exact(4)  # 서버는 마스킹하지 않지만 방어
            payload = self._recv_exact(n)
            if op == 0x8:
                raise ConnectionError("ws close")
            if op == 0x9:  # ping
                continue
            parts.append(payload)
            if b1 & 0x80:
                return b"".join(parts).decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CDP:
    def __init__(self, ws: MiniWS):
        self.ws, self.i, self.events = ws, 0, []

    def call(self, method: str, params: dict | None = None, deadline: float | None = None) -> dict:
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            if deadline and time.time() > deadline:
                raise TimeoutError(method)
            self.ws.sock.settimeout(max(0.1, (deadline - time.time()) if deadline else 30))
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})
            self.events.append(msg)

    def wait_event(self, name: str, deadline: float) -> bool:
        if any(e.get("method") == name for e in self.events):
            return True
        while time.time() < deadline:
            self.ws.sock.settimeout(max(0.1, deadline - time.time()))
            try:
                msg = json.loads(self.ws.recv())
            except (socket.timeout, TimeoutError):
                return False
            if msg.get("method") == name:
                return True
        return False


# 브라우저 안에서 도는 판정 스크립트. 텍스트를 가진 요소와 링크만 본다.
PROBE_JS = r"""
(() => {
  const vw = Math.max(document.documentElement.scrollWidth, innerWidth);
  const vh = Math.max(document.documentElement.scrollHeight, innerHeight);
  const parseRGBA = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0],p[1],p[2], p.length>3?p[3]:1]; };
  const bgOf = el => { for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const c = parseRGBA(getComputedStyle(e).backgroundColor); if (c && c[3] > 0.05) return c; }
    return [255,255,255,1]; };
  const effOpacity = el => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement)
      o *= parseFloat(getComputedStyle(e).opacity); return o; };
  const lum = c => { const f = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); };
      return 0.2126*f(c[0])+0.7152*f(c[1])+0.0722*f(c[2]); };
  const contrast = (a,b) => { const x=lum(a), y=lum(b); return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05); };
  const clippedByAncestor = (el, r) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      const s = getComputedStyle(e); if (s.clipPath !== 'none' || s.clip !== 'auto') return true; if (s.overflow === 'visible') continue;
      const pr = e.getBoundingClientRect();
      if (pr.width < 2 || pr.height < 2) return true;
      if (r.right <= pr.left || r.left >= pr.right || r.bottom <= pr.top || r.top >= pr.bottom) return true; }
    return false; };
  const out = [];
  const els = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of els) {
    if (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','META','LINK'].includes(el.tagName)) continue;
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    const isLink = el.tagName === 'A' && el.getAttribute('href');
    if (!own && !isLink) continue;
    const s = getComputedStyle(el), r = el.getBoundingClientRect(), why = [];
    if (!el.checkVisibility()) why.push(s.display === 'none' ? 'DISPLAY_NONE' : 'DISPLAY_NONE_ANCESTOR');
    if (s.visibility !== 'visible') why.push('VISIBILITY_HIDDEN');
    if (effOpacity(el) < 0.05) why.push('OPACITY_ZERO');
    const fg = parseRGBA(s.color);
    if (fg && fg[3] < 0.05) why.push('TRANSPARENT_TEXT');
    else if (fg && own && contrast(fg, bgOf(el)) < 1.15) why.push('SAME_COLOR');
    if (r.width * r.height > 0 && (r.right + scrollX <= 0 || r.bottom + scrollY <= 0 || r.left + scrollX >= vw || r.top + scrollY >= vh)) why.push('OFFSCREEN');
    if (el.checkVisibility() && (r.width < 2 || r.height < 2)) why.push('ZERO_SIZE');
    if (parseFloat(s.fontSize) < 3 && own) why.push('TINY_FONT');
    if (s.clipPath !== 'none' || s.clip !== 'auto' || clippedByAncestor(el, r)) why.push('CLIPPED');
    if (!why.length && r.width > 0 && r.height > 0) {
      const cx = r.left + r.width/2, cy = r.top + r.height/2;
      if (cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight) {
        const top = document.elementFromPoint(cx, cy);
        if (top && top !== el && !el.contains(top) && !top.contains(el)) why.push('BEHIND');
      }
    }
    out.push({tag: el.tagName.toLowerCase(), text: (own || el.textContent).trim().slice(0, 200),
              href: isLink ? el.href : null, rect: [r.left|0, r.top|0, r.width|0, r.height|0], reasons: why});
  }
  return {elements: out, dom: document.documentElement.outerHTML};
})()
"""


def probe(url: str, timeout_s: float = 20.0, settle_ms: int = 1500, browser: str | None = None) -> dict | None:
    exe = browser or find_browser()
    if not exe:
        return None
    deadline = time.time() + timeout_s
    profile = tempfile.mkdtemp(prefix="iad_cdp_")
    # Chrome 136+ 는 기본 프로필에 대한 원격 디버깅을 막으므로 반드시 별도 --user-data-dir.
    args = [exe, *COMMON_FLAGS, f"--user-data-dir={profile}", "--remote-debugging-port=0",
            "--remote-allow-origins=*", "about:blank"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, **_popen_kwargs())
    ws = None
    try:
        port_file = os.path.join(profile, "DevToolsActivePort")
        while not os.path.isfile(port_file) or os.path.getsize(port_file) == 0:
            if time.time() > deadline or proc.poll() is not None:
                return None
            time.sleep(0.05)
        port = int(open(port_file).read().split()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
            targets = [t for t in json.load(r) if t.get("type") == "page"]
        ws = MiniWS(targets[0]["webSocketDebuggerUrl"], timeout=5)
        cdp = CDP(ws)
        cdp.call("Page.enable", deadline=deadline)
        cdp.call("Page.navigate", {"url": _to_url(url)}, deadline=deadline)
        load_deadline = min(deadline - 3, time.time() + max(3.0, timeout_s * 0.5))
        loaded = cdp.wait_event("Page.loadEventFired", load_deadline)
        time.sleep(settle_ms / 1000)
        partial = not loaded
        try:
            res = cdp.call("Runtime.evaluate", {"expression": PROBE_JS, "returnByValue": True},
                           deadline=min(deadline - 1.5, time.time() + 5))
        except (TimeoutError, socket.timeout):
            # 무한루프 스크립트가 메인 스레드를 잡고 있음 → 같은 연결에서 실행 강제 종료 후 재시도(부분 DOM)
            cdp.call("Runtime.terminateExecution", deadline=time.time() + 2)
            res = cdp.call("Runtime.evaluate", {"expression": PROBE_JS, "returnByValue": True},
                           deadline=time.time() + 3)
            partial = True
        val = res.get("result", {}).get("value")
        if not isinstance(val, dict):
            return None
        val["partial"] = partial
        return val
    except Exception as e:
        if os.environ.get('IAD_DEBUG'):
            import traceback; traceback.print_exc()
        return None
    finally:
        if ws:
            ws.close()
        kill_tree(proc)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fixtures", "js_inject.html")
    t0 = time.time()
    r = probe(t, timeout_s=float(os.environ.get("IAD_TIMEOUT", "20")))
    print(f"elapsed {time.time() - t0:.2f}s")
    if r is None:
        print("None")
    else:
        print("partial:", r["partial"], "dom_len:", len(r["dom"]))
        for e in r["elements"]:
            print(f'{",".join(e["reasons"]) or "visible":28s} {e["tag"]:5s} {e["text"][:40]!r} {e["href"] or ""}')
