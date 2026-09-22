"""Complete, valid member envelopes for the collector's shard, assembly, and
workflow-adapter suites, built through the members' own envelope builders from
synthetic child readings, and shard captures written from them, so no member
subprocess ever runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import instance_state_overhead as instance_report
import lifecycle_overhead
import write_lowering_overhead as write_report
from cost_report import (
    HEAD,
    MEMBERS,
    SHARDS,
    WORKLOAD_OPTION,
    Member,
    MemberResult,
    Request,
    Shard,
    ShardResult,
    write_shard,
)
from durations import Spans
from interpreter_matrix import RuntimeIdentity, RuntimeStatus, supported_minors
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
from tests.unit._instance_state_support import REPORTED, Scenario

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


def _instance_arm(scenario: Scenario, retained: int, ratio: float) -> instance_report.ArmReading:
    cells = len(scenario.values) + len(scenario.unloaded)
    baseline_ns = float(max(cells, 1) * 100)
    return instance_report.ArmReading(
        cells=cells,
        retained_bytes=retained,
        bare_bytes=retained - max(cells, 1),
        peak_bytes=retained + max(cells, 1),
        construct_ns=baseline_ns * ratio,
        call_ns=baseline_ns / max(cells, 1),
        scaffolding_ns=0.0,
        read_ns=baseline_ns * ratio,
        dump_ns=baseline_ns * ratio,
    )


def _instance_reading(scenario: Scenario, contract: BudgetContract) -> instance_report.Reading:
    scale = max(len(scenario.values) + len(scenario.unloaded), 1)
    legacy = scale * 100
    return instance_report.Reading(
        scenario.name,
        scenario.summary,
        len(scenario.values),
        contract.timing_warmups,
        _instance_arm(scenario, legacy * 2, 1.0),
        _instance_arm(scenario, legacy, 1.0),
        _instance_arm(scenario, legacy // 2, 1.0),
        instance_report.ProjectionReading(
            retained_bytes=scale * 10,
            peak_bytes=scale * 20,
            projection_ns=scale * 100.0,
            projection_reuse_ns=scale * 80.0,
            direct_wire_ns=scale * 90.0,
        )
        if scenario in instance_report.SCENARIOS
        else None,
    )


def complete_instance_state(contract: BudgetContract) -> Document:
    """A complete instance-state envelope over every supported minor, its
    compact arm retaining half of the legacy one and moving no operation."""
    matrix: instance_report.Matrix = {
        runtime: {scenario.name: _instance_reading(scenario, contract) for scenario in REPORTED}
        for runtime in supported_minors()
    }
    return instance_report.build_envelope(
        contract,
        instance_report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage] - entrypoint seam
        matrix,
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


def shard_envelope(
    shard: Shard, envelopes: Mapping[str, Document], contract: BudgetContract
) -> Document:
    """The envelope ``shard`` collects, from ``envelopes`` keyed by subject: the
    member's whole envelope, or for a workload shard the Snapshot envelope's
    readings and comparisons narrowed to the shard's selection, keeping the
    provenance and authority the whole envelope carries."""
    document = envelopes[shard.subject]
    if shard.workloads is None:
        return document
    selected = shard.selection(contract)
    return {
        **document,
        "readings": [
            reading
            for reading in cast("list[Document]", document["readings"])
            if selected(reading["workload"], reading["cell"])
        ],
        "comparisons": [
            comparison
            for comparison in cast("list[Document]", document["comparisons"])
            if selected(comparison["workload"], comparison["cell"])
        ],
    }


def shard_envelopes(
    envelopes: Mapping[str, Document], contract: BudgetContract, plan: Sequence[Shard] = SHARDS
) -> dict[str, Document]:
    """One envelope per shard of ``plan``, keyed by shard id."""
    return {shard.id: shard_envelope(shard, envelopes, contract) for shard in plan}


def requested_shard(
    member: Member, arguments: Sequence[str], plan: Sequence[Shard] = SHARDS
) -> Shard:
    """The shard of ``plan`` a member invocation with ``arguments`` collects."""
    workloads = frozenset(
        arguments[index + 1]
        for index, argument in enumerate(arguments)
        if argument == WORKLOAD_OPTION
    )
    return next(
        shard
        for shard in plan
        if shard.member == member and (shard.workloads or frozenset()) == workloads
    )


def identities(**versions: str) -> dict[str, RuntimeStatus]:
    """One available identity per supported minor, its full version overridden
    by a keyword spelling the minor with an underscore."""
    return {
        minor: RuntimeIdentity("CPython", versions.get(minor.replace(".", "_"), f"{minor}.1"), "/p")
        for minor in supported_minors()
    }


def collection_spans(shard_id: str, seconds: float) -> Spans:
    """A collection span over one member span, ``seconds`` long, on a fake clock."""
    elapsed = [0.0]
    wall = datetime(2026, 9, 18, 6, 0, tzinfo=UTC)
    spans = Spans(clock=lambda: elapsed[0], now=lambda: wall + timedelta(seconds=elapsed[0]))
    with (
        spans.span("collection", shard_id, shard=shard_id),
        spans.span("member", "member", member="member"),
    ):
        elapsed[0] += seconds
    return spans


def write_capture(
    root: Path,
    artifact: str,
    shard: Shard,
    side: str,
    request: Request,
    envelope: Document | None,
    *,
    commit: str | None = None,
    pair: str = "pair",
    runtimes: dict[str, RuntimeStatus] | None = None,
    seconds: float = 10.0,
) -> Path:
    """One side of one shard under ``root/artifact``, as a runner would have
    written it for ``request``; the measured commit defaults to the request's
    commit for that side."""
    measured = commit or (request.head_commit if side == HEAD else request.base_commit)
    assert measured is not None
    result = ShardResult(
        shard,
        MemberResult(shard.member, envelope, None if envelope is not None else "exit 1: gone"),
        collection_spans(shard.id, seconds),
        runtimes if runtimes is not None else identities(),
    )
    out = root / artifact / side / shard.id
    write_shard(result, request, side, measured, pair, out)
    return out
