"""Complete, valid member envelopes for the collector's shard and assembly
suites, built through the members' own envelope builders from synthetic child
readings, so no member subprocess ever runs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import lifecycle_overhead
import write_lowering_overhead as write_report
from cost_report import MEMBERS, Member
from interpreter_matrix import supported_minors
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import (
    CostReportEnvelope,
    Provenance,
    classify_authority,
)
from snapshot_delivery_overhead import (
    ChildReading,
    Selection,
    build_envelope,
    canary,
    every_cell,
    expanded_cells,
    expected_readings,
    is_memory_cell,
    selected_addresses,
    unit,
)

type Document = dict[str, Any]


def canary_provenance(contract: BudgetContract) -> Provenance:
    return canary(
        contract,
        lambda _request: ChildReading(1.0, "ms", (1.0,) * contract.timing_measured),
    ).provenance


def complete_snapshot(contract: BudgetContract, selected: Selection = every_cell) -> Document:
    """A valid Snapshot envelope over the addresses ``selected``."""
    runtimes = supported_minors()
    limits = {(cell.workload, cell.path): float(cell.value) for cell in expanded_cells(contract)}
    results: dict[tuple[str, str, str], tuple[ChildReading, ...]] = {}
    for runtime, workload, path in selected_addresses(contract, runtimes, selected):
        count = expected_readings(contract, path)
        value = limits.get((workload, path), 1.0)
        samples = () if is_memory_cell(path) else (value,) * contract.timing_measured
        results[(runtime, workload, path)] = tuple(
            ChildReading(value, unit(path), samples) for _ in range(count)
        )
    return build_envelope(
        contract, canary_provenance(contract), results, runtimes, selected
    ).document()


def complete_write(contract: BudgetContract) -> Document:
    matrix: write_report.Matrix = {
        runtime: {
            case: write_report._canary_reading(case)  # pyright: ignore[reportPrivateUsage] - canary seam
            for case in write_report.CASE_NAMES
        }
        for runtime in supported_minors()
    }
    return write_report.build_envelope(
        contract,
        write_report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage] - entrypoint seam
        matrix,
    ).document()


def optional_document(member: Member, contract: BudgetContract) -> Document:
    return CostReportEnvelope(
        member.subject, canary_provenance(contract), "non-authoritative"
    ).document()


def clean(document: Document, contract: BudgetContract, commit: str | None = None) -> Document:
    """``document`` as a clean capture at ``commit``, its authority reclassified
    from the provenance it then carries."""
    cleaned = deepcopy(document)
    provenance = cast("dict[str, Any]", cleaned["provenance"])
    provenance["dirty"] = False
    if commit is not None:
        provenance["commit"] = commit
    cleaned["authority"] = classify_authority(Provenance.from_document(provenance), contract)
    return cleaned


def lifecycle_document(contract: BudgetContract) -> Document:
    """The lifecycle member's canary: readings and comparisons without a timer."""
    provenance = replace(canary_provenance(contract), sampling={"timing": {"canary": 2}})
    return lifecycle_overhead.canary(contract, provenance).document()


def member_envelopes(contract: BudgetContract) -> dict[str, Document]:
    """One dirty-tree envelope per member, keyed by subject."""
    envelopes: dict[str, Document] = {}
    for member in MEMBERS:
        if member.subject == "snapshot-delivery":
            envelopes[member.subject] = complete_snapshot(contract)
        elif member.subject == write_report.SUBJECT:
            envelopes[member.subject] = complete_write(contract)
        elif member.subject == lifecycle_overhead.SUBJECT:
            envelopes[member.subject] = lifecycle_document(contract)
        else:
            envelopes[member.subject] = optional_document(member, contract)
    return envelopes
