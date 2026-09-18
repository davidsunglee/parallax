from __future__ import annotations

import json
import os
import platform
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import interpreter_matrix as matrix


def test_supported_minors_close_the_declared_floor_from_below() -> None:
    minors = matrix.supported_minors()
    assert len(minors) == matrix.SUPPORTED_MINORS
    major, floor = (int(part) for part in minors[0].split("."))
    assert minors == tuple(f"{major}.{floor + above}" for above in range(len(minors)))
    assert matrix.CURRENT_MINOR in minors


def test_authority_minor_reads_the_contract_fingerprint() -> None:
    assert matrix.authority_minor({"cpython": "3.14.7"}) == "3.14"
    with pytest.raises(ValueError, match="does not name"):
        matrix.authority_minor({"cpython": "latest"})


def test_child_command_uses_the_current_interpreter_or_uv() -> None:
    script = Path("/tmp/reading.py")
    current = matrix.child_command(matrix.CURRENT_MINOR, script, ["case", "--flag"])
    other = matrix.child_command("9.99", script, ["case"])
    assert current == [sys.executable, str(script), "case", "--flag"]
    assert other == ["uv", "run", "--frozen", "--python", "9.99", "python", str(script), "case"]


def test_child_environment_isolates_another_minor_and_pins_hashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONHOME", "wrong-runtime")
    monkeypatch.setenv("VIRTUAL_ENV", "wrong-environment")
    monkeypatch.setenv("COVERAGE_PROCESS_START", "coverage")
    current = matrix.child_environment(matrix.CURRENT_MINOR, "probe")
    other = matrix.child_environment("9.99", "probe")
    assert current["PYTHONHASHSEED"] == matrix.HASH_SEED
    assert current["PYTHONPATH"] == os.pathsep.join(entry for entry in sys.path if entry)
    assert "COVERAGE_PROCESS_START" not in current
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & other.keys()
    assert other["PYTHONHASHSEED"] == matrix.HASH_SEED
    assert other["UV_PROJECT_ENVIRONMENT"].endswith("parallax-probe-9.99")


def _probe(
    answer: tuple[int, str, str],
) -> tuple[matrix.ProbeRunner, list[tuple[list[str], dict[str, str]]]]:
    asked: list[tuple[list[str], dict[str, str]]] = []

    def run(command: Sequence[str], environment: Mapping[str, str]) -> tuple[int, str, str]:
        asked.append((list(command), dict(environment)))
        return answer

    return run, asked


def test_the_identity_probe_is_routed_through_the_reading_childs_own_resolution() -> None:
    identity = json.dumps({"implementation": "CPython", "version": "9.99.1", "executable": "/p"})
    run, asked = _probe((0, f"noise\n{identity}\n", ""))
    assert matrix.probe_runtime("9.99", "probe", run) == matrix.RuntimeIdentity(
        "CPython", "9.99.1", "/p"
    )
    (command, environment) = asked[0]
    assert command == matrix.child_command("9.99", matrix.IDENTITY_SCRIPT, ())
    assert environment == matrix.child_environment("9.99", "probe")
    run, asked = _probe((0, identity, ""))
    matrix.probe_runtime(matrix.CURRENT_MINOR, "probe", run)
    assert asked[0][0] == [sys.executable, str(matrix.IDENTITY_SCRIPT)]


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ((3, "", "no such interpreter"), "exited 3: no such interpreter"),
        ((0, "\n", ""), "printed nothing"),
        ((0, "not json", ""), "answered no identity"),
        ((0, "[1]", ""), "answered no identity"),
        ((0, json.dumps({"version": "3.14.7"}), ""), "answered no identity"),
        (
            (0, json.dumps({"implementation": "", "version": "3", "executable": "/p"}), ""),
            "incomplete",
        ),
    ],
)
def test_a_probe_that_answers_no_identity_leaves_the_runtime_unavailable(
    answer: tuple[int, str, str], reason: str
) -> None:
    run, _asked = _probe(answer)
    status = matrix.probe_identity(["python"], {}, run)
    assert isinstance(status, matrix.RuntimeUnavailable)
    assert reason in status.reason


def test_the_script_answers_the_identity_of_the_interpreter_running_it() -> None:
    status = matrix.probe_identity([sys.executable, str(matrix.IDENTITY_SCRIPT)], dict(os.environ))
    assert status == matrix.current_identity()
    assert isinstance(status, matrix.RuntimeIdentity)
    assert status.version == platform.python_version()
    assert status.executable == sys.executable
    unavailable = matrix.probe_identity(["/nonexistent/python"], {})
    assert isinstance(unavailable, matrix.RuntimeUnavailable)
    assert "exited 127" in unavailable.reason


def test_metadata_round_trips_every_runtime_status(tmp_path: Path) -> None:
    runtimes: dict[str, matrix.RuntimeStatus] = {
        "3.14": matrix.RuntimeIdentity("CPython", "3.14.7", "/usr/bin/python3.14"),
        "3.13": matrix.RuntimeUnavailable("the identity probe exited 1: gone"),
    }
    sidecar = tmp_path / "metadata.json"
    matrix.write_metadata(sidecar, "subject", runtimes)
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    assert document == {
        "schemaVersion": matrix.METADATA_VERSION,
        "subject": "subject",
        "runtimes": {
            "3.13": {"status": "unavailable", "reason": "the identity probe exited 1: gone"},
            "3.14": {
                "status": "available",
                "implementation": "CPython",
                "version": "3.14.7",
                "executable": "/usr/bin/python3.14",
            },
        },
    }
    assert matrix.load_metadata(sidecar) == runtimes


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("[]", "does not hold a metadata document"),
        ('{"schemaVersion": 2, "runtimes": {}}', "schemaVersion 2"),
        ('{"schemaVersion": 1, "runtimes": []}', "runtimes is not an object"),
        ('{"schemaVersion": 1, "runtimes": {"3.14": "yes"}}', "is not an object"),
        (
            '{"schemaVersion": 1, "runtimes": {"3.14": {"status": "maybe"}}}',
            "not available|unavailable",
        ),
        ('{"schemaVersion": 1, "runtimes": {"3.14": {"status": "unavailable"}}}', "reason None"),
        (
            '{"schemaVersion": 1, "runtimes": {"3.14": {"status": "available", "version": "3"}}}',
            "is incomplete",
        ),
    ],
)
def test_a_malformed_metadata_sidecar_is_refused_by_name(
    tmp_path: Path, document: str, message: str
) -> None:
    sidecar = tmp_path / "metadata.json"
    sidecar.write_text(document, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        matrix.load_metadata(sidecar)
