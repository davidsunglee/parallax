"""Emit the structural write evidence on every supported CPython minor.

The report owns the runtime-by-case matrix and the Cost Report Envelope. Each
reading is taken by ``write_lowering_reading.py`` in an isolated child process:
the twenty categorical keyed-write cases, the target writes
beside them, the geometry inserts, the changed-ancestor successors, and the
leaf-type inserts through their public verbs and the flush's actual driver
serialization, the public Wire insert to the node it answers, and the two
model-preparation checkpoints. The leaf-type cases are read only on the
supported minors the leaf-type manifest scopes them to. The cross-object
flushes are read on every supported minor: each one flush of keyed amendments
over many distinct objects, read as its planning and Write Group execution
regions. Measurements are observations: only an incomplete matrix changes this
command's exit status.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path
from statistics import median
from typing import Any, Final, cast

from durations import Spans, write_sidecar
from interpreter_matrix import (
    CURRENT_MINOR,
    HASH_SEED,
    ProbeRunner,
    RuntimeStatus,
    child_command,
    child_environment,
    probe_runtime,
    run_probe,
    supported_minors,
    write_metadata,
)
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import (
    CostReportEnvelope,
    Provenance,
    Reading,
    classify_authority,
    validate,
)
from parallax.conformance.workloads import leaf_type_runtimes

WORKSPACE: Final = Path(__file__).resolve().parents[1]
READING_SCRIPT: Final = Path(__file__).resolve().parent / "write_lowering_reading.py"
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_write_lowering_support.py"
SUBJECT: Final = "write-lowering"
WARMUPS: Final = 3
MEASURED: Final = 9
ENVIRONMENT_NAMESPACE: Final = "write-lowering"
CALL_NAMES: Final = (
    "occurrenceShape",
    "encodeManagedDocument",
    "encodeManagedMany",
    "applyPatches",
    "detachJsonContainer",
)
"""The pass observations a keyed-write child answers, exactly and only."""
MANAGED_CALL_NAMES: Final = (
    "shapeOfDeclaration",
    "entityShape",
    "occurrenceShape",
    "encodeManagedDocument",
    "encodeManagedMany",
    "applyPatches",
    "detachJsonContainer",
)
"""The vocabulary captures were taken under while the document codec still
exported ``shape_of_declaration`` and ``entity_shape``; the unified write path
reached neither, so both counters read zero there and the current vocabulary
drops them. A historical envelope verifies against this vocabulary whole, and a
child answering it is refused."""
LEGACY_CALL_NAMES: Final = (
    "shapeOfDeclaration",
    "entityShape",
    "occurrenceShape",
    "encodeDocument",
    "encodeMany",
    "applyPatches",
    "detachJsonContainer",
)
"""The vocabulary the retained captures were taken under. ``encodeDocument`` and
``encodeMany`` counted a second, presence-driven document encoder the unified
write path does not run; the managed names count the managed encoders it does.
A historical envelope verifies against this vocabulary whole, and a child
answering it is refused."""
CALL_VOCABULARIES: Final[Mapping[str, tuple[str, ...]]] = {
    "current": CALL_NAMES,
    "managed": MANAGED_CALL_NAMES,
    "legacy": LEGACY_CALL_NAMES,
}
"""Every complete counter vocabulary a write-lowering envelope may carry, by
the name a validation failure reports it under."""
METRICS: Final = ("elapsedUs", "transientBytes", "retainedBytes")
FLUSH_UNITS: Final[Mapping[str, str]] = {
    "plan.elapsedUs": "us",
    "plan.retainedBytes": "B",
    "plan.retainedBytesPerObject": "B/row",
    "execution.elapsedUs": "us",
    "execution.transientBytes": "B",
    "execution.transientBytesPerObject": "B/row",
    "work.statements": "statements",
    "work.invocations": "invocations",
    "work.largestOrderedInvocation": "statements",
    "work.largestGroupedInsert": "rows",
}
"""Every cell a cross-object flush answers, exactly and only, with its unit. A
``B`` reading is per flush and its ``B/row`` peer the same reading divided by
the flush's objects, so the two are distinct addresses of one quantity."""
FLUSH_METRICS: Final = tuple(FLUSH_UNITS)
REPEATED_METRICS: Final = (
    "elapsedUs",
    "transientBytes",
    "plan.elapsedUs",
    "execution.elapsedUs",
    "execution.transientBytes",
    "execution.transientBytesPerObject",
)
"""The metrics sampled once per measured run. A retained reading is one
checkpoint, a work count is exact, and every ``calls.*`` observation is one
median, so each carries a single sample."""
POSITIVE_METRICS: Final = frozenset(
    {
        "elapsedUs",
        "plan.elapsedUs",
        "execution.elapsedUs",
        *(m for m in FLUSH_UNITS if m.startswith("work.")),
    }
)

