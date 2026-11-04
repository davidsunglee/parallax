from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests._support.repo import PY_ROOT


@pytest.mark.parametrize("workers", [0, 2])
def test_timing_reports_keep_startup_and_each_test_phase_on_failure(
    tmp_path: Path, workers: int
) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "from tests._support.session_timings import configure\n"
        "def pytest_addoption(parser):\n"
        "    parser.addoption('--timing-report')\n"
        "def pytest_configure(config):\n"
        "    configure(config)\n",
        encoding="utf-8",
    )
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n"
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        "@pytest.fixture\n"
        "def broken_fixture():\n"
        "    pytest.fail('setup failure')\n"
        "@pytest.fixture\n"
        "def broken_teardown():\n"
        "    yield\n"
        "    pytest.fail('teardown failure')\n"
        "def test_pass():\n"
        "    directory = Path(__file__).parent\n"
        "    completed = subprocess.run([sys.executable, '-m', 'pytest', '-c',\n"
        "        str(directory / 'pytest.ini'), '--confcutdir', str(directory),\n"
        "        '--collect-only', '-q', __file__], capture_output=True, text=True, timeout=30)\n"
        "    assert completed.returncode == 0, completed.stdout + completed.stderr\n"
        "def test_call_failure():\n"
        "    pytest.fail('call failure')\n"
        "def test_setup_failure(broken_fixture):\n"
        "    pass\n"
        "def test_teardown_failure(broken_teardown):\n"
        "    pass\n"
        "@pytest.mark.skip(reason='intentional skip')\n"
        "def test_skip():\n"
        "    pass\n",
        encoding="utf-8",
    )
    report_dir = tmp_path / "timings"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(tmp_path / "pytest.ini"),
            "--confcutdir",
            str(tmp_path),
            "-n",
            str(workers),
            "--timing-report",
            str(report_dir),
            str(tmp_path / "test_sample.py"),
        ],
        cwd=PY_ROOT,
        env={**os.environ, "PYTEST_ADDOPTS": f"--timing-report={shlex.quote(str(report_dir))}"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    sessions = [
        {path.stem: _events(path) for path in directory.glob("*.jsonl")}
        for directory in report_dir.iterdir()
    ]
    assert len(sessions) == 2
    files = next(
        session
        for session in sessions
        if any(row["event"] == "test-report" for row in session["controller"])
    )
    (nested,) = [session for session in sessions if session is not files]
    assert set(nested) == {"controller"}
    assert nested["controller"][-1]["event"] == "session-finish"
    assert nested["controller"][-1]["exitstatus"] == 0
    assert all(row["event"] != "test-report" for row in nested["controller"])
    assert set(files) == {"controller", *(f"gw{i}" for i in range(workers))}
    for events in files.values():
        assert [row["event"] for row in events[:2]] == ["configured", "session-start"]
        assert events[-1]["event"] == "session-finish"
        assert events[-1]["exitstatus"] == 1
        assert all(isinstance(row["time"], float) for row in events)

    collectors = [files[f"gw{i}"] for i in range(workers)] if workers else [files["controller"]]
    for events in collectors:
        collection = [row for row in events if row["event"].startswith("collection-")]
        assert [row["event"] for row in collection] == ["collection-start", "collection-finish"]
        assert collection[-1]["selected"] == 5

    phases = [row for row in files["controller"] if row["event"] == "test-report"]
    assert len(phases) == 13
    assert len({(row["nodeid"], row["phase"]) for row in phases}) == len(phases)
    assert {(row["nodeid"].split("::")[-1], row["phase"], row["outcome"]) for row in phases} == {
        ("test_pass", "setup", "passed"),
        ("test_pass", "call", "passed"),
        ("test_pass", "teardown", "passed"),
        ("test_call_failure", "setup", "passed"),
        ("test_call_failure", "call", "failed"),
        ("test_call_failure", "teardown", "passed"),
        ("test_setup_failure", "setup", "failed"),
        ("test_setup_failure", "teardown", "passed"),
        ("test_teardown_failure", "setup", "passed"),
        ("test_teardown_failure", "call", "passed"),
        ("test_teardown_failure", "teardown", "failed"),
        ("test_skip", "setup", "skipped"),
        ("test_skip", "teardown", "passed"),
    }
    for row in phases:
        assert row["duration"] >= 0
        assert row["stop"] >= row["start"] > 0
        assert row["worker"] in ({f"gw{i}" for i in range(workers)} if workers else {"controller"})
    for worker, events in files.items():
        if worker != "controller":
            assert all(row["event"] != "test-report" for row in events)


def _events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
