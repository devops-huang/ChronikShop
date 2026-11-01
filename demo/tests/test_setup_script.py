"""Guards for scripts/setup.sh — the first thing anyone runs.

These are cheap static checks, but they protect the two mistakes that would
actually cost the user an hour: a script that is not executable, and a
dependency installer that ignores a broken index instead of falling back.
"""

import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "setup.sh"


def text() -> str:
    return SCRIPT.read_text()


def test_script_exists_and_is_executable():
    assert SCRIPT.exists()
    assert SCRIPT.stat().st_mode & 0o111, "setup.sh must be executable"


def test_shell_syntax_is_valid():
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_python_floor_matches_the_package_guard():
    from chronik import MIN_PYTHON

    m = re.search(r"^MIN_MAJOR=(\d+)$", text(), re.M)
    n = re.search(r"^MIN_MINOR=(\d+)$", text(), re.M)
    assert m and n, "MIN_MAJOR / MIN_MINOR must stay greppable"
    assert (int(m.group(1)), int(n.group(1))) == MIN_PYTHON


def test_every_pip_call_pins_an_index_url():
    """Regression: an exported PIP_INDEX_URL used to shadow the fallback, so the
    'plain PyPI' retry silently repeated the same failing index."""
    for line in text().splitlines():
        stripped = line.strip()
        if "-m pip install" in stripped:
            assert "--index-url" in stripped or "pip install -q --upgrade pip" in stripped, stripped


def test_has_a_mirror_fallback():
    body = text()
    assert "CHRONIK_PIP_MIRROR" in body
    assert "pypi.tuna.tsinghua.edu.cn" in body


def test_recreates_a_too_old_venv():
    assert "recreating it" in text()
    assert "rm -rf \"$DEMO/.venv\"" in text()


def test_help_flag_documents_the_modes():
    proc = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    for flag in ("--lang", "--docker", "--install-py"):
        assert flag in proc.stdout


def test_unknown_option_fails_loudly():
    proc = subprocess.run(["bash", str(SCRIPT), "--nope"], capture_output=True, text=True)
    assert proc.returncode == 2
    assert "unknown option" in proc.stdout
