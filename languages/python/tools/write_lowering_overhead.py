"""Emit the structural write evidence on every supported CPython minor.

The report owns the runtime-by-case matrix and the Cost Report Envelope. Each
reading is taken by ``write_lowering_reading.py`` in an isolated child process:
the twenty categorical keyed-write cases and the geometry inserts through actual
driver serialization, the predicate-acquisition families to their buffered
group, and the model-preparation checkpoint. Measurements are observations:
only an incomplete matrix changes this command's exit status.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median
from typing import Any, Final, cast

from interpreter_matrix import (
    CURRENT_MINOR,
    HASH_SEED,
    child_command,
    child_environment,
    supported_minors,
)
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
SUBJECT: Final = "write-lowering"
WARMUPS: Final = 3
MEASURED: Final = 9
ENVIRONMENT_NAMESPACE: Final = "write-lowering"
CALL_NAMES: Final = (
    "shapeOfDeclaration",
    "entityShape",
    "occurrenceShape",
    "encodeDocument",
    "encodeMany",
    "applyPatches",
    "detachJsonContainer",
)
METRICS: Final = ("elapsedUs", "transientBytes", "retainedBytes")
KEYED_WINDOW: Final = "keyed-write"
ACQUISITION_WINDOW: Final = "predicate-acquisition"
MODEL_WINDOW: Final = "model-preparation"
MODEL_CASE: Final = "model.prepared"
WINDOW_DESCRIPTIONS: Final[Mapping[str, str]] = {
    KEYED_WINDOW: (
        "Typed or Wire input through preparation, settlement, SQL lowering, production "
        "bind adaptation, and psycopg's document serialization; no database execution"
    ),
    ACQUISITION_WINDOW: (
        "a prepared Bitemporal updateUntil predicate and freshly composed resolving rows "
        "through production acquisition to a buffered Materialized Write Group; no "
        "ingress preparation, JSON parsing, flush, or serialization"
    ),
    MODEL_WINDOW: "one complete model preparation from the declared Entity Classes",
}

sys.path.insert(0, str(WORKSPACE))

from tests.unit import _predicate_acquisition_support as acquisition_support  # noqa: E402
from tests.unit import _write_lowering_support as lowering_support  # noqa: E402

if Path(lowering_support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(
        f"this report measures over {SUPPORT_MODULE}, but "
        f"'_write_lowering_support' resolved to {lowering_support.__file__}"
    )

WINDOWS: Final[Mapping[str, str]] = {
    **{case.name: KEYED_WINDOW for case in lowering_support.CASES},
    **{case.name: ACQUISITION_WINDOW for case in acquisition_support.CASES},
    MODEL_CASE: MODEL_WINDOW,
}
"""Every case the child can be asked for, and the window it reads."""

CASE_NAMES: Final = tuple(WINDOWS)


@dataclass(frozen=True, slots=True)
class ChildReading:
    case: str
    window: str
    units: int
    samples: Mapping[str, tuple[float, ...]]
    calls: Mapping[str, float]
    warmups: int
    measured: int
    retained_warmups: int


type Cell = ChildReading | str
type Matrix = dict[str, dict[str, Cell]]


def unit_of(window: str, metric: str) -> str:
    """The unit one metric is reported in over one window."""
    scale = "" if window == MODEL_WINDOW else "/row"
    return f"{'us' if metric == 'elapsedUs' else 'B'}{scale}"


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


def _samples(value: object, name: str, *, positive: bool) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list of samples")
    samples = tuple(_number(sample) for sample in cast("list[object]", value))
    if any(sample < 0 or (positive and sample == 0) for sample in samples):
        raise ValueError(f"{name} samples must be {'positive' if positive else 'non-negative'}")
    return samples


def _decoded(output: str, case: str) -> Cell:
    lines = output.strip().splitlines()
    if not lines:
        return "the child printed nothing"
    try:
        document = cast("Mapping[str, Any]", json.loads(lines[-1]))
        expected_fields = {
            "case",
            "window",
            "units",
            "samples",
            "calls",
            "warmups",
            "measured",
            "retainedWarmups",
        }
        if set(document) != expected_fields:
            raise ValueError(
                f"reading fields were {sorted(document)}, expected {sorted(expected_fields)}"
            )
        if document["case"] != case:
            raise ValueError(f"the child answered for {document['case']!r}, expected {case!r}")
        window = WINDOWS[case]
        if document["window"] != window:
            raise ValueError(f"the child read window {document['window']!r}, expected {window!r}")
        samples = cast("Mapping[str, object]", document["samples"])
        if set(samples) != set(METRICS):
            raise ValueError(f"sampled metrics were {sorted(samples)}, expected {list(METRICS)}")
        calls = cast("Mapping[str, object]", document["calls"])
        expected_calls = set(CALL_NAMES) if window == KEYED_WINDOW else set[str]()
        if set(calls) != expected_calls:
            raise ValueError(
                f"observed calls were {sorted(calls)}, expected {sorted(expected_calls)}"
            )
        reading = ChildReading(
            case=case,
            window=window,
            units=_positive_integer(document["units"], "units"),
            samples={
                metric: _samples(
                    samples[metric], f"samples.{metric}", positive=metric == "elapsedUs"
                )
                for metric in METRICS
            },
            calls={name: _number(calls[name]) for name in expected_calls},
            warmups=_positive_integer(document["warmups"], "warmups"),
            measured=_positive_integer(document["measured"], "measured"),
            retained_warmups=_positive_integer(document["retainedWarmups"], "retainedWarmups"),
        )
        if any(count < 0 for count in reading.calls.values()):
            raise ValueError("call counts must be non-negative")
        if reading.warmups != WARMUPS or reading.measured != MEASURED:
            raise ValueError(
                f"sampling was {reading.warmups}/{reading.measured}, expected {WARMUPS}/{MEASURED}"
            )
        return reading
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return f"the child's reading did not decode: {error}"


def in_a_child(runtime: str, case: str) -> Cell:
    """Take one case reading on one runtime, or return why it is unavailable."""
    arguments = [case, "--warmups", str(WARMUPS), "--measured", str(MEASURED)]
    try:
        completed = subprocess.run(
            child_command(runtime, READING_SCRIPT, arguments),
            cwd=WORKSPACE,
            env=child_environment(runtime, ENVIRONMENT_NAMESPACE),
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


def retained_warmups(matrix: Matrix) -> int:
    """The one retained-checkpoint warm-up count every child in ``matrix`` ran."""
    counts = {
        cell.retained_warmups
        for cells in matrix.values()
        for cell in cells.values()
        if isinstance(cell, ChildReading)
    }
    if len(counts) != 1:
        raise ValueError(f"children disagree on the retained warm-up count: {sorted(counts)}")
    return counts.pop()


def case_readings(runtime: str, reading: ChildReading) -> tuple[Reading, ...]:
    """Every envelope reading one child answer contributes."""
    return (
        *(
            Reading(
                reading.case,
                metric,
                float(median(reading.samples[metric])),
                unit_of(reading.window, metric),
                reading.samples[metric],
                window=reading.window,
                runtime=runtime,
            )
            for metric in METRICS
        ),
        *(
            Reading(
                reading.case,
                f"calls.{name}",
                reading.calls[name],
                "calls/row",
                (reading.calls[name],),
                window=reading.window,
                runtime=runtime,
            )
            for name in CALL_NAMES
            if name in reading.calls
        ),
    )


def expected_addresses(runtimes: Sequence[str]) -> frozenset[tuple[str, str, str]]:
    """Every (runtime, case, cell) address a complete envelope carries."""
    addresses: set[tuple[str, str, str]] = set()
    for runtime in runtimes:
        for case, window in WINDOWS.items():
            addresses.update((runtime, case, metric) for metric in METRICS)
            if window == KEYED_WINDOW:
                addresses.update((runtime, case, f"calls.{name}") for name in CALL_NAMES)
    return frozenset(addresses)


def build_envelope(
    contract: BudgetContract,
    provenance: Provenance,
    matrix: Matrix,
) -> CostReportEnvelope:
    """Build and validate the complete runtime-by-case evidence envelope."""
    readings: list[Reading] = []
    for runtime, cells in matrix.items():
        for reading in _complete(cells):
            readings.extend(case_readings(runtime, reading))
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


def sampling(retained_warmups: int) -> dict[str, object]:
    """The protocol every reading in this envelope was taken under."""
    return {
        "warmups": WARMUPS,
        "measured": MEASURED,
        "retainedWarmups": retained_warmups,
        "hashSeed": HASH_SEED,
        "windows": dict(WINDOW_DESCRIPTIONS),
    }


def _provenance(contract: BudgetContract, matrix: Matrix) -> Provenance:
    return Provenance.capture(
        contract,
        workload_digest=lowering_support.write_lowering_digest(),
        postgres=_VersionSource(),
        sampling=sampling(retained_warmups(matrix)),
    )


def _canary_reading(case: str) -> ChildReading:
    window = WINDOWS[case]
    return ChildReading(
        case,
        window,
        1,
        {metric: (10.0,) for metric in METRICS},
        dict.fromkeys(CALL_NAMES, 1.0) if window == KEYED_WINDOW else {},
        WARMUPS,
        MEASURED,
        1,
    )


def canary(contract: BudgetContract) -> CostReportEnvelope:
    """Build one schema-valid complete envelope without running a child."""
    matrix: Matrix = {CURRENT_MINOR: {case: _canary_reading(case) for case in CASE_NAMES}}
    provenance = replace(_provenance(contract, matrix), dirty=True)
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
    envelope = build_envelope(contract, _provenance(contract, matrix), matrix)
    print(json.dumps(envelope.document(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
