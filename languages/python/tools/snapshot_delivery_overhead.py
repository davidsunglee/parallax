"""Emit the complete Snapshot delivery Budget Contract portfolio.

The report expands work from the contract, takes every quantitative reading in
``snapshot_delivery_reading.py`` children on every supported CPython minor, and
emits one Cost Report Envelope. The contract's ceilings are compared on the
runtime its authority fingerprint names; every other runtime's readings are
evidence beside them. The provider-free geometry read families are read the
same way and compared against nothing. Budget outcomes are observations: an
outside reading never changes this command's exit status. Missing or malformed
readings are explicit incompleteness and errors.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal, cast

from interpreter_matrix import (
    CURRENT_MINOR,
    authority_minor,
    child_command,
    child_environment,
    supported_minors,
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
    catalog,
    workload_digest,
)

WORKSPACE: Final = Path(__file__).resolve().parents[1]
READING_SCRIPT: Final = Path(__file__).resolve().parent / "snapshot_delivery_reading.py"
SUBJECT: Final = "snapshot-delivery"
ENVIRONMENT_NAMESPACE: Final = "snapshot-delivery"
GEOMETRY_METRICS: Final = ("elapsedUsPerRoot", "peakKiB", "retainedKiB")
LIVE_WINDOW: Final = "live-delivery"
PROVIDER_FREE_WINDOW: Final = "provider-free-delivery"
STRESS_WINDOW: Final = "positional-materialization"
WINDOW_DESCRIPTIONS: Final[Mapping[str, str]] = {
    LIVE_WINDOW: "a connected Wire find or stream against PostgreSQL, parsing included",
    PROVIDER_FREE_WINDOW: (
        "a Wire find over already-parsed provider rows through production planning, "
        "materialization, and publication; no parsing or provider work"
    ),
    STRESS_WINDOW: "the shipped raw-row conversion loop over prepared reads, to a finished Page",
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
        GeometryCell(f"read-{level.id}", f"{layout}.{metric}")
        for level in GEOMETRY_LEVELS
        for layout in STRUCTURAL_LAYOUTS
        for metric in GEOMETRY_METRICS
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


def window_of(path: str) -> str:
    """The window one cell path is read over."""
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
        window=window_of(path),
        runtime=runtime,
    )


def addresses(contract: BudgetContract, runtimes: Sequence[str]) -> tuple[Address, ...]:
    """Every (runtime, workload, cell) address a complete envelope carries."""
    return tuple(
        (runtime, cell.workload, cell.path)
        for runtime in runtimes
        for cell in (*expanded_cells(contract), *geometry_cells())
    )


def build_envelope(
    contract: BudgetContract,
    provenance: Provenance,
    results: Mapping[Address, Sequence[ChildResult]],
    runtimes: Sequence[str] = (CURRENT_MINOR,),
) -> CostReportEnvelope:
    """Build and validate the report envelope from all attempted cells."""
    readings: list[Reading] = []
    diagnostics: list[Diagnostic] = []
    by_address: dict[Address, Reading] = {}
    scaling_arms = contract.memory_scaling_arms
    for address in addresses(contract, runtimes):
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
        reading = _reading(runtime, workload, path, successful, scaling_arms)
        readings.append(reading)
        by_address[address] = reading
    complete = not diagnostics and len(readings) == len(addresses(contract, runtimes))
    compared = authority_minor(contract.authority)
    comparisons = tuple(
        comparison(
            cell,
            by_address.get((compared, cell.workload, cell.path)),
            contract,
            complete=complete,
        )
        for cell in expanded_cells(contract)
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


def _measure_runtime(
    contract: BudgetContract,
    provisioner: Provisioner,
    runner: ChildRunner,
    runtime: str,
    results: dict[Address, list[ChildResult]],
) -> None:
    workloads = catalog(contract)
    cells = expanded_cells(contract)
    memory_children = contract.memory_children
    scaling_arms = contract.memory_scaling_arms
    for workload_id in contract.workload_ids:
        workload = workloads[workload_id]
        live = [
            cell for cell in cells if cell.workload == workload_id and needs_database(cell.path)
        ]
        if live:
            workload.provision(provisioner, scaling_arms[0])
        for cell in live:
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
                workload.provision(provisioner, roots)
            for cell in memory_live:
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
            if cell.workload != workload_id or needs_database(cell.path):
                continue
            for _ in range(memory_children if is_memory_cell(cell.path) else 1):
                results[(runtime, cell.workload, cell.path)].append(
                    runner(
                        _request(contract, runtime, cell.workload, cell.path, scaling_arms[0], None)
                    )
                )
    for cell in geometry_cells():
        for _ in range(memory_children if is_memory_cell(cell.path) else 1):
            results[(runtime, cell.workload, cell.path)].append(
                runner(_request(contract, runtime, cell.workload, cell.path, scaling_arms[0], None))
            )


def measure(
    contract: BudgetContract,
    provisioner: Provisioner,
    runner: ChildRunner,
    runtimes: Sequence[str] | None = None,
) -> CostReportEnvelope:
    selected = tuple(runtimes) if runtimes is not None else supported_minors()
    results: dict[Address, list[ChildResult]] = {
        address: [] for address in addresses(contract, selected)
    }
    for runtime in selected:
        _measure_runtime(contract, provisioner, runner, runtime, results)
    server_version = provisioner.port.execute("show server_version", ())[0][0]
    provenance = Provenance.capture(
        contract,
        workload_digest=workload_digest(catalog(contract)),
        postgres=_CanaryPostgres(str(server_version)),
    )
    return build_envelope(contract, provenance, results, selected)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, received {value!r}")
    return float(value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args(argv)
    contract = BudgetContract.load()
    if args.canary:
        envelope = canary(contract, run_child)
    else:
        provisioner = Provisioner()
        try:
            envelope = measure(contract, provisioner, run_child)
        finally:
            provisioner.close()
    rendered = json.dumps(envelope.document(), indent=2, sort_keys=True)
    if args.out is None:
        print(rendered)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
