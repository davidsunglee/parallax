"""Emit the complete Snapshot delivery Budget Contract portfolio.

The report expands work from the contract, takes every quantitative reading in
``snapshot_delivery_reading.py`` children on every supported CPython minor, and
emits one Cost Report Envelope. The contract's ceilings are compared on the
runtime its authority fingerprint names; every other runtime's readings are
evidence beside them. The provider-free geometry read families are read the
same way and compared against nothing. Budget outcomes are observations: an
outside reading never changes this command's exit status. Missing or malformed
readings are explicit incompleteness and errors.

``--workload`` narrows the evidence path to named contract workloads and the
``geometry`` and ``plan`` groups: the envelope keeps full provenance and
completeness is judged over the addresses selected, so a slice of the matrix is
evidence about that slice, never a diagnostic promoted to evidence.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final, Literal, cast

from durations import Spans, write_sidecar
from interpreter_matrix import (
    CURRENT_MINOR,
    ProbeRunner,
    RuntimeStatus,
    authority_minor,
    child_command,
    child_environment,
    probe_runtime,
    run_probe,
    supported_minors,
    write_metadata,
)
from parallax.conformance.budget import BudgetCell, BudgetContract
from parallax.conformance.cost_envelope import (
    Comparison,
    CostReportEnvelope,
    Diagnostic,
    Provenance,
    Reading,
    classify_authority,
    validate,
)
from parallax.conformance.provision import Provisioner
from parallax.conformance.workloads import (
    GEOMETRY_LEVELS,
    STRUCTURAL_LAYOUTS,
    Workload,
    catalog,
    plan_levels,
    workload_digest,
)

WORKSPACE: Final = Path(__file__).resolve().parents[1]
READING_SCRIPT: Final = Path(__file__).resolve().parent / "snapshot_delivery_reading.py"
SUBJECT: Final = "snapshot-delivery"
ENVIRONMENT_NAMESPACE: Final = "snapshot-delivery"
GEOMETRY_METRICS: Final = ("elapsedUsPerRoot", "peakKiB", "retainedKiB")
PLAN_METRICS: Final = ("elapsedUs", "peakKiB", "retainedKiB")
GEOMETRY_PREFIX: Final = "read-"
PLAN_PREFIX: Final = "plan-"
LIVE_WINDOW: Final = "live-delivery"
PROVIDER_FREE_WINDOW: Final = "provider-free-delivery"
STRESS_WINDOW: Final = "positional-materialization"
PLAN_WINDOW: Final = "read-plan-compilation"
WINDOW_DESCRIPTIONS: Final[Mapping[str, str]] = {
    LIVE_WINDOW: "a connected Wire find or stream against PostgreSQL, parsing included",
    PROVIDER_FREE_WINDOW: (
        "a Wire find over already-parsed provider rows through production planning, "
        "materialization, and publication; no parsing or provider work"
    ),
    STRESS_WINDOW: "the shipped raw-row conversion loop over prepared reads, to a finished Page",
    PLAN_WINDOW: (
        "one whole-table instance read planned into an already composed and empty read plan "
        "cache of production capacity; no cache construction, model preparation, query "
        "validation, execution, or materialization"
    ),
}


@dataclass(frozen=True, slots=True)
class ChildRequest:
    workload: str
    cell: str
    roots: int
    warmups: int
    measured: int
    connection_info: str | None = None
    runtime: str = CURRENT_MINOR


@dataclass(frozen=True, slots=True)
class ChildReading:
    value: float
    unit: str
    samples: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class GeometryCell:
    """One provider-free geometry read address: a level's read under one layout."""

    workload: str
    path: str


type ChildResult = ChildReading | Diagnostic
type ChildRunner = Callable[[ChildRequest], ChildResult]
type Address = tuple[str, str, str]
"""A reading's (runtime, workload, cell) address."""


def expanded_cells(contract: BudgetContract) -> tuple[BudgetCell, ...]:
    """Every required numeric cell, in authored contract order."""
    return tuple(cell for workload in contract.workload_ids for cell in contract.cells(workload))


def geometry_cells() -> tuple[GeometryCell, ...]:
    """Every geometry read address, in level then layout then metric order."""
    return tuple(
        GeometryCell(f"{GEOMETRY_PREFIX}{level.id}", f"{layout}.{metric}")
        for level in GEOMETRY_LEVELS
        for layout in STRUCTURAL_LAYOUTS
        for metric in GEOMETRY_METRICS
    )


