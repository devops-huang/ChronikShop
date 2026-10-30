#!/usr/bin/env python3
"""Preflight check: is this machine able to run the demo?

Run *before* `pip install`, with whatever python is lying around (even 2.7/3.6 —
this file intentionally uses no modern syntax on the import path):

    python3 scripts/doctor.py
    python  scripts/doctor.py      # whatever is on PATH

It answers four questions offline:
  1. Which interpreter am I on, and is it new enough?
  2. Is there a *newer* interpreter already installed that we should use instead?
  3. Are the dependencies installed and importable?
  4. Do we have a CJK font (only affects Chinese labels on the PNG review card)?
"""

from __future__ import print_function

import os
import platform
import shutil
import subprocess
import sys

MIN = (3, 9)
GOOD = [(3, 13), (3, 12), (3, 11), (3, 10), (3, 9)]
CANDIDATES = ["python3.13", "python3.12", "python3.11", "python3.10", "python3.9", "python3", "python"]

OK = "[ ok ]"
WARN = "[warn]"
FAIL = "[FAIL]"


def line(kind, msg):
    print("%s %s" % (kind, msg))


def find_interpreters():
    """Look for a usable interpreter in PATH and in the usual pyenv/conda spots."""
    found = []
    seen = set()
    search = list(CANDIDATES)
    for d in ("/usr/local/bin", "/opt/python/bin", os.path.expanduser("~/.pyenv/shims"),
              "/opt/conda/bin", "/usr/local/python3/bin", "/usr/bin", "/bin"):
        for name in CANDIDATES:
            search.append(os.path.join(d, name))
    for name in search:
        path = shutil.which(name) if os.sep not in name else (name if os.path.exists(name) else None)
        if not path:
            continue
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        try:
            out = subprocess.check_output(
                [path, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                stderr=subprocess.STDOUT,
            )
            ver = out.decode().strip()
            major, minor = [int(x) for x in ver.split(".")[:2]]
        except Exception:
            continue
        found.append((path, (major, minor)))
    return found


def check_deps():
    missing = []
    for mod, pipname in [
        ("pydantic", "pydantic>=2.7"),
        ("pymupdf", "pymupdf>=1.24"),
        ("rapidfuzz", "rapidfuzz>=3.9"),
        ("reportlab", "reportlab>=4.1"),
        ("PIL", "pillow>=10.3"),
        ("pytest", "pytest>=8.2"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pipname)
    return missing


def check_pydantic_v2():
    try:
        import pydantic
    except ImportError:
        return None
    return getattr(pydantic, "VERSION", "1.x")


def check_cjk_font():
    from pathlib import Path

    dirs = [
        str(Path.home() / ".fonts"),
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/local/share/fonts",
        "/Library/Fonts",
        "C:/Windows/Fonts",
    ]
    names = ["NotoSansCJKsc-Regular.otf", "NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.otf",
             "SourceHanSansSC-Regular.otf", "msyh.ttc", "simhei.ttf", "PingFang.ttc"]
    for d in dirs:
        for n in names:
            if os.path.exists(os.path.join(d, n)):
                return os.path.join(d, n)
    return None


def main():
    v = sys.version_info
    here = (v[0], v[1])
    print("Chronik demo — preflight / 环境自检")
    print("=" * 62)
    line(OK, "platform  : %s %s" % (platform.system(), platform.release()))
    line(OK, "python    : %d.%d.%d  (%s)" % (v[0], v[1], v[2], sys.executable))
    line(OK if here >= MIN else FAIL,
         "version   : need >= %d.%d, have %d.%d" % (MIN[0], MIN[1], here[0], here[1]))

    others = [(p, ver) for p, ver in find_interpreters() if ver >= MIN]
    if here >= MIN:
        print()
        line(OK, "interpreter is fine — continue with:")
        print("        python -m venv .venv && . .venv/bin/activate")
        print("        pip install -r requirements.txt")
        print("        python -m chronik.cli")
    else:
        print()
        line(FAIL, "this interpreter is too old — pip will report 'no matching distribution'")
        print("       为什么：pydantic 2.x 需要 Python >= 3.7（实际要 3.8+），PyMuPDF 新版要 3.9+。")
        print("       pip 在旧解释器上只会列出 pydantic 1.9.x，于是报 'Could not find a version'。")
        print()
        if others:
            line(OK, "already installed newer interpreters / 已装好的新版解释器：")
            for p, ver in others:
                print("        %-32s %d.%d" % (p, ver[0], ver[1]))
            p, ver = others[0]
            print()
            print("        use it / 用它：")
            print("        %s -m venv .venv && . .venv/bin/activate" % p)
            print("        pip install -r requirements.txt")
        else:
            line(WARN, "no newer Python found on PATH / PATH 里没有新版 Python")
            print()
            print("        Option A — 装一个 3.11（RedHat/CentOS 系）：")
            print("          dnf install -y python3.11 python3.11-pip    # 或 yum install python3.11")
            print("          python3.11 -m venv .venv && . .venv/bin/activate")
            print()
            print("        Option B — pyenv（不需要 root）：")
            print("          curl -fsSL https://pyenv.run | bash")
            print("          pyenv install 3.11.9 && pyenv local 3.11.9")
            print()
            print("        Option C — Docker（完全不碰系统 Python，最稳）：")
            print("          cd ..  &&  docker compose run --rm demo")
            print()
            print("        Option D — conda：")
            print("          conda create -n chronik python=3.11 && conda activate chronik")

    print()
    print("-" * 62)
    print("dependencies / 依赖：")
    if here >= MIN:
        missing = check_deps()
        pv = check_pydantic_v2()
        if pv:
            line(OK, "pydantic  : %s" % pv)
        if missing:
            line(FAIL, "missing   : %s" % ", ".join(missing))
            print("        pip install -r requirements.txt")
        else:
            line(OK, "all runtime + dev dependencies importable")
        font = check_cjk_font()
        if font:
            line(OK, "cjk font  : %s" % font)
        else:
            line(WARN, "cjk font  : none found -> PNG cards fall back to English labels")
            print("        (只在 --lang zh/both 的 PNG 复核卡上影响中文，不影响功能)")
    else:
        line(WARN, "skipped (needs a newer interpreter first)")

    print()
    print("next / 下一步：docs/05_本地运行指南.md   ·   make demo")
    return 0 if here >= MIN else 1


if __name__ == "__main__":
    sys.exit(main())
