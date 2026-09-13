"""Emit the complete Snapshot delivery Budget Contract portfolio.

The report expands work from the contract, takes every quantitative reading in
``snapshot_delivery_reading.py`` children, and emits one Cost Report Envelope.
Budget outcomes are observations: an outside reading never changes this command's
exit status. Missing or malformed readings are explicit incompleteness and errors.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal, cast

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
from parallax.conformance.workloads import catalog, workload_digest

WORKSPACE: Final = Path(__file__).resolve().parents[1]
READING_SCRIPT: Final = Path(__file__).resolve().parent / "snapshot_delivery_reading.py"
SUBJECT: Final = "snapshot-delivery"
MEMORY_ROOTS: Final = (200, 2_000)
HASH_SEED: Final = "0"


@dataclass(frozen=True, slots=True)
class ChildRequest:
    workload: str
    cell: str
    roots: int
    connection_info: str | None = None


@dataclass(frozen=True, slots=True)
class ChildReading:
    value: float
    unit: str
    samples: tuple[float, ...]


type ChildResult = ChildReading | Diagnostic
type ChildRunner = Callable[[ChildRequest], ChildResult]


def expanded_cells(contract: BudgetContract) -> tuple[BudgetCell, ...]:
    """Every required numeric cell, in authored contract order."""
    return tuple(cell for workload in contract.workload_ids for cell in contract.cells(workload))


def is_memory_cell(path: str) -> bool:
    return path.startswith(("eagerMemory.", "streamedMemory.")) or path.startswith(
        (
            "stress.retainedBPerProjection",
            "stress.transientBPerProjection",
            "stress.peakFor64KiB",
            "stress.preparedSetKiB",
        )
    )


def is_scaling_cell(path: str) -> bool:
    return path.startswith("streamedMemory.")


def needs_database(path: str) -> bool:
    return path.startswith(("live.", "firstResult.", "eagerMemory.", "streamedMemory."))


def _child_command(request: ChildRequest) -> list[str]:
    command = [
        sys.executable,
        str(READING_SCRIPT),
        "--workload",
        request.workload,
        "--cell",
        request.cell,
        "--roots",
        str(request.roots),
    ]
    if request.connection_info is not None:
        command += ["--connection-info", request.connection_info]
    return command


def run_child(request: ChildRequest) -> ChildResult:
    """Run one isolated reading child and decode its final JSON line."""
    excluded = {
        "COV_CORE_SOURCE",
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COVERAGE_PROCESS_START",
    }
    environment = {name: value for name, value in os.environ.items() if name not in excluded}
    environment["PYTHONHASHSEED"] = HASH_SEED
    completed = subprocess.run(
        _child_command(request),
        cwd=WORKSPACE,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return Diagnostic(
            "cell-child-failed",
            f"{request.workload}.{request.cell} ({request.roots} roots) exited "
            f"{completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}",
        )
    lines = completed.stdout.strip().splitlines()
    if not lines:
        return Diagnostic(
            "cell-child-empty", f"{request.workload}.{request.cell} printed no reading"
        )
    try:
        document = cast("Mapping[str, Any]", json.loads(lines[-1]))
        samples = tuple(_number(value) for value in cast("Sequence[object]", document["samples"]))
        return ChildReading(_number(document["value"]), str(document["unit"]), samples)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return Diagnostic(
            "cell-child-invalid",
            f"{request.workload}.{request.cell} returned an invalid reading: {error}",
        )


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


def _reading(cell: BudgetCell, results: Sequence[ChildReading]) -> Reading:
    samples = tuple(sample for result in results for sample in (result.samples or (result.value,)))
    if is_scaling_cell(cell.path):
        split = len(results) // len(MEMORY_ROOTS)
        value = statistics.median(result.value for result in results[:split])
    else:
        value = statistics.median(samples)
    return Reading(cell.workload, cell.path, float(value), results[0].unit, samples)


def build_envelope(
    contract: BudgetContract,
    provenance: Provenance,
    results: Mapping[tuple[str, str], Sequence[ChildResult]],
) -> CostReportEnvelope:
    """Build and validate the report envelope from all attempted cells."""
    readings: list[Reading] = []
    diagnostics: list[Diagnostic] = []
    by_cell: dict[tuple[str, str], Reading] = {}
    memory = cast("Mapping[str, object]", contract.sampling["memory"])
    memory_children = int(_number(memory["children"]))
    for cell in expanded_cells(contract):
        outcomes = results.get((cell.workload, cell.path), ())
        failures = [outcome for outcome in outcomes if isinstance(outcome, Diagnostic)]
        successful = [outcome for outcome in outcomes if isinstance(outcome, ChildReading)]
        diagnostics.extend(failures)
        expected = (
            memory_children * len(MEMORY_ROOTS)
            if is_scaling_cell(cell.path)
            else memory_children
            if is_memory_cell(cell.path)
            else 1
        )
        if len(successful) != expected:
            diagnostics.append(
                Diagnostic(
                    "cell-unavailable",
                    f"{cell.workload}.{cell.path}: expected {expected} isolated reading(s), "
                    f"received {len(successful)}",
                )
            )
            continue
        reading = _reading(cell, successful)
        readings.append(reading)
        by_cell[(cell.workload, cell.path)] = reading
    complete = not diagnostics and len(readings) == len(expanded_cells(contract))
    comparisons = tuple(
        comparison(
            cell,
            by_cell.get((cell.workload, cell.path)),
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
    result = runner(ChildRequest(cell.workload, cell.path, 200))
    provenance = Provenance.capture(
        contract,
        workload_digest=workload_digest(),
        postgres=_CanaryPostgres(str(contract.authority["postgres"])),
    )
    provenance = replace(provenance, dirty=True)
    return build_envelope(contract, provenance, {(cell.workload, cell.path): (result,)})


def measure(
    contract: BudgetContract, provisioner: Provisioner, runner: ChildRunner
) -> CostReportEnvelope:
    workloads = catalog(contract)
    cells = expanded_cells(contract)
    results: dict[tuple[str, str], list[ChildResult]] = {
        (cell.workload, cell.path): [] for cell in cells
    }
    memory = cast("Mapping[str, object]", contract.sampling["memory"])
    memory_children = int(_number(memory["children"]))
    for workload_id in contract.workload_ids:
        workload = workloads[workload_id]
        live = [
            cell for cell in cells if cell.workload == workload_id and needs_database(cell.path)
        ]
        if live:
            workload.provision(provisioner, MEMORY_ROOTS[0])
        for cell in live:
            repeats = memory_children if is_memory_cell(cell.path) else 1
            for _ in range(repeats):
                results[(cell.workload, cell.path)].append(
                    runner(
                        ChildRequest(
                            cell.workload,
                            cell.path,
                            MEMORY_ROOTS[0],
                            provisioner.connection_info,
                        )
                    )
                )
        memory_live = [cell for cell in live if is_scaling_cell(cell.path)]
        if memory_live:
            workload.provision(provisioner, MEMORY_ROOTS[1])
        for cell in memory_live:
            for _ in range(memory_children):
                results[(cell.workload, cell.path)].append(
                    runner(
                        ChildRequest(
                            cell.workload,
                            cell.path,
                            MEMORY_ROOTS[1],
                            provisioner.connection_info,
                        )
                    )
                )
        for cell in cells:
            if cell.workload != workload_id or needs_database(cell.path):
                continue
            repeats = memory_children if is_memory_cell(cell.path) else 1
            for _ in range(repeats):
                results[(cell.workload, cell.path)].append(
                    runner(ChildRequest(cell.workload, cell.path, MEMORY_ROOTS[0]))
                )
    server_version = provisioner.port.execute("show server_version", ())[0][0]
    provenance = Provenance.capture(
        contract,
        workload_digest=workload_digest(workloads),
        postgres=_CanaryPostgres(str(server_version)),
    )
    return build_envelope(contract, provenance, results)


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
