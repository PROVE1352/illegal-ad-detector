"""CLI exe 진입점 (src/run_cli.py 가 없을 때 iad.spec 이 사용한다).

`python -m iad ...` 와 같은 동작을 한다.
"""
import runpy
import sys

if __name__ == "__main__":
    sys.argv[0] = "iad-cli"
    runpy.run_module("iad", run_name="__main__", alter_sys=True)
