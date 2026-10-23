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
        ttk.Checkbutton(opts, text="robots.txt 존중", variable=self.robots).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="외부 iframe 수집", variable=self.ext_iframe).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="클로킹 점검(봇 UA 재요청)", variable=self.cloak).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Edge 렌더 비교(선택, 느림)", variable=self.render).pack(side="left", padx=4)
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
        cols = ("risk", "tech", "category", "url", "location", "evidence")
        self.tree = ttk.Treeview(resf, columns=cols, show="headings")
        for c, t, w in (("risk", "위험도", 60), ("tech", "기법", 120), ("category", "분류", 80), ("url", "페이지 URL", 260),
                        ("location", "위치(CSS)", 260), ("evidence", "근거 텍스트", 260)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        tsb = ttk.Scrollbar(resf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tsb.pack(side="right", fill="y")
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
                          cloak_pages=40 if self.cloak.get() else 0)
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
        self.stop_btn.configure(state="disabled")
        self.result = res
        if res is None:
            return
        self.open_btn.configure(state="normal")
        n_off = sum(len(f.official) for f in res.findings)
        self.summary.configure(text=f"페이지 {len(res.pages)}개 · 탐지 {len(res.findings)}건 (요강 4종 {n_off}건, 추가 {len(res.findings) - sum(1 for f in res.findings if f.official and not f.extra_names)}건) · "
                                    f"소요 {res.elapsed:.1f}초 · result.json: {res.result_json}")
        order = {"높음": 0, "중간": 1, "낮음": 2}
        for f in sorted(res.findings, key=lambda x: (order.get(x.risk, 3), -x.score)):
            self.tree.insert("", "end", values=(f.risk, "|".join(f.official + f.extra_names), f.category, f.page_url,
                                                f.location, f.evidence_text[:120]))
        self.nb.select(1)
        self.log(f"요약: 탐지 {len(res.findings)}건, 요강 4종 {n_off}건. '리포트 열기'로 상세를 확인하세요.")

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
