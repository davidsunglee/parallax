"""Report bounded Typed predicate and scalar-collection costs on every supported minor."""

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
from typing import Final, cast

from durations import Spans, write_sidecar
from interpreter_matrix import (
    HASH_SEED,
    RuntimeStatus,
    child_command,
    child_environment,
    probe_runtime,
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

WORKSPACE: Final = Path(__file__).resolve().parents[1]
READING_SCRIPT: Final = Path(__file__).with_name("feature_boundary_reading.py")
SUBJECT: Final = "feature-boundary"
ENVIRONMENT_NAMESPACE: Final = SUBJECT
WARMUPS: Final = 3
MEASURED: Final = 9
RETAINED_WARMUPS: Final = 200
METRICS: Final = ("elapsedUs", "peakBytes", "retainedBytes")
CELL_UNITS: Final = {"elapsedUs": "us", "peakBytes": "B", "retainedBytes": "B"}
sys.path.insert(0, str(WORKSPACE))

from tests.unit import _feature_boundary_support as support  # noqa: E402

SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_feature_boundary_support.py"
if Path(support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(f"this report requires {SUPPORT_MODULE}, but resolved {support.__file__}")

CASE_NAMES: Final = tuple(case.name for case in support.CASES)
WINDOWS: Final = {case.name: case.window for case in support.CASES}
UNITS: Final = {case.name: case.units for case in support.CASES}
WINDOW_DESCRIPTIONS: Final = support.WINDOW_DESCRIPTIONS


@dataclass(frozen=True, slots=True)
class ChildReading:
    case: str
    window: str
    units: int
    samples: Mapping[str, tuple[float, ...]]


type Cell = ChildReading | str
type Matrix = dict[str, dict[str, Cell]]
type Child = Callable[[str, str], Cell]


def workload_digest() -> str:
    return support.workload_digest()


def samples_expected(metric: str) -> int:
    return 1 if metric == "retainedBytes" else MEASURED


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"expected a finite number, received {value!r}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"expected a finite non-negative number, received {value!r}")
    return number


def _samples(value: object, metric: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{metric} must be a list of samples")
    values = cast("list[object]", value)
    if len(values) != samples_expected(metric):
        raise ValueError(f"{metric} must have {samples_expected(metric)} samples")
    samples = tuple(_number(sample) for sample in values)
    if metric == "elapsedUs" and any(sample == 0 for sample in samples):
        raise ValueError("elapsedUs samples must be positive")
    return samples


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return cast("Mapping[str, object]", value)


def decode_child(output: str, case: str) -> Cell:
    try:
        lines = output.strip().splitlines()
        if not lines:
            raise ValueError("the child printed nothing")
        document = _mapping(json.loads(lines[-1]), "reading")
        expected = {"case", "window", "units", "samples", "warmups", "measured", "retainedWarmups"}
        if set(document) != expected:
            raise ValueError(f"reading fields must be {sorted(expected)}")
        for name, value in (
            ("case", case),
            ("window", WINDOWS[case]),
            ("units", UNITS[case]),
            ("warmups", WARMUPS),
            ("measured", MEASURED),
            ("retainedWarmups", RETAINED_WARMUPS),
        ):
            observed = document[name]
            if observed != value or (
                isinstance(value, int)
                and (isinstance(observed, bool) or not isinstance(observed, int))
            ):
                raise ValueError(f"{name} was {document[name]!r}, expected {value!r}")
        samples = _mapping(document["samples"], "samples")
        if set(samples) != set(METRICS):
            raise ValueError(f"sample metrics must be {list(METRICS)}")
        return ChildReading(
            case,
            WINDOWS[case],
            UNITS[case],
            {metric: _samples(samples[metric], metric) for metric in METRICS},
        )
    except (KeyError, TypeError, ValueError) as error:
        return f"the child's reading did not decode: {error}"


def in_a_child(runtime: str, case: str) -> Cell:
    try:
        completed = subprocess.run(
            child_command(
                runtime,
                READING_SCRIPT,
                (case, "--warmups", str(WARMUPS), "--measured", str(MEASURED)),
            ),
            cwd=WORKSPACE,
            env=child_environment(runtime, ENVIRONMENT_NAMESPACE),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return f"the child could not be started: {error}"
    if completed.returncode:
        return f"the child exited {completed.returncode}\n{completed.stdout}{completed.stderr}"
    return decode_child(completed.stdout, case)


def case_readings(runtime: str, reading: ChildReading) -> tuple[Reading, ...]:
    return tuple(
        Reading(
            reading.case,
            metric,
            float(median(reading.samples[metric])),
            CELL_UNITS[metric],
            reading.samples[metric],
            window=reading.window,
            runtime=runtime,
        )
        for metric in METRICS
    )


def expected_addresses(runtimes: Sequence[str]) -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (runtime, case, metric) for runtime in runtimes for case in CASE_NAMES for metric in METRICS
    )


def sampling() -> dict[str, object]:
    return {
        "warmups": WARMUPS,
        "measured": MEASURED,
        "retainedWarmups": RETAINED_WARMUPS,
        "hashSeed": HASH_SEED,
        "windows": dict(WINDOW_DESCRIPTIONS),
        "cases": {case: {"window": WINDOWS[case], "units": UNITS[case]} for case in CASE_NAMES},
    }


def _validate_sampling(value: object) -> None:
    protocol = _mapping(value, "sampling")
    if protocol != sampling():
        raise ValueError("feature-boundary sampling does not match the frozen protocol")
    for field in ("warmups", "measured", "retainedWarmups"):
        if type(protocol[field]) is not int:
            raise ValueError(f"sampling.{field} must be an integer")
    cases = _mapping(protocol["cases"], "sampling.cases")
    for case in CASE_NAMES:
        declaration = _mapping(cases[case], f"sampling.cases.{case}")
        if type(declaration["units"]) is not int:
            raise ValueError(f"sampling.cases.{case}.units must be an integer")


def validate_matrix(document: Mapping[str, object], runtimes: Sequence[str] | None = None) -> None:
    """Raise ValueError for evidence outside the complete declared sampling matrix."""
    validate(document)
    if document.get("subject") != SUBJECT:
        raise ValueError(f"expected subject {SUBJECT}")
    if document.get("incomplete") or document.get("errors"):
        raise ValueError("feature-boundary evidence has incomplete or error diagnostics")
    provenance = _mapping(document["provenance"], "provenance")
    _validate_sampling(provenance.get("sampling"))
    raw = document["readings"]
    if not isinstance(raw, list):
        raise ValueError("readings must be a list")
    seen: set[tuple[str, str, str]] = set()
    for item in cast("list[object]", raw):
        reading = _mapping(item, "reading")
        runtime, case, metric = (str(reading.get(key)) for key in ("runtime", "workload", "cell"))
        address = (runtime, case, metric)
        if address in seen or case not in WINDOWS or metric not in METRICS:
            raise ValueError(f"unexpected or duplicate feature-boundary address {address}")
        seen.add(address)
        if reading.get("window") != WINDOWS[case] or reading.get("unit") != CELL_UNITS[metric]:
            raise ValueError(f"incorrect window or unit at {address}")
        samples = _samples(reading.get("samples"), metric)
        if _number(reading.get("value")) != median(samples):
            raise ValueError(f"value is not the sample median at {address}")
    expected = expected_addresses(supported_minors() if runtimes is None else runtimes)
    if frozenset(seen) != expected:
        raise ValueError(
            f"feature-boundary matrix differs: missing={sorted(expected - seen)}, "
            f"extra={sorted(seen - expected)}"
        )


class _VersionSource:
    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[object] = ()
    ) -> list[Mapping[str, object]]:
        del binds, document_reads
        if sql != "show server_version":
            raise ValueError(sql)
        return [{"server_version": "not-used"}]


def build_envelope(
    contract: BudgetContract, provenance: Provenance, matrix: Matrix
) -> CostReportEnvelope:
    readings = tuple(
        reading
        for runtime, cells in matrix.items()
        for cell in cells.values()
        if isinstance(cell, ChildReading)
        for reading in case_readings(runtime, cell)
    )
    envelope = CostReportEnvelope(
        SUBJECT, provenance, classify_authority(provenance, contract), readings
    )
    validate_matrix(envelope.document())
    return envelope


def _provenance(contract: BudgetContract) -> Provenance:
    return Provenance.capture(
        contract, workload_digest=workload_digest(), postgres=_VersionSource(), sampling=sampling()
    )


def canary(contract: BudgetContract) -> CostReportEnvelope:
    """Build synthetic, non-authoritative evidence without starting a measurement child."""
    matrix: Matrix = {
        runtime: {
            case: ChildReading(
                case,
                WINDOWS[case],
                UNITS[case],
                {metric: (10.0,) * samples_expected(metric) for metric in METRICS},
            )
            for case in CASE_NAMES
        }
        for runtime in supported_minors()
    }
    return build_envelope(contract, replace(_provenance(contract), dirty=True), matrix)


def timed_matrix(
    runtimes: Sequence[str], cases: Sequence[str], spans: Spans, child: Child | None = None
) -> Matrix:
    take = in_a_child if child is None else child
    matrix: Matrix = {}
    for runtime in runtimes:
        matrix[runtime] = {}
        for case in cases:
            with spans.span("case", case, member=SUBJECT, runtime=runtime, window=WINDOWS[case]):
                matrix[runtime][case] = take(runtime, case)
    return matrix


def missing_cells(matrix: Matrix, runtimes: Sequence[str], cases: Sequence[str]) -> list[str]:
    return [
        f"CPython {runtime}, {case}: {cell}"
        for runtime in runtimes
        for case in cases
        if isinstance(cell := matrix.get(runtime, {}).get(case, "no child was run"), str)
    ]


def selected_cases(patterns: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        case for case in CASE_NAMES if any(fnmatchcase(case, pattern) for pattern in patterns)
    )


def diagnostic(
    runtimes: Sequence[str], cases: Sequence[str], child: Child | None = None
) -> dict[str, object]:
    matrix = timed_matrix(runtimes, cases, Spans(), child)
    return {
        "diagnostic": True,
        "subject": SUBJECT,
        "runtimes": list(runtimes),
        "readings": [
            reading.document()
            for runtime, cells in matrix.items()
            for cell in cells.values()
            if isinstance(cell, ChildReading)
            for reading in case_readings(runtime, cell)
        ],
        "unavailable": missing_cells(matrix, runtimes, cases),
    }


def runtime_identities(runtimes: Sequence[str], spans: Spans) -> dict[str, RuntimeStatus]:
    identities: dict[str, RuntimeStatus] = {}
    for runtime in runtimes:
        with spans.span("setup", "identity", member=SUBJECT, runtime=runtime):
            identities[runtime] = probe_runtime(runtime, ENVIRONMENT_NAMESPACE)
    return identities


def _emit(document: Mapping[str, object], out: Path | None) -> None:
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if out is None:
        print(rendered, end="")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")


def _measured(spans: Spans, out: Path | None, metadata: Path | None) -> int:
    runtimes = supported_minors()
    if metadata is not None:
        identities = runtime_identities(runtimes, spans)
        write_sidecar(metadata, lambda path: write_metadata(path, SUBJECT, identities))
    matrix = timed_matrix(runtimes, CASE_NAMES, spans)
    absent = missing_cells(matrix, runtimes, CASE_NAMES)
    if absent:
        print("\n".join(("the feature-boundary matrix is incomplete:", *absent)), file=sys.stderr)
        return 3
    contract = BudgetContract.load()
    try:
        envelope = build_envelope(contract, _provenance(contract), matrix)
        _emit(envelope.document(), out)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 3
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--durations", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--select", action="append", default=[])
    parser.add_argument("--runtime", action="append", default=[])
    args = parser.parse_args(argv)
    if (
        ((args.select or args.runtime) and not args.diagnostic)
        or (args.diagnostic and (args.canary or args.out or args.durations or args.metadata))
        or (args.canary and (args.durations or args.metadata))
    ):
        parser.error(
            "selection requires --diagnostic; diagnostics and canaries "
            "cannot write measurement sidecars"
        )
    if args.diagnostic:
        runtimes = tuple(args.runtime) or supported_minors()
        if len(set(runtimes)) != len(runtimes) or set(runtimes) - set(supported_minors()):
            parser.error("runtime selection must name distinct supported CPython minors")
        cases = selected_cases(args.select) if args.select else CASE_NAMES
        if not cases:
            parser.error("no case matches the selection")
        _emit(diagnostic(runtimes, cases), None)
        return 0
    if args.canary:
        _emit(canary(BudgetContract.load()).document(), args.out)
        return 0
    spans = Spans()
    try:
        return _measured(spans, args.out, args.metadata)
    finally:
        if args.durations is not None:
            write_sidecar(args.durations, spans.write)


if __name__ == "__main__":
    raise SystemExit(main())
