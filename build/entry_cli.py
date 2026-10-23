"""CLI exe 진입점 (src/run_cli.py 가 없을 때 iad.spec 이 사용한다).

`python -m iad ...` 와 같은 동작을 한다. 정적 import 로 써야 PyInstaller 가 의존성을 따라간다.
"""
import sys

from iad.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
