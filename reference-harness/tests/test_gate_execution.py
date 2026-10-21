from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

_PROBE = """from pathlib import Path
import sys
import time

root = Path(__file__).parent
lane = sys.argv[1]
if lane == "summary":
    assert all((root / f"{name}.done").exists() for name in ("dbfree", "db"))
    (root / "summary").touch()
else:
    (root / f"{lane}.started").touch()
    other = "db" if lane == "dbfree" else "dbfree"
    deadline = time.monotonic() + 10
    while not (root / f"{other}.started").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("verification lanes did not overlap")
        time.sleep(0.01)
    (root / f"{lane}.done").touch()
    if len(sys.argv) > 2 and sys.argv[2] == "fail":
        sys.exit("injected database failure")
"""


def _run_gate(repo_root: Path, tmp_path: Path, *, fail: bool) -> subprocess.CompletedProcess[str]:
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE)
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(probe))}"
    replacement = f"""
set allow-duplicate-recipes

check-gates:
    @true

check-dbfree:
    @{command} dbfree

check-db:
    @{command} db {"fail" if fail else ""}

report-check-summary:
    @{command} summary
"""
    (tmp_path / "justfile").write_text((repo_root / "justfile").read_text() + replacement)
    return subprocess.run(
        ["just", "check"], cwd=tmp_path, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("fail", [False, True], ids=["complete", "database-failure"])
def test_parallel_verification_lanes_report_success_only_after_both_finish(
    repo_root: Path, tmp_path: Path, fail: bool
) -> None:
    result = _run_gate(repo_root, tmp_path, fail=fail)
    assert all((tmp_path / f"{lane}.done").exists() for lane in ("dbfree", "db")), result.stderr
    assert (tmp_path / "summary").exists() is not fail
    if fail:
        assert result.returncode != 0
        assert "injected database failure" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