def plan_cells() -> tuple[GeometryCell, ...]:
    """Every read-plan compilation address, in level then layout then metric order."""
    return tuple(
        GeometryCell(f"{PLAN_PREFIX}{level.id}", f"{layout}.{metric}")
        for level in plan_levels()
        for layout in STRUCTURAL_LAYOUTS
        for metric in PLAN_METRICS
    )


def is_memory_cell(path: str) -> bool:
    return path.startswith(("eagerMemory.", "streamedMemory.")) or path.endswith(
        (
            "retainedBPerProjection",
            "transientBPerProjection",
            "peakFor64KiB",
            "preparedSetKiB",
            ".peakKiB",
            ".retainedKiB",
        )
    )


def is_scaling_cell(path: str) -> bool:
    return path.startswith("streamedMemory.")


def needs_database(path: str) -> bool:
    return path.startswith(("live.", "firstResult.", "eagerMemory.", "streamedMemory."))


def window_of(path: str, workload: str = "") -> str:
    """The window one cell is read over."""
    if workload.startswith(PLAN_PREFIX):
        return PLAN_WINDOW
    if needs_database(path):
        return LIVE_WINDOW
    if path.startswith("stress."):
        return STRESS_WINDOW
    return PROVIDER_FREE_WINDOW


def _child_command(request: ChildRequest) -> list[str]:
    arguments = [
        "--workload",
        request.workload,
        "--cell",
        request.cell,
        "--roots",
        str(request.roots),
        "--warmups",
        str(request.warmups),
        "--measured",
        str(request.measured),
    ]
    if request.connection_info is not None:
        arguments += ["--connection-info", request.connection_info]
    return child_command(request.runtime, READING_SCRIPT, arguments)


