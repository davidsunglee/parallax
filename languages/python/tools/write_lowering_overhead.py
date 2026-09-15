"""Emit write-lowering builder cost evidence on every supported CPython minor.

The report owns the runtime-by-case matrix and the Cost Report Envelope. Each
reading is taken by ``write_lowering_reading.py`` in an isolated child process.
Measurements are observations: only an incomplete matrix changes this command's
exit status.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, cast

from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import (
    CostReportEnvelope,
    Provenance,
    Reading,
    classify_authority,
    validate,
)

WORKSPACE: Final = Path(__file__).resolve().parents[1]
READING_SCRIPT: Final = Path(__file__).resolve().parent / "write_lowering_reading.py"
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_write_lowering_support.py"
CURRENT_MINOR: Final = f"{sys.version_info.major}.{sys.version_info.minor}"
SUPPORTED_MINORS: Final = 2
SUBJECT: Final = "write-lowering"
WARMUPS: Final = 3
MEASURED: Final = 9
HASH_SEED: Final = "0"
CALL_NAMES: Final = (
    "shapeOfDeclaration",
    "entityShape",
    "occurrenceShape",
    "encodeDocument",
    "encodeMany",
)

sys.path.insert(0, str(WORKSPACE))

from tests.unit import _write_lowering_support as lowering_support  # noqa: E402

if Path(lowering_support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(
        f"this report measures over {SUPPORT_MODULE}, but "
        f"'_write_lowering_support' resolved to {lowering_support.__file__}"
    )

CASE_NAMES: Final = tuple(case.name for case in lowering_support.CASES)


@dataclass(frozen=True, slots=True)
class ChildReading:
    case: str
    rows: int
    elapsed_us: float
    transient_bytes: float
    calls: Mapping[str, float]
    warmups: int
    measured: int


type Cell = ChildReading | str
type Matrix = dict[str, dict[str, Cell]]


def supported_minors() -> tuple[str, ...]:
    """Every CPython minor declared by the workspace, oldest first."""
    declared = cast(
        "str",
        tomllib.loads((WORKSPACE / "pyproject.toml").read_text())["project"]["requires-python"],
    )
    floor = declared.removeprefix(">=").strip()
    parts = floor.split(".")
    if not (
        declared.startswith(">=") and len(parts) == 2 and all(part.isdigit() for part in parts)
    ):
        raise SystemExit(
            f"requires-python {declared!r} is not the bare '>=<major>.<minor>' "
            "floor this report requires"
        )
    major, minor = (int(part) for part in parts)
    return tuple(f"{major}.{minor + above}" for above in range(SUPPORTED_MINORS))


def _child_environment(runtime: str) -> dict[str, str]:
    excluded = {
        "COV_CORE_SOURCE",
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COVERAGE_PROCESS_START",
    }
    environment = {name: value for name, value in os.environ.items() if name not in excluded}
    environment["PYTHONHASHSEED"] = HASH_SEED
    if runtime == CURRENT_MINOR:
        environment["PYTHONPATH"] = os.pathsep.join(entry for entry in sys.path if entry)
        return environment
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["UV_PROJECT_ENVIRONMENT"] = str(
        Path(tempfile.gettempdir()) / f"parallax-write-lowering-{runtime}"
    )
    return environment


def _child_command(runtime: str, case: str) -> list[str]:
    arguments = [case, "--warmups", str(WARMUPS), "--measured", str(MEASURED)]
    if runtime == CURRENT_MINOR:
        return [sys.executable, str(READING_SCRIPT), *arguments]
    return [
        "uv",
        "run",
        "--frozen",
        "--python",
        runtime,
        "python",
        str(READING_SCRIPT),
        *arguments,
    ]


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, received {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"expected a finite number, received {value!r}")
    return number


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer, received {value!r}")
    return value


def _nonnegative_number(value: object, name: str) -> float:
    number = _number(value)
    if number < 0:
        raise ValueError(f"{name} must be non-negative, received {value!r}")
    return number


def _positive_number(value: object, name: str) -> float:
    number = _number(value)
    if number <= 0:
        raise ValueError(f"{name} must be positive, received {value!r}")
    return number


def _decoded(output: str, case: str) -> Cell:
    lines = output.strip().splitlines()
    if not lines:
        return "the child printed nothing"
    try:
        document = cast("Mapping[str, Any]", json.loads(lines[-1]))
        calls = cast("Mapping[str, object]", document["calls"])
        if set(calls) != set(CALL_NAMES):
            raise ValueError(f"builder calls were {sorted(calls)}, expected {list(CALL_NAMES)}")
        expected_fields = {"rows", "perRow", "calls", "warmups", "measured"}
        if set(document) != expected_fields:
            raise ValueError(
                f"reading fields were {sorted(document)}, expected {sorted(expected_fields)}"
            )
        per_row = cast("Mapping[str, object]", document["perRow"])
        if set(per_row) != {"elapsedUs", "transientBytes"}:
            raise ValueError("perRow must contain elapsedUs and transientBytes")
        reading = ChildReading(
            case=case,
            rows=_positive_integer(document["rows"], "rows"),
            elapsed_us=_positive_number(per_row["elapsedUs"], "perRow.elapsedUs"),
            transient_bytes=_positive_number(per_row["transientBytes"], "perRow.transientBytes"),
            calls={name: _nonnegative_number(calls[name], f"calls.{name}") for name in CALL_NAMES},
            warmups=_positive_integer(document["warmups"], "warmups"),
            measured=_positive_integer(document["measured"], "measured"),
        )
        if reading.warmups != WARMUPS or reading.measured != MEASURED:
            raise ValueError(
                f"sampling was {reading.warmups}/{reading.measured}, expected {WARMUPS}/{MEASURED}"
            )
        return reading
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return f"the child's reading did not decode: {error}"


def in_a_child(runtime: str, case: str) -> Cell:
    """Take one case reading on one runtime, or return why it is unavailable."""
    try:
        completed = subprocess.run(
            _child_command(runtime, case),
            cwd=WORKSPACE,
            env=_child_environment(runtime),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return f"the child could not be started: {error}"
    if completed.returncode != 0:
        return f"the child exited {completed.returncode}\n{completed.stdout}{completed.stderr}"
    return _decoded(completed.stdout, case)


def missing_cells(matrix: Matrix, runtimes: Sequence[str], cases: Sequence[str]) -> list[str]:
    absent: list[str] = []
    for runtime in runtimes:
        cells = matrix.get(runtime, {})
        for case in cases:
            cell = cells.get(case, "no child was run")
            if isinstance(cell, str):
                absent.append(f"CPython {runtime}, {case}: {cell}")
    return absent


def _complete(cells: Mapping[str, Cell]) -> tuple[ChildReading, ...]:
    readings = tuple(cells.get(case) for case in CASE_NAMES)
    if not all(isinstance(reading, ChildReading) for reading in readings):
        raise ValueError("the write-lowering matrix is incomplete")
    return cast("tuple[ChildReading, ...]", readings)


def _case_readings(workload: str, reading: ChildReading) -> tuple[Reading, ...]:
    prefix = reading.case
    return (
        Reading(workload, f"{prefix}.perRow.elapsedUs", reading.elapsed_us, "us/row"),
        Reading(
            workload,
            f"{prefix}.perRow.transientBytes",
            reading.transient_bytes,
            "B/row",
        ),
        *(
            Reading(workload, f"{prefix}.calls.{name}", reading.calls[name], "calls/row")
            for name in CALL_NAMES
        ),
    )


def build_envelope(
    contract: BudgetContract,
    provenance: Provenance,
    matrix: Matrix,
) -> CostReportEnvelope:
    """Build and validate the complete runtime-by-case evidence envelope."""
    readings: list[Reading] = []
    for runtime, cells in matrix.items():
        workload = f"cpython-{runtime}"
        complete = _complete(cells)
        for reading in complete:
            readings.extend(_case_readings(workload, reading))
    envelope = CostReportEnvelope(
        SUBJECT,
        provenance,
        classify_authority(provenance, contract),
        tuple(readings),
    )
    validate(envelope)
    return envelope


class _VersionSource:
    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[object] = (),
    ) -> list[Mapping[str, object]]:
        del binds, document_reads
        if sql != "show server_version":
            raise ValueError(sql)
        return [{"server_version": "not-used"}]


def _provenance(contract: BudgetContract) -> Provenance:
    return Provenance.capture(
        contract,
        workload_digest=lowering_support.write_lowering_digest(),
        postgres=_VersionSource(),
        sampling={"warmups": WARMUPS, "measured": MEASURED},
    )


def _canary_reading(case: str) -> ChildReading:
    return ChildReading(
        case,
        1,
        10.0,
        100.0,
        dict.fromkeys(CALL_NAMES, 1.0),
        WARMUPS,
        MEASURED,
    )


def canary(contract: BudgetContract) -> CostReportEnvelope:
    """Build one schema-valid complete envelope without running a child."""
    matrix: Matrix = {CURRENT_MINOR: {case: _canary_reading(case) for case in CASE_NAMES}}
    provenance = replace(_provenance(contract), dirty=True)
    return build_envelope(contract, provenance, matrix)


def main(argv: list[str]) -> int:
    """Spawn all children and emit one envelope; judge only completeness."""
    if argv:
        print("usage: python tools/write_lowering_overhead.py", file=sys.stderr)
        return 2
    runtimes = supported_minors()
    matrix: Matrix = {
        runtime: {case: in_a_child(runtime, case) for case in CASE_NAMES} for runtime in runtimes
    }
    absent = missing_cells(matrix, runtimes, CASE_NAMES)
    if absent:
        print(
            "\n".join(["the matrix is incomplete, so no envelope is reported:", *absent]),
            file=sys.stderr,
        )
        return 3
    contract = BudgetContract.load()
    envelope = build_envelope(contract, _provenance(contract), matrix)
    print(json.dumps(envelope.document(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