KEYED_WINDOW: Final = "keyed-write"
RESPONSE_WINDOW: Final = "wire-insert-response"
MODEL_WINDOW: Final = "model-preparation"
FLUSH_WINDOW: Final = "cross-object-flush"
MODEL_CASE: Final = "model.prepared"
MODEL_FAMILY_CASE: Final = "model.prepared.family"
WINDOW_DESCRIPTIONS: Final[Mapping[str, str]] = {
    KEYED_WINDOW: (
        "one public Typed or Wire keyed verb over a row its transaction already read, "
        "or one target write over a row its transaction never read, "
        "until transact returns: preparation, buffering, the pre-commit flush's "
        "settlement and SQL lowering, production bind adaptation, psycopg's document "
        "serialization, and the commit; a target's own coverage read at flush over "
        "provider-free rows, but no earlier read and no database execution"
    ),
    RESPONSE_WINDOW: (
        "one public tx.wire.insert of a nested, polymorphic Create Payload inside an open "
        "transaction, from the payload arriving to the frozen node it answers; no flush, "
        "lowering, or serialization"
    ),
    MODEL_WINDOW: "one complete model preparation from the declared Entity Classes",
    FLUSH_WINDOW: (
        "one pre-commit flush of a keyed amendment of each of many distinct objects its "
        "transaction already read and buffered, over a provider-free port offering ordered "
        "transport, read as two regions: planning, from finalization's start to the "
        "finalized plan, whose retained bytes are a separate checkpoint before any Write "
        "Group executes; and execution, summed over every Write Group's steps through "
        "lowering, production bind adaptation, psycopg's serialization, and presentation, "
        "with each group's completion between regions and inside neither; the read, the "
        "authored inputs, admission, and the commit precede or follow both; per-object "
        "bytes divide a flush's by its objects"
    ),
}

sys.path.insert(0, str(WORKSPACE))

# `sys.path` gains the workspace above, so this import cannot precede it; that is
# what its E402 suppression records.
from tests.unit import _write_lowering_support as lowering_support  # noqa: E402

