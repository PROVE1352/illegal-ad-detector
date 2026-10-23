"""tkinter GUI: 진입 URL 입력 → 탐지 시작 → 진행 로그 → 결과 요약·관리 화면 → 리포트 열기.

PyInstaller 진입점. result.json / result_extra.json 은 exe 와 같은 폴더에 생성된다.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iad import __version__  # noqa: E402
from iad.crawler import CrawlConfig  # noqa: E402
from iad.official import run_dir  # noqa: E402
from iad.scan import ScanResult, scan  # noqa: E402
from iad.triage import area_of, contact_for, defang, fingerprint, guide_for, priority_of  # noqa: E402


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"공공 웹사이트 불법광고 탐지 도구 v{__version__}")
        self.geometry("980x720")
        self.minsize(820, 600)
        self.q: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_requested = False
        self.result: ScanResult | None = None
        self._build()
        self.after(150, self._poll)

    def _build(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="진입 URL (여러 개면 줄바꿈으로 구분, 순서대로 탐지)").grid(row=0, column=0, sticky="w", columnspan=6)
        self.url_box = tk.Text(top, height=3, width=100)
        self.url_box.grid(row=1, column=0, columnspan=6, sticky="we", pady=(2, 8))
        self.url_box.insert("1.0", "")
        ttk.Label(top, text="깊이").grid(row=2, column=0, sticky="e")
        self.depth = tk.IntVar(value=3)
        ttk.Spinbox(top, from_=0, to=10, textvariable=self.depth, width=5).grid(row=2, column=1, sticky="w")
        ttk.Label(top, text="최대 페이지").grid(row=2, column=2, sticky="e")
        self.max_pages = tk.IntVar(value=300)
        ttk.Spinbox(top, from_=1, to=5000, textvariable=self.max_pages, width=7).grid(row=2, column=3, sticky="w")
        ttk.Label(top, text="요청 간격(초)").grid(row=2, column=4, sticky="e")
        self.delay = tk.DoubleVar(value=0.3)
        ttk.Spinbox(top, from_=0, to=5, increment=0.1, textvariable=self.delay, width=5).grid(row=2, column=5, sticky="w")
        opts = ttk.Frame(top)
        opts.grid(row=3, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.robots = tk.BooleanVar(value=False)
        self.render = tk.BooleanVar(value=False)
        self.ext_iframe = tk.BooleanVar(value=True)
        self.cloak = tk.BooleanVar(value=True)
        self.browser = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="robots.txt 존중", variable=self.robots).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="외부 iframe 수집", variable=self.ext_iframe).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="클로킹 점검(봇 UA 재요청)", variable=self.cloak).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Edge JS 실행 비교(의심 스크립트 쪽만)", variable=self.browser).pack(side="left", padx=4)
        self.render_cb = ttk.Checkbutton(opts, text="Edge 렌더 비교(선택, 느림)", variable=self.render)
        self.render_cb.pack(side="left", padx=4)
        try:
            from iad.render import render_available
            static_only = not render_available()
        except Exception:
            static_only = True
        if static_only:   # 제출본은 playwright 없는 정적 빌드
            self.render.set(False)
            self.render_cb.configure(state="disabled")
            ttk.Label(opts, text="(이 배포본은 정적 분석 전용 —\n렌더 비교 미포함)", foreground="#667", justify="left",
                      wraplength=200).pack(side="left", padx=4)
        btns = ttk.Frame(top)
        btns.grid(row=4, column=0, columnspan=6, sticky="we", pady=(8, 0))
        self.start_btn = ttk.Button(btns, text="탐지 시작", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="중단", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.open_btn = ttk.Button(btns, text="리포트 열기", command=self.open_report, state="disabled")
        self.open_btn.pack(side="left", padx=6)
        self.folder_btn = ttk.Button(btns, text="결과 폴더 열기", command=self.open_folder)
        self.folder_btn.pack(side="left", padx=6)
        self.demo_btn = ttk.Button(btns, text="데모 실행(내장 테스트 사이트)", command=self.start_demo)
        self.demo_btn.pack(side="left", padx=6)
        self.status = ttk.Label(btns, text=f"결과 폴더: {run_dir()}")
        self.status.pack(side="left", padx=12)
        top.columnconfigure(5, weight=1)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        logf = ttk.Frame(nb)
        nb.add(logf, text="진행 로그")
        self.log_box = tk.Text(logf, wrap="word", state="disabled", font=("Consolas", 10))
        sb = ttk.Scrollbar(logf, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        resf = ttk.Frame(nb)
        nb.add(resf, text="검출 결과")
        self.summary = ttk.Label(resf, text="아직 결과가 없습니다.", padding=6)
        self.summary.pack(fill="x")
        bar = ttk.Frame(resf, padding=(6, 0, 6, 4))
        bar.pack(fill="x")
        self.only_official = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="요강 4종만", variable=self.only_official, command=self._refresh_tree).pack(side="left")
        ttk.Label(bar, text="  우선순위").pack(side="left")
        self.f_pri = ttk.Combobox(bar, values=("전체", "긴급", "높음", "보통"), width=6, state="readonly")
        self.f_pri.set("전체")
        self.f_pri.bind("<<ComboboxSelected>>", lambda e: self._refresh_tree())
        self.f_pri.pack(side="left")
        ttk.Label(bar, text="  영역").pack(side="left")
        self.f_area = ttk.Combobox(bar, values=("전체",), width=12, state="readonly")
        self.f_area.set("전체")
        self.f_area.bind("<<ComboboxSelected>>", lambda e: self._refresh_tree())
        self.f_area.pack(side="left")
        ttk.Label(bar, text="  검색").pack(side="left")
        self.f_q = ttk.Entry(bar, width=24)
        self.f_q.bind("<KeyRelease>", lambda e: self._refresh_tree())
        self.f_q.pack(side="left")
        ttk.Button(bar, text="선택 항목 상세/조치", command=self._show_detail).pack(side="right")
        ttk.Button(bar, text="선택자 복사", command=lambda: self._copy_selected("location")).pack(side="right", padx=4)
        ttk.Button(bar, text="URL 복사", command=lambda: self._copy_selected("url")).pack(side="right")
        cols = ("priority", "area", "tech", "category", "url", "location", "evidence")
        self.tree = ttk.Treeview(resf, columns=cols, show="headings")
        for c, t, w in (("priority", "우선순위", 60), ("area", "영역", 90), ("tech", "기법/유형", 150), ("category", "분류", 70),
                        ("url", "페이지 URL", 240), ("location", "위치(CSS)", 240), ("evidence", "근거 텍스트", 240)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("긴급", foreground="#7b1fa2")
        self.tree.tag_configure("높음", foreground="#c62828")
        self.tree.bind("<Double-1>", lambda e: self._show_detail())
        tsb = ttk.Scrollbar(resf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tsb.pack(side="right", fill="y")
        self._rows: dict[str, object] = {}
        self.nb = nb

    # ---------- 동작 ----------
    def log(self, msg: str) -> None:
        self.q.put(("log", msg))

    def start(self) -> None:
        urls = [u.strip() for u in self.url_box.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("입력 필요", "진입 URL을 입력하세요.")
            return
        self.stop_requested = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.open_btn.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        cfg = CrawlConfig(depth=self.depth.get(), max_pages=self.max_pages.get(), delay=self.delay.get(),
                          respect_robots=self.robots.get(), follow_external_iframes=self.ext_iframe.get(),
                          cloak_pages=40 if self.cloak.get() else 0, browser=self.browser.get())
        render = self.render.get()

        def work() -> None:
            last = None
            for i, u in enumerate(urls):
                if self.stop_requested:
                    break
                rd = run_dir() if i == 0 else run_dir() / f"result_{i + 1}"
                try:
                    last = scan(u, cfg, result_dir=rd, log=self.log, render=render, stop_flag=lambda: self.stop_requested)
                except Exception as e:
                    self.log(f"오류: {e!r}")
            self.q.put(("done", last))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def start_demo(self) -> None:
        """내장 테스트베드를 로컬(127.0.0.1)에 띄워 스캔하고 리포트를 연다. 결과는 구동 폴더/demo 에 쓴다."""
        from iad.demo import run_demo
        self.stop_requested = False
        self.start_btn.configure(state="disabled")
        self.demo_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.open_btn.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.nb.select(0)

        def work() -> None:
            last = None
            try:
                last = run_demo(log=self.log, stop_flag=lambda: self.stop_requested)
            except Exception as e:
                self.log(f"데모 오류: {e!r}")
            self.q.put(("done", last))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stop_requested = True
        self.log("중단 요청… 현재 페이지까지 처리 후 결과 파일을 생성합니다.")

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", str(payload) + "\n")
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
                elif kind == "done":
                    self._finish(payload)  # type: ignore[arg-type]
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _finish(self, res: ScanResult | None) -> None:
        self.start_btn.configure(state="normal")
        self.demo_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.result = res
        if res is None:
            return
        self.open_btn.configure(state="normal")
        n_off = sum(len(f.official) for f in res.findings)
        self.summary.configure(text=f"페이지 {len(res.pages)}개 · 탐지 {len(res.findings)}건 (요강 4종 {n_off}건, 추가 {len(res.findings) - sum(1 for f in res.findings if f.official and not f.extra_names)}건) · "
                                    f"소요 {res.elapsed:.1f}초 · result.json: {res.result_json}")
        areas = sorted({area_of(f) for f in res.findings})
        self.f_area.configure(values=("전체", *areas))
        self.f_area.set("전체")
        self._refresh_tree()
        self.nb.select(1)
        self.log(f"요약: 탐지 {len(res.findings)}건, 요강 4종 {n_off}건. 행을 더블클릭하면 조치 가이드가 열립니다. '리포트 열기'로 작업지시서를 확인하세요.")

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        if not self.result:
            return
        order = {"긴급": 0, "높음": 1, "보통": 2}
        pri = self.f_pri.get()
        area = self.f_area.get()
        q = self.f_q.get().strip().lower()
        rows = []
        for f in self.result.findings:
            p = priority_of(f)
            a = area_of(f)
            if self.only_official.get() and not f.official:
                continue
            if pri != "전체" and p != pri:
                continue
            if area != "전체" and a != area:
                continue
            if q and q not in (f.evidence_text + f.page_url + f.location + " ".join(f.links)).lower():
                continue
            rows.append((order.get(p, 3), -f.score, p, a, f))
        for _o, _s, p, a, f in sorted(rows, key=lambda r: (r[0], r[1])):
            iid = self.tree.insert("", "end", values=(p, a, "|".join(f.official + f.extra_names), f.category, f.page_url,
                                                      f.location, f.evidence_text[:120]), tags=(p,))
            self._rows[iid] = f
        self.summary.configure(text=self.summary.cget("text").split(" · 표시")[0] + f" · 표시 {len(rows)}건")

    def _selected(self):
        sel = self.tree.selection()
        return self._rows.get(sel[0]) if sel else None

    def _copy_selected(self, what: str) -> None:
        f = self._selected()
        if not f:
            return
        self.clipboard_clear()
        self.clipboard_append(f.location if what == "location" else f.page_url)

    def _show_detail(self) -> None:
        f = self._selected()
        if not f:
            return
        win = tk.Toplevel(self)
        win.title("검출 상세 · 조치 가이드")
        win.geometry("760x560")
        txt = tk.Text(win, wrap="word", font=("Malgun Gothic", 10))
        sb = ttk.Scrollbar(win, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        lines = [f"[{priority_of(f)}] {area_of(f)} · {'|'.join(f.official + f.extra_names)} · {f.category} · 위험도 {f.risk}({f.score})", "",
                 f"페이지: {f.page_url}", f"페이지(defang): {defang(f.page_url)}"]
        if f.frame_url:
            lines.append(f"iframe 문서: {f.frame_url}")
        lines += [f"위치(CSS 선택자): {f.location}", f"지문(SHA-256): {fingerprint(f)}", "", "근거 텍스트:", f.evidence_text[:500], ""]
        if f.links:
            lines += ["링크(defang):"] + [f"  - {defang(u)}" for u in f.links] + [""]
        lines.append("탐지 근거:")
        lines += [f"  {'+' if e.weight > 0 else ''}{e.weight}  {e.detail}" for e in f.evidence]
        lines += ["", "조치 가이드:"]
        for g in guide_for(f):
            lines.append(f"  ■ {g['name']} — {g['summary']}")
            lines += [f"     {i + 1}. {s}" for i, s in enumerate(g["steps"])]
        lines += ["", f"신고처: {contact_for(f)}", "", "원문 HTML:", f.html[:800]]
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")
        btns = ttk.Frame(win, padding=6)
        btns.pack(fill="x", side="bottom")
        ttk.Button(btns, text="선택자 복사", command=lambda: (self.clipboard_clear(), self.clipboard_append(f.location))).pack(side="left")
        ttk.Button(btns, text="URL 복사", command=lambda: (self.clipboard_clear(), self.clipboard_append(f.page_url))).pack(side="left", padx=4)
        ttk.Button(btns, text="페이지 열기", command=lambda: webbrowser.open(f.page_url)).pack(side="left")
        ttk.Button(btns, text="닫기", command=win.destroy).pack(side="right")
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def open_report(self) -> None:
        if self.result and self.result.report_html:
            webbrowser.open(self.result.report_html.resolve().as_uri())

    def open_folder(self) -> None:
        d = str(run_dir())
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showinfo("결과 폴더", f"{d}\n({e})")


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
