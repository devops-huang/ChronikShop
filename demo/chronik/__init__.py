"""Chronik PO agent prototype.

Importing the package fails fast and loudly on an unsupported interpreter.

Why bother: the most common install failure is a bare CentOS/RHEL box whose
``python3`` is 3.6. pip then resolves pydantic to 1.9.x and reports a confusing
"Could not find a version that satisfies the requirement pydantic>=2.7" instead
of "your Python is too old". A four-line guard turns that into an actionable
message.
"""

from __future__ import annotations

import sys

MIN_PYTHON = (3, 9)


def check_python(version_info=None) -> None:
    """Raise a readable error if the interpreter is too old."""
    v = version_info or sys.version_info
    major, minor = v[0], v[1]  # works for both sys.version_info and a plain tuple
    if (major, minor) < MIN_PYTHON:
        raise RuntimeError(
            f"\n"
            f"  Chronik demo needs Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}, "
            f"but this interpreter is {major}.{minor}.{v[2]} ({sys.executable}).\n"
            f"  这个 demo 需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 或更高，"
            f"当前是 {major}.{minor}.{v[2]}。\n"
            f"\n"
            f"  Fix it with any of these / 任选一种修法：\n"
            f"    python3.11 -m venv .venv && . .venv/bin/activate   # 有 3.11 就直接用\n"
            f"    docker compose run --rm demo                         # 完全不碰系统 Python\n"
            f"    python demo/scripts/doctor.py                        # 先诊断，会给具体命令\n"
            f"\n"
            f"  Details / 详细步骤: docs/05_本地运行指南.md\n"
        )


check_python()

__version__ = "0.1.0"