if Path(lowering_support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(
        f"this report measures over {SUPPORT_MODULE}, but "
        f"'_write_lowering_support' resolved to {lowering_support.__file__}"
    )

WINDOWS: Final[Mapping[str, str]] = {
    **{case.name: KEYED_WINDOW for case in lowering_support.CASES},
    **{case.name: RESPONSE_WINDOW for case in lowering_support.RESPONSE_CASES},
    MODEL_CASE: MODEL_WINDOW,
    MODEL_FAMILY_CASE: MODEL_WINDOW,
    **{case.name: FLUSH_WINDOW for case in lowering_support.CROSS_OBJECT_CASES},
}
"""Every case the child can be asked for, and the window it reads."""

CASE_NAMES: Final = tuple(WINDOWS)
CONTROL_CASE_NAMES: Final = (
    *(case.name for case in lowering_support.RESPONSE_CASES),
    MODEL_FAMILY_CASE,
)
"""The cases added as before/after controls beside the lowering matrix: the
public insert response and the family-bearing preparation."""
LEAF_TYPE_CASE_NAMES: Final = tuple(
    case.name for case in lowering_support.CASES if case.family == lowering_support.LEAF_FAMILY
)
"""The leaf-type inserts, read only on the supported minors the leaf-type
manifest scopes them to."""
TARGET_CASE_NAMES: Final = tuple(case.name for case in lowering_support.CASES if case.addressed)
"""The target writes."""
CROSS_OBJECT_OBJECTS: Final[Mapping[str, int]] = {
    case.name: case.objects for case in lowering_support.CROSS_OBJECT_CASES
}
"""Each cross-object flush and the objects it amends: the denominator of its
per-object readings."""
CROSS_OBJECT_CASE_NAMES: Final = tuple(CROSS_OBJECT_OBJECTS)
RETIRED_WINDOWS: Final[Mapping[str, str]] = {
    "acquisition.rows-8.columns": "predicate-acquisition",
    "acquisition.rows-32.columns": "predicate-acquisition",
    "acquisition.rows-128.columns": "predicate-acquisition",
    "acquisition.rows-8.document": "predicate-acquisition",
    "acquisition.rows-32.document": "predicate-acquisition",
    "acquisition.rows-128.document": "predicate-acquisition",
}
"""The cases the retained legacy captures read that no child reads any more,
and the window each was read over."""
ENVELOPE_WINDOWS: Final[Mapping[str, str]] = {**WINDOWS, **RETIRED_WINDOWS}
"""Every case a write-lowering envelope may carry, and the window it was read
over."""
LEGACY_CASE_NAMES: Final = (
    *(
        name
        for name in CASE_NAMES
        if WINDOWS[name] == KEYED_WINDOW
        and name not in TARGET_CASE_NAMES
        and name not in LEAF_TYPE_CASE_NAMES
    ),
    *RETIRED_WINDOWS,
    MODEL_CASE,
)
"""The case set the retained captures were taken over."""
CASE_COVERAGES: Final[Mapping[str, tuple[str, ...]]] = {
    "current": CASE_NAMES,
    "legacy": LEGACY_CASE_NAMES,
}
"""Every complete case set a write-lowering envelope may carry, by the name a
validation failure reports it under; a matrix is exact under one whole case
set and one whole counter vocabulary."""


def runtime_cases(runtime: str, case_names: Sequence[str] = CASE_NAMES) -> tuple[str, ...]:
    """The cases among ``case_names`` read on ``runtime``: the leaf-type cases
    only on the supported minors the leaf-type manifest scopes them to."""
    if runtime in leaf_type_runtimes(supported_minors()):
        return tuple(case_names)
    return tuple(case for case in case_names if case not in LEAF_TYPE_CASE_NAMES)


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


def metrics_of(window: str) -> tuple[str, ...]:
    """The cells other than pass observations a reading over ``window`` answers."""
    return FLUSH_METRICS if window == FLUSH_WINDOW else METRICS


def unit_of(window: str, metric: str) -> str:
    """The unit one metric is reported in over one window."""
    if window == FLUSH_WINDOW:
        return FLUSH_UNITS[metric]
    scale = "" if window == MODEL_WINDOW else "/row"
    return f"{'us' if metric == 'elapsedUs' else 'B'}{scale}"


def samples_expected(cell: str) -> int:
    """How many samples one reading cell carries under the frozen protocol.

    A cell whose sample count disagrees was truncated after the child took it,
    so the evidence is incomplete however well its median agrees.
    """
    return MEASURED if cell in REPEATED_METRICS else 1


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


def _samples(value: object, name: str, expected: int, *, positive: bool) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of samples")
    samples = tuple(_number(sample) for sample in cast("list[object]", value))
    if len(samples) != expected:
        raise ValueError(f"{name} carries {len(samples)} samples, expected {expected}")
    if any(sample < 0 or (positive and sample == 0) for sample in samples):
        raise ValueError(f"{name} samples must be {'positive' if positive else 'non-negative'}")
    return samples


def _units(value: object, case: str) -> int:
    units = _positive_integer(value, "units")
    objects = CROSS_OBJECT_OBJECTS.get(case, units)
    if units != objects:
        raise ValueError(f"the child divided by {units} objects, expected {objects}")
    return units


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
        metrics = metrics_of(window)
        if set(samples) != set(metrics):
            raise ValueError(f"sampled metrics were {sorted(samples)}, expected {list(metrics)}")
        calls = cast("Mapping[str, object]", document["calls"])
        expected_calls = set(CALL_NAMES) if window == KEYED_WINDOW else set[str]()
        if set(calls) != expected_calls:
            raise ValueError(
                f"observed calls were {sorted(calls)}, expected {sorted(expected_calls)}"
            )
        units = _units(document["units"], case)
        warmups = _positive_integer(document["warmups"], "warmups")
        measured = _positive_integer(document["measured"], "measured")
        if warmups != WARMUPS or measured != MEASURED:
            raise ValueError(f"sampling was {warmups}/{measured}, expected {WARMUPS}/{MEASURED}")
        reading = ChildReading(
            case=case,
            window=window,
            units=units,
            samples={
                metric: _samples(
                    samples[metric],
                    f"samples.{metric}",
                    samples_expected(metric),
                    positive=metric in POSITIVE_METRICS,
                )
                for metric in metrics
            },
            calls={name: _number(calls[name]) for name in expected_calls},
            warmups=warmups,
            measured=measured,
            retained_warmups=_positive_integer(document["retainedWarmups"], "retainedWarmups"),
        )
        if any(count < 0 for count in reading.calls.values()):
            raise ValueError("call counts must be non-negative")
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
        for case in runtime_cases(runtime, cases):
            cell = cells.get(case, "no child was run")
            if isinstance(cell, str):
                absent.append(f"CPython {runtime}, {case}: {cell}")
    return absent


def _complete(runtime: str, cells: Mapping[str, Cell]) -> tuple[ChildReading, ...]:
    readings = tuple(cells.get(case) for case in runtime_cases(runtime))
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
            for metric in metrics_of(reading.window)
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


def expected_addresses(
    runtimes: Sequence[str],
    call_names: Sequence[str] = CALL_NAMES,
    case_names: Sequence[str] = CASE_NAMES,
) -> frozenset[tuple[str, str, str]]:
    """Every (runtime, case, cell) address a complete envelope over
    ``case_names`` carries whose keyed-write cases count ``call_names``."""
    addresses: set[tuple[str, str, str]] = set()
    for runtime in runtimes:
        for case in runtime_cases(runtime, case_names):
            window = ENVELOPE_WINDOWS[case]
            addresses.update((runtime, case, metric) for metric in metrics_of(window))
            if window == KEYED_WINDOW:
                addresses.update((runtime, case, f"calls.{name}") for name in call_names)
    return frozenset(addresses)


def build_envelope(
    contract: BudgetContract,
    provenance: Provenance,
    matrix: Matrix,
) -> CostReportEnvelope:
    """Build and validate the complete runtime-by-case evidence envelope."""
    readings: list[Reading] = []
    for runtime, cells in matrix.items():
        for reading in _complete(runtime, cells):
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
        {metric: (10.0,) * samples_expected(metric) for metric in metrics_of(window)},
        dict.fromkeys(CALL_NAMES, 1.0) if window == KEYED_WINDOW else {},
        WARMUPS,
        MEASURED,
        1,
    )