def run_child(request: ChildRequest) -> ChildResult:
    """Run one isolated reading child and decode its final JSON line."""
    completed = subprocess.run(
        _child_command(request),
        cwd=WORKSPACE,
        env=child_environment(request.runtime, ENVIRONMENT_NAMESPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    label = f"CPython {request.runtime} {request.workload}.{request.cell}"
    if completed.returncode != 0:
        return Diagnostic(
            "cell-child-failed",
            f"{label} ({request.roots} roots) exited "
            f"{completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}",
        )
    lines = completed.stdout.strip().splitlines()
    if not lines:
        return Diagnostic("cell-child-empty", f"{label} printed no reading")
    try:
        document = cast("Mapping[str, Any]", json.loads(lines[-1]))
        samples = tuple(_number(value) for value in cast("Sequence[object]", document["samples"]))
        return ChildReading(_number(document["value"]), str(document["unit"]), samples)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return Diagnostic("cell-child-invalid", f"{label} returned an invalid reading: {error}")


def operator(path: str) -> Literal["at-most", "at-least"]:
    return "at-least" if ".min" in path else "at-most"


def unit(path: str) -> str:
    if path.endswith("maxMs"):
        return "ms"
    if path.endswith("minRootsPerSecond"):
        return "roots/s"
    if path.endswith("maxUsPerProjection"):
        return "us/projection"
    if path.endswith("minProjectionsPerSecond"):
        return "projections/s"
    if path.endswith(("retainedBPerProjection", "transientBPerProjection")):
        return "B/projection"
    if path.endswith("elapsedUsPerRoot"):
        return "us/root"
    if path.endswith(".elapsedUs"):
        return "us"
    return "KiB"


def within(cell: BudgetCell, reading: Reading, contract: BudgetContract) -> bool:
    timing = cast("Mapping[str, object]", contract.sampling["timing"])
    memory = cast("Mapping[str, object]", contract.sampling["memory"])
    median_ok = (
        reading.value >= cell.value
        if operator(cell.path) == "at-least"
        else reading.value <= cell.value
    )
    if not reading.samples:
        return median_ok
    if is_memory_cell(cell.path):
        return median_ok and max(reading.samples) <= float(cell.value) * _number(
            memory["individualMax"]
        )
    ordered = sorted(reading.samples)
    spread = _number(timing["secondSlowestMax"])
    if operator(cell.path) == "at-least":
        return median_ok and ordered[1] >= float(cell.value) / spread
    return median_ok and ordered[-2] <= float(cell.value) * spread


def comparison(
    cell: BudgetCell,
    reading: Reading | None,
    contract: BudgetContract,
    *,
    complete: bool,
) -> Comparison:
    outcome: Literal["within", "outside", "unavailable"]
    if reading is None or not complete:
        outcome = "unavailable"
    else:
        outcome = "within" if within(cell, reading, contract) else "outside"
    return Comparison(
        cell.workload,
        cell.path,
        operator(cell.path),
        float(cell.value),
        reading.unit if reading is not None else unit(cell.path),
        outcome,
    )


def expected_readings(contract: BudgetContract, path: str) -> int:
    """How many isolated child readings one cell path takes."""
    if is_scaling_cell(path):
        return contract.memory_children * len(contract.memory_scaling_arms)
    if is_memory_cell(path):
        return contract.memory_children
    return 1


def _reading(
    runtime: str,
    workload: str,
    path: str,
    results: Sequence[ChildReading],
    scaling_arms: Sequence[int],
) -> Reading:
    samples = tuple(sample for result in results for sample in (result.samples or (result.value,)))
    if is_scaling_cell(path):
        split = len(results) // len(scaling_arms)
        value = statistics.median(result.value for result in results[:split])
    else:
        value = statistics.median(samples)
    return Reading(
        workload,
        path,
        float(value),
        results[0].unit,
        samples,
        window=window_of(path, workload),
        runtime=runtime,
    )


def addresses(contract: BudgetContract, runtimes: Sequence[str]) -> tuple[Address, ...]:
    """Every (runtime, workload, cell) address a complete envelope carries."""
    return tuple(
        (runtime, cell.workload, cell.path)
        for runtime in runtimes
        for cell in (*expanded_cells(contract), *geometry_cells(), *plan_cells())
    )


def selected_addresses(
    contract: BudgetContract, runtimes: Sequence[str], selected: Selection
) -> tuple[Address, ...]:
    """The addresses among :func:`addresses` that ``selected`` keeps."""
    return tuple(
        address for address in addresses(contract, runtimes) if selected(address[1], address[2])
    )


def _collected(
    contract: BudgetContract,
    results: Mapping[Address, Sequence[ChildResult]],
    selected: Sequence[Address],
) -> tuple[list[Reading], list[Diagnostic]]:
    """Every reading ``results`` completes among ``selected``, and every reason
    one of them is unavailable."""
    readings: list[Reading] = []
    diagnostics: list[Diagnostic] = []
    scaling_arms = contract.memory_scaling_arms
    for address in selected:
        runtime, workload, path = address
        outcomes = results.get(address, ())
        failures = [outcome for outcome in outcomes if isinstance(outcome, Diagnostic)]
        successful = [outcome for outcome in outcomes if isinstance(outcome, ChildReading)]
        diagnostics.extend(failures)
        expected = expected_readings(contract, path)
        if len(successful) != expected:
            diagnostics.append(
                Diagnostic(
                    "cell-unavailable",
                    f"CPython {runtime} {workload}.{path}: expected {expected} isolated "
                    f"reading(s), received {len(successful)}",
                )
            )
            continue
        readings.append(_reading(runtime, workload, path, successful, scaling_arms))
    return readings, diagnostics


def build_envelope(
    contract: BudgetContract,
    provenance: Provenance,
    results: Mapping[Address, Sequence[ChildResult]],
    runtimes: Sequence[str] = (CURRENT_MINOR,),
    selected: Selection | None = None,
) -> CostReportEnvelope:
    """Build and validate the report envelope from all attempted cells among
    the addresses ``selected``, comparing the selected contract cells."""
    chosen = selected if selected is not None else every_cell
    expected = selected_addresses(contract, runtimes, chosen)
    readings, diagnostics = _collected(contract, results, expected)
    by_address = {
        (reading.runtime or "", reading.workload, reading.cell): reading for reading in readings
    }
    complete = not diagnostics and len(readings) == len(expected)
    compared = authority_minor(contract.authority)
    comparisons = tuple(
        comparison(
            cell,
            by_address.get((compared, cell.workload, cell.path)),
            contract,
            complete=complete,
        )
        for cell in expanded_cells(contract)
        if chosen(cell.workload, cell.path)
    )
    envelope = CostReportEnvelope(
        SUBJECT,
        provenance,
        classify_authority(provenance, contract),
        tuple(readings),
        comparisons,
        tuple(diagnostics),
    )
    validate(envelope)
    return envelope


class _CanaryPostgres:
    def __init__(self, version: str) -> None:
        self._version = version

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[object] = (),
    ) -> list[Mapping[str, object]]:
        del binds, document_reads
        if sql != "show server_version":
            raise ValueError(sql)
        return [{"server_version": self._version}]


def canary(contract: BudgetContract, runner: ChildRunner) -> CostReportEnvelope:
    cell = expanded_cells(contract)[0]
    result = runner(
        ChildRequest(
            cell.workload,
            cell.path,
            contract.memory_scaling_arms[0],
            contract.timing_warmups,
            contract.timing_measured,
        )
    )
    provenance = Provenance.capture(
        contract,
        workload_digest=workload_digest(),
        postgres=_CanaryPostgres(str(contract.authority["postgres"])),
    )
    provenance = replace(provenance, dirty=True)
    return build_envelope(
        contract, provenance, {(CURRENT_MINOR, cell.workload, cell.path): (result,)}
    )


def _request(
    contract: BudgetContract,
    runtime: str,
    workload: str,
    path: str,
    roots: int,
    connection_info: str | None,
) -> ChildRequest:
    return ChildRequest(
        workload,
        path,
        roots,
        contract.timing_warmups,
        contract.timing_measured,
        connection_info,
        runtime,
    )


type Selection = Callable[[str, str], bool]
"""Whether one (workload, cell) address is measured."""


def every_cell(_workload: str, _path: str) -> bool:
    return True


GEOMETRY_GROUP: Final = "geometry"
PLAN_GROUP: Final = "plan"
WORKLOAD_GROUPS: Final = (GEOMETRY_GROUP, PLAN_GROUP)


def workload_names(contract: BudgetContract) -> tuple[str, ...]:
    """Every name ``--workload`` accepts: the contract's workload ids, then the
    two groups of cells outside the contract."""
    return (*contract.workload_ids, *WORKLOAD_GROUPS)


def workload_selection(names: Iterable[str], contract: BudgetContract | None = None) -> Selection:
    """The addresses the exact workload ``names`` cover: a contract workload id
    selects its cells, ``geometry`` and ``plan`` select the groups outside the
    contract, and no name at all selects every cell. An unknown name is a
    ``ValueError`` before any work starts."""
    active = contract if contract is not None else BudgetContract.load()
    known = workload_names(active)
    chosen = frozenset(names)
    unknown = sorted(chosen - frozenset(known))
    if unknown:
        raise ValueError(f"unknown workload {', '.join(unknown)}; workloads are {list(known)}")
    if not chosen:
        return every_cell

    def selected(workload: str, _path: str) -> bool:
        if workload.startswith(GEOMETRY_PREFIX):
            return GEOMETRY_GROUP in chosen
        if workload.startswith(PLAN_PREFIX):
            return PLAN_GROUP in chosen
        return workload in chosen

    return selected


def _measure_runtime(
    contract: BudgetContract,
    provisioner: Provisioner | None,
    runner: ChildRunner,
    runtime: str,
    results: dict[Address, list[ChildResult]],
    selected: Selection = every_cell,
    spans: Spans | None = None,
) -> None:
    recorder = spans if spans is not None else Spans()
    workloads = catalog(contract)
    cells = [cell for cell in expanded_cells(contract) if selected(cell.workload, cell.path)]
    memory_children = contract.memory_children
    scaling_arms = contract.memory_scaling_arms
    for workload_id in contract.workload_ids:
        workload_cells = [cell for cell in cells if cell.workload == workload_id]
        if not workload_cells:
            continue
        with recorder.span("workload", workload_id, member=SUBJECT, runtime=runtime):
            _measure_workload(
                contract,
                provisioner,
                runner,
                runtime,
                results,
                workloads[workload_id],
                workload_cells,
                recorder,
            )
    for group, group_cells in ((GEOMETRY_GROUP, geometry_cells()), (PLAN_GROUP, plan_cells())):
        chosen = [cell for cell in group_cells if selected(cell.workload, cell.path)]
        if not chosen:
            continue
        with recorder.span("workload", group, member=SUBJECT, runtime=runtime):
            for cell in chosen:
                for _ in range(memory_children if is_memory_cell(cell.path) else 1):
                    results[(runtime, cell.workload, cell.path)].append(
                        runner(
                            _request(
                                contract, runtime, cell.workload, cell.path, scaling_arms[0], None
                            )
                        )
                    )


def _provision(
    workload: Workload, provisioner: Provisioner, roots: int, runtime: str, recorder: Spans
) -> None:
    with recorder.span(
        "setup",
        "provision",
        member=SUBJECT,
        runtime=runtime,
        workload=workload.id,
        roots=str(roots),
    ):
        workload.provision(provisioner, roots)


def _measure_workload(
    contract: BudgetContract,
    provisioner: Provisioner | None,
    runner: ChildRunner,
    runtime: str,
    results: dict[Address, list[ChildResult]],
    workload: Workload,
    cells: Sequence[BudgetCell],
    recorder: Spans,
) -> None:
    memory_children = contract.memory_children
    scaling_arms = contract.memory_scaling_arms
    live = [cell for cell in cells if needs_database(cell.path)]
    if live and provisioner is None:
        for cell in live:
            results[(runtime, cell.workload, cell.path)].append(
                Diagnostic(
                    "cell-unprovisioned",
                    f"CPython {runtime} {cell.workload}.{cell.path} needs a provisioned database",
                )
            )
        live = []
    if live:
        assert provisioner is not None
        _provision(workload, provisioner, scaling_arms[0], runtime, recorder)
    for cell in live:
        assert provisioner is not None
        for _ in range(memory_children if is_memory_cell(cell.path) else 1):
            results[(runtime, cell.workload, cell.path)].append(
                runner(
                    _request(
                        contract,
                        runtime,
                        cell.workload,
                        cell.path,
                        scaling_arms[0],
                        provisioner.connection_info,
                    )
                )
            )
    memory_live = [cell for cell in live if is_scaling_cell(cell.path)]
    for roots in scaling_arms[1:]:
        if memory_live:
            assert provisioner is not None
            _provision(workload, provisioner, roots, runtime, recorder)
        for cell in memory_live:
            assert provisioner is not None
            for _ in range(memory_children):
                results[(runtime, cell.workload, cell.path)].append(
                    runner(
                        _request(
                            contract,
                            runtime,
                            cell.workload,
                            cell.path,
                            roots,
                            provisioner.connection_info,
                        )
                    )
                )
    for cell in cells:
        if needs_database(cell.path):
            continue
        for _ in range(memory_children if is_memory_cell(cell.path) else 1):
            results[(runtime, cell.workload, cell.path)].append(
                runner(_request(contract, runtime, cell.workload, cell.path, scaling_arms[0], None))
            )


def measure(
    contract: BudgetContract,
    provisioner: Provisioner,
    runner: ChildRunner,
    runtimes: Sequence[str] | None = None,
    spans: Spans | None = None,
    selected: Selection = every_cell,
) -> CostReportEnvelope:
    chosen_runtimes = tuple(runtimes) if runtimes is not None else supported_minors()
    results: dict[Address, list[ChildResult]] = {
        address: [] for address in selected_addresses(contract, chosen_runtimes, selected)
    }
    for runtime in chosen_runtimes:
        _measure_runtime(contract, provisioner, runner, runtime, results, selected, spans)
    server_version = provisioner.port.execute("show server_version", ())[0][0]
    provenance = Provenance.capture(
        contract,
        workload_digest=workload_digest(catalog(contract)),
        postgres=_CanaryPostgres(str(server_version)),
    )
    return build_envelope(contract, provenance, results, chosen_runtimes, selected)


def selection(workloads: Sequence[str], cells: Sequence[str]) -> Selection:
    """The addresses whose workload matches any of ``workloads`` and whose cell
    matches any of ``cells``, as shell-style patterns; an empty list matches all."""

    def selected(workload: str, path: str) -> bool:
        return (not workloads or any(fnmatchcase(workload, p) for p in workloads)) and (
            not cells or any(fnmatchcase(path, p) for p in cells)
        )

    return selected


def diagnostic(
    contract: BudgetContract,
    runner: ChildRunner,
    runtimes: Sequence[str],
    selected: Selection,
    provisioner: Provisioner | None,
) -> dict[str, object]:
    """Readings for a chosen subset of addresses, as a diagnostic document.

    A diagnostic run answers a question about some cells; it is not evidence. It
    carries no provenance and is not an envelope, so nothing downstream can
    validate, verify, or retain it as a capture.
    """
    chosen = [
        address for address in addresses(contract, runtimes) if selected(address[1], address[2])
    ]
    results: dict[Address, list[ChildResult]] = {address: [] for address in chosen}
    for runtime in runtimes:
        _measure_runtime(contract, provisioner, runner, runtime, results, selected)
    readings, diagnostics = _collected(contract, results, chosen)
    return {
        "diagnostic": True,
        "subject": SUBJECT,
        "runtimes": list(runtimes),
        "readings": [reading.document() for reading in readings],
        "unavailable": [asdict(item) for item in diagnostics],
    }


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, received {value!r}")
    return float(value)


def _diagnostic_selects_live(
    contract: BudgetContract, runtimes: Sequence[str], selected: Selection
) -> bool:
    return any(
        needs_database(path)
        for _runtime, workload, path in addresses(contract, runtimes)
        if selected(workload, path)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--canary", action="store_true")
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="take readings for a subset of addresses; the result is not evidence",
    )
    parser.add_argument("--select", action="append", default=[], help="workload pattern")
    parser.add_argument("--cell", action="append", default=[], help="cell pattern")
    parser.add_argument("--runtime", action="append", default=[], help="CPython minor")
    parser.add_argument(
        "--workload",
        action="append",
        default=[],
        help="an exact contract workload id, or the geometry or plan group, to measure as evidence",
    )
    parser.add_argument(
        "--durations", type=Path, help="where the harness writes its spans; not evidence"
    )
    parser.add_argument(
        "--metadata", type=Path, help="where the runtime identities are written; not evidence"
    )
    args = parser.parse_args(argv)
    if (args.select or args.cell or args.runtime) and not args.diagnostic:
        parser.error("--select, --cell, and --runtime are diagnostic options")
    if args.diagnostic and args.out is not None:
        parser.error("a diagnostic run is not evidence and is printed, never written to a file")
    if args.durations is not None and (args.diagnostic or args.canary):
        parser.error("--durations records a complete measurement, never a diagnostic or canary")
    if args.metadata is not None and (args.diagnostic or args.canary):
        parser.error("--metadata records a complete measurement, never a diagnostic or canary")
    if args.workload and (args.diagnostic or args.canary):
        parser.error("--workload selects evidence, never a diagnostic or canary")
    contract = BudgetContract.load()
    try:
        selected = workload_selection(args.workload, contract)
    except ValueError as error:
        parser.error(str(error))
    if args.diagnostic:
        runtimes = tuple(args.runtime) or supported_minors()
        selected = selection(args.select, args.cell)
        provisioner = (
            Provisioner() if _diagnostic_selects_live(contract, runtimes, selected) else None
        )
        try:
            document = diagnostic(contract, run_child, runtimes, selected, provisioner)
        finally:
            if provisioner is not None:
                provisioner.close()
        rendered = json.dumps(document, indent=2, sort_keys=True)
    elif args.canary:
        rendered = json.dumps(canary(contract, run_child).document(), indent=2, sort_keys=True)
    else:
        envelope = _measured(contract, args.durations, args.metadata, selected)
        rendered = json.dumps(envelope.document(), indent=2, sort_keys=True)
    if args.out is None:
        print(rendered)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


def runtime_identities(
    runtimes: Sequence[str], spans: Spans, probe: ProbeRunner = run_probe
) -> dict[str, RuntimeStatus]:
    """Each runtime's interpreter, probed once through the reading child's own
    command and environment resolution, outside every measured window."""
    identities: dict[str, RuntimeStatus] = {}
    for runtime in runtimes:
        with spans.span("setup", "identity", member=SUBJECT, runtime=runtime):
            identities[runtime] = probe_runtime(runtime, ENVIRONMENT_NAMESPACE, probe)
    return identities


def _measured(
    contract: BudgetContract,
    durations: Path | None,
    metadata: Path | None,
    selected: Selection = every_cell,
) -> CostReportEnvelope:
    spans = Spans()
    try:
        if metadata is not None:
            identities = runtime_identities(supported_minors(), spans, run_probe)
            write_sidecar(metadata, lambda path: write_metadata(path, SUBJECT, identities))
        with spans.span("setup", "provisioner", member=SUBJECT):
            provisioner = Provisioner()
        try:
            return measure(contract, provisioner, run_child, spans=spans, selected=selected)
        finally:
            with spans.span("setup", "close", member=SUBJECT):
                provisioner.close()
    finally:
        if durations is not None:
            write_sidecar(durations, spans.write)


if __name__ == "__main__":
    raise SystemExit(main())
