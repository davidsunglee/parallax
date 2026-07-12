"""``parallax-conformance`` CLI tests: in-process wire surface + subprocess smoke."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

import jsonschema
import pytest

from conftest import adapter_schema, canonical_snapshot_claim
from parallax.conformance import case_format, cli

pytestmark = pytest.mark.unit

_SCHEMA = adapter_schema()
_READ_CASE = str(case_format.default_cases_dir() / "m-op-algebra-002-eq.yaml")


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_describe_in_process(capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = _run(capsys, ["describe"])
    assert code == 0
    jsonschema.validate(envelope, _SCHEMA)
    canonical = canonical_snapshot_claim()
    assert envelope["capabilities"] == canonical["capabilities"]
    assert envelope["adapter"]["language"] == "python"


def test_compile_claimed_case_errors_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = _run(capsys, ["compile", "--case", _READ_CASE, "--dialect", "postgres"])
    assert code == 1
    assert envelope["status"] == "error"


def test_run_claimed_case_errors_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = _run(capsys, ["run", "--case", _READ_CASE, "--dialect", "postgres"])
    assert code == 1
    assert envelope["status"] == "error"


def test_compile_unsupported_dialect_exit_10(capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = _run(capsys, ["compile", "--case", _READ_CASE, "--dialect", "mariadb"])
    assert code == 10
    assert envelope["status"] == "unsupported"


def test_benchmark_unsupported_command_exit_10(capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = _run(capsys, ["benchmark", "--benchmark", "b.yaml", "--dialect", "postgres"])
    assert code == 10
    assert envelope["command"] == "benchmark"
    assert envelope["diagnostics"][0]["code"] == "unsupported-command"


def test_unreadable_case_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = _run(
        capsys, ["run", "--case", "/nonexistent/missing.yaml", "--dialect", "postgres"]
    )
    assert code == 2
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["diagnostics"][0]["code"] == "unreadable-case"


def test_missing_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2


def test_describe_subprocess_smoke() -> None:
    executable = shutil.which("parallax-conformance")
    assert executable is not None, "the parallax-conformance console script must be installed"
    result = subprocess.run([executable, "describe"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    jsonschema.validate(envelope, _SCHEMA)
    canonical = canonical_snapshot_claim()
    canonical["adapter"] = envelope["adapter"]
    assert envelope == canonical