def canary(contract: BudgetContract) -> CostReportEnvelope:
    """Build one schema-valid complete envelope without running a child."""
    matrix: Matrix = {
        CURRENT_MINOR: {case: _canary_reading(case) for case in runtime_cases(CURRENT_MINOR)}
    }
    provenance = replace(_provenance(contract, matrix), dirty=True)
    return build_envelope(contract, provenance, matrix)


def diagnostic(
    runtimes: Sequence[str],
    cases: Sequence[str],
    child: Callable[[str, str], Cell] | None = None,
) -> dict[str, object]:
    """Readings for chosen cases on chosen runtimes, as a diagnostic document.

    A diagnostic run answers a question about some cases; it is not evidence. It
    carries no provenance and is not an envelope, so nothing downstream can
    validate, verify, or retain it as a capture.
    """
    take = in_a_child if child is None else child
    matrix: Matrix = {
        runtime: {case: take(runtime, case) for case in runtime_cases(runtime, cases)}
        for runtime in runtimes
    }
    readings = [
        reading.document()
        for runtime, cells in matrix.items()
        for cell in cells.values()
        if isinstance(cell, ChildReading)
        for reading in case_readings(runtime, cell)
    ]
    return {
        "diagnostic": True,
        "subject": SUBJECT,
        "runtimes": list(runtimes),
        "readings": readings,
        "unavailable": missing_cells(matrix, runtimes, cases),
    }


