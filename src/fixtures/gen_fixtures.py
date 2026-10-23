"""가짜 공공기관 사이트 픽스처 생성기 — 실제 구현은 iad/testbed.py (PyInstaller 번들에 포함되도록 패키지 안에 둔다).

python src/fixtures/gen_fixtures.py [--port 8765]
- dev/     : 규칙 튜닝용
- holdout/ : 검증용(규칙 튜닝에 쓰지 않음)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from iad.testbed import CSS, Site, TestbedHandler, generate, pick_port, serve  # noqa: E402,F401

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    d = generate(HERE, a.port)
    print(f"labels: {len(d['labels'])}")
