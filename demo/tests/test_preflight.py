"""The interpreter guard should explain the problem, not raise a stack trace.

This matters because the failure it catches (pip resolving pydantic to 1.9.x on
Python 3.6) looks like a package problem, not a Python problem.
"""

import importlib.util
from pathlib import Path
import pytest

from chronik import MIN_PYTHON, check_python

DOCTOR = Path(__file__).resolve().parent.parent / "scripts" / "doctor.py"


def load_doctor():
    spec = importlib.util.spec_from_file_location("doctor_under_test", DOCTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# sys.version_info is a structseq: indexable, which is all check_python needs
OK = (3, 9, 0, "final", 0)
OLD = (3, 6, 8, "final", 0)
NEW = (3, 11, 2, "final", 0)
ANCIENT = (2, 7, 18, "final", 0)


def test_minimum_is_documented_and_consistent():
    assert MIN_PYTHON == (3, 9)


@pytest.mark.parametrize("v", [OK, NEW])
def test_supported_interpreters_pass(v):
    check_python(v)  # must not raise


@pytest.mark.parametrize("v", [OLD, ANCIENT])
def test_old_interpreters_get_an_actionable_message(v):
    with pytest.raises(RuntimeError) as exc:
        check_python(v)
    msg = str(exc.value)
    assert "3.9" in msg
    assert "doctor.py" in msg            # points at the diagnostic script
    assert "docker" in msg               # and at the escape hatch
    assert "python3.11 -m venv" in msg    # and at the direct fix
    assert "当前是" in msg                # bilingual, like the rest of the repo


def test_doctor_offers_docker_when_no_newer_python_exists(monkeypatch, capsys):
    doc = load_doctor()
    monkeypatch.setattr(doc.sys, "version_info", (3, 6, 8, "final", 0))
    monkeypatch.setattr(doc, "find_interpreters", lambda: [("/usr/bin/python3", (3, 6, 8))])
    rc = doc.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "too old" in out
    assert "docker compose run --rm demo" in out
    assert "dnf install -y python3.11" in out


def test_doctor_points_at_an_existing_newer_interpreter(monkeypatch, capsys):
    doc = load_doctor()
    monkeypatch.setattr(doc.sys, "version_info", (3, 6, 8, "final", 0))
    monkeypatch.setattr(doc, "find_interpreters", lambda: [("/usr/bin/python3.11", (3, 11))])
    rc = doc.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "/usr/bin/python3.11" in out
    assert "use it" in out


def test_doctor_passes_on_a_good_interpreter(capsys):
    doc = load_doctor()
    rc = doc.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "dependencies" in out
    assert "[FAIL]" not in out