def selected_cases(patterns: Sequence[str]) -> tuple[str, ...]:
    """Every case name matching any of ``patterns`` as a shell-style pattern."""
    return tuple(
        case for case in CASE_NAMES if any(fnmatchcase(case, pattern) for pattern in patterns)
    )


def timed_matrix(
    runtimes: Sequence[str],
    cases: Sequence[str],
    spans: Spans,
    child: Callable[[str, str], Cell] | None = None,
) -> Matrix:
    """Every case :func:`runtime_cases` reads on each runtime, each child inside
    a span of its own."""
    take = in_a_child if child is None else child
    matrix: Matrix = {}
    for runtime in runtimes:
        cells: dict[str, Cell] = {}
        for case in runtime_cases(runtime, cases):
            with spans.span("case", case, member=SUBJECT, runtime=runtime, window=WINDOWS[case]):
                cells[case] = take(runtime, case)
        matrix[runtime] = cells
    return matrix


def main(argv: list[str]) -> int:
    """Spawn all children and emit one envelope; judge only completeness.

    ``--diagnostic`` instead takes readings for the cases and runtimes named,
    and prints them as a diagnostic document that is not an envelope.
    """
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--runtime", action="append", default=[])
    parser.add_argument("--durations", type=Path)
    parser.add_argument("--metadata", type=Path)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        args = None
    if (
        args is None
        or ((args.case or args.runtime) and not args.diagnostic)
        or (args.diagnostic and (args.durations is not None or args.metadata is not None))
    ):
        print(
            "usage: python tools/write_lowering_overhead.py "
            "[--durations PATH] [--metadata PATH] "
            "| --diagnostic [--case PATTERN]... [--runtime MINOR]...",
            file=sys.stderr,
        )
        return 2
    if args.diagnostic:
        cases = selected_cases(args.case) if args.case else CASE_NAMES
        if not cases:
            print(f"no case matches {args.case}", file=sys.stderr)
            return 2
        document = diagnostic(tuple(args.runtime) or supported_minors(), cases)
        print(json.dumps(document, indent=2, sort_keys=True))
        return 0
    spans = Spans()
    try:
        return _measured(spans, args.metadata)
    finally:
        if args.durations is not None:
            write_sidecar(args.durations, spans.write)


def runtime_identities(
    runtimes: Sequence[str], spans: Spans, probe: ProbeRunner = run_probe
) -> dict[str, RuntimeStatus]:
    """Each runtime's interpreter, probed once through the reading child's own
    command and environment resolution, before any case is read."""
    identities: dict[str, RuntimeStatus] = {}
    for runtime in runtimes:
        with spans.span("setup", "identity", member=SUBJECT, runtime=runtime):
            identities[runtime] = probe_runtime(runtime, ENVIRONMENT_NAMESPACE, probe)
    return identities


def _measured(spans: Spans, metadata: Path | None) -> int:
    runtimes = supported_minors()
    if metadata is not None:
        identities = runtime_identities(runtimes, spans, run_probe)
        write_sidecar(metadata, lambda path: write_metadata(path, SUBJECT, identities))
    matrix = timed_matrix(runtimes, CASE_NAMES, spans)
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
