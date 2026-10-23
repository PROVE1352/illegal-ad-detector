# PyInstaller runtime hook (src 코드를 건드리지 않고 실행 환경만 보정한다).
#
# 1) 한글 출력: Windows 기본 코드페이지(cp949/cp1252)에서 파이프·리다이렉트로
#    출력할 때 UnicodeEncodeError 가 나지 않도록 stdout/stderr 를 UTF-8 로 바꾼다.
#    --windowed GUI 에서는 sys.stdout/stderr 가 None 이므로 건드리지 않는다.
# 2) 스모크 테스트(IAD_SMOKE=1)일 때만: tkinter mainloop 진입 시 마커 파일을 쓰고
#    몇 초 뒤 창을 닫아 정상 종료시킨다. 창이 뜨기 전에 죽거나 예외 대화상자에
#    걸리면 마커가 생기지 않으므로 CI 가 실패를 잡을 수 있다.
import os
import sys

for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

if os.environ.get("IAD_SMOKE") == "1":
    _marker = os.environ.get("IAD_SMOKE_MARKER")
    _log = os.environ.get("IAD_SMOKE_LOG")
    _seconds = int(os.environ.get("IAD_SMOKE_SECONDS", "5"))

    if _log and sys.stderr is None:
        try:
            sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stderr
        except Exception:
            pass

    def _write_marker(text):
        if not _marker:
            return
        try:
            with open(_marker, "a", encoding="utf-8") as fp:
                fp.write(text + "\n")
        except Exception:
            pass

    try:
        import tkinter as _tk

        _orig_misc_mainloop = _tk.Misc.mainloop

        _capture = os.environ.get("IAD_SMOKE_CAPTURE") == "1"   # 캡처 모드: 첫 화면 → 데모 실행 → 결과 화면
        _ack_dir = os.environ.get("IAD_SMOKE_ACK_DIR", "")

        if _capture:
            # 데모가 끝나면 GUI 가 리포트를 브라우저로 여는데, 캡처 화면을 가리지 않도록 막는다.
            import webbrowser as _wb

            _wb.open = lambda *a, **k: True
            _wb.open_new = _wb.open_new_tab = _wb.open

        def _ack(name):
            return bool(_ack_dir) and os.path.exists(os.path.join(_ack_dir, name))

        def _capture_flow(root):
            state = {"seen_disabled": False, "t": 0}

            def front():
                try:
                    root.deiconify()
                    root.lift()
                    root.attributes("-topmost", True)
                    root.focus_force()
                except Exception:
                    pass

            def wait_ack(name, then):
                if _ack(name):
                    then()
                else:
                    root.after(300, lambda: wait_ack(name, then))

            def shot1():
                front()
                root.update_idletasks()
                _write_marker("shot1-ready")
                wait_ack("ack1", start_demo)

            def start_demo():
                btn = getattr(root, "demo_btn", None)
                if btn is None:
                    _write_marker("demo-button-missing")
                    root.destroy()
                    return
                btn.invoke()
                _write_marker("demo-started")
                root.after(500, poll_demo)

            def poll_demo():
                btn = root.demo_btn
                st = str(btn.cget("state"))
                if st == "disabled":
                    state["seen_disabled"] = True
                if state["seen_disabled"] and st != "disabled":
                    root.after(1500, shot2)
                else:
                    root.after(500, poll_demo)

            def shot2():
                front()
                root.update_idletasks()
                _write_marker("shot2-ready")
                wait_ack("ack2", finish)

            def finish():
                _write_marker("capture-done")
                root.destroy()

            def overall_timeout():
                _write_marker("capture-timeout")
                root.destroy()

            root.after(240000, overall_timeout)
            root.after(2500, shot1)

        def _smoke_mainloop(self, n=0):
            _write_marker("mainloop-entered")
            try:
                root = self._root()
                if _capture:
                    _capture_flow(root)
                else:
                    root.after(_seconds * 1000, root.destroy)
            except Exception as exc:  # pragma: no cover
                _write_marker("after-failed: %r" % (exc,))
            return _orig_misc_mainloop(self, n)

        def _smoke_module_mainloop(n=0):
            root = getattr(_tk, "_default_root", None)
            if root is None:
                raise RuntimeError("tkinter.mainloop() called without a root window")
            return _smoke_mainloop(root, n)

        _tk.Misc.mainloop = _smoke_mainloop
        _tk.mainloop = _smoke_module_mainloop
    except Exception as exc:
        _write_marker("tkinter-unavailable: %r" % (exc,))
