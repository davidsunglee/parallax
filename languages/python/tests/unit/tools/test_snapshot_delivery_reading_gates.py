"""The memory gates over the structural read windows, and what they can see.

`spec/memory-gates.yaml` holds one blocking ceiling per retained page and per
high-water mark of every provider-free geometry read, under both layouts, and
per retained entry and high-water mark of every cold read-plan compilation,
derived from the retained capture the file names as its basis. Each family
below reads its levels through the same child the report measures with — the
geometry and plan readings of :mod:`snapshot_delivery_reading`, the identical
port, roots, cache capacity, and warm-ups — and grades the peak and retained
readings against their gates.

Beside the gates, seeded regressions prove what each one detects. A retained
duplication is seeded at the positional builder as a reduced dictionary kept
beside every positional row, which is the intermediate tree direct decoding
removed; a peak-increasing copy is seeded at the provider port as a detached
copy of the rows it last answered, alive while they are materialized and
replaced on the next statement, so it raises the high-water mark and leaves the
retained page alone; a second plan cache compiling every plan again is seeded at
the cold-plan window. Every seed is a monkeypatch inside the child and ships
nowhere.

Timing is never asserted here, and no elapsed reading is taken.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from typing import Any, Final

import pytest

from parallax.conformance.budget import MemoryGates
from parallax.conformance.workloads import plan_levels
from parallax.core.base import detach_json_container
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import MemberShape
from parallax.snapshot.handle._read_plan import DEFAULT_READ_PLAN_CACHE_CAPACITY, ReadPlanCache
from parallax.snapshot.materialize import _prepared as prepared_reads
from parallax.snapshot.materialize._convert import build_positional_object
from snapshot_delivery_reading import (
    PLAN_EDITION,
    ColdPlan,
    _geometry,  # pyright: ignore[reportPrivateUsage] - the geometry reading is what the gate grades
    _plan,  # pyright: ignore[reportPrivateUsage] - the plan reading is what the gate grades
    geometry_address,
    plan_address,
)
from tests.unit import _memory_gate_support as gate_support
from tests.unit import _structural_geometry_support as geometry_support
from tests.unit.memory_instruments import in_a_child_interpreter, serve_one_measurement

WARMUPS: Final = 1
MEASURED: Final = 3
"""The sampling a gate reading takes: a retained reading is one checkpoint after
the child's own warm-ups whatever these say, and a peak is one high-water mark
after these warm-ups; neither is a timing sample."""

DUPLICATED_READS: Final = ("read-depth-1", "read-sparse-64", "read-many-32")
"""Where the reduced-tree seed is proved to trip: the shallow baseline, the
sparse wide level whose declared width the seed's dictionaries carry in full,
and the widest Many."""

COPIED_READS: Final = ("read-depth-1", "read-width-64")
"""Where the port-copy seed is proved to trip: the shallow baseline and the
level whose rows are widest."""


def _read(workload: str, cell: str) -> float:
    """One gated reading at ``workload.cell``, through the reading the report takes."""
    geometry = geometry_address(workload, cell)
    if geometry is not None:
        level, layout, metric = geometry
        value, _unit, _samples = _geometry(
            level, layout, metric, warmups=WARMUPS, measured=MEASURED
        )
        return value
    plan = plan_address(workload, cell)
    assert plan is not None, (workload, cell)
    level, layout, metric = plan
    value, _unit, _samples = _plan(level, layout, metric, warmups=WARMUPS, measured=MEASURED)
    return value


def _within_gates(owner: gate_support.GateOwner) -> None:
    gates = MemoryGates.load()
    for gate in owner.gates(gates):
        value = _read(gate.workload, gate.cell)
        assert gate.within(value), (gate.workload, gate.cell, value, gate.max_bytes)


def _outside(workload: str, cell: str) -> bool:
    gate = MemoryGates.load().gate(gate_support.SNAPSHOT_SUBJECT, workload, cell)
    return not gate.within(_read(workload, cell))


class _Registry:
    """The holder a seeded regression keeps its duplicates in. ``kept``
    accumulates, as a retained regression does, so a checkpoint counts what the
    sampled run added; ``latest`` is replaced per statement, so a peak counts
    the copy alive during one materialization and a checkpoint sees no growth."""

    __slots__ = ("kept", "latest")

    def __init__(self) -> None:
        self.kept: list[object] = []
        self.latest: object = None

    def clear(self) -> None:
        self.kept.clear()
        self.latest = None


_REGISTRY: Final = _Registry()


def _keeping_a_reduced_tree(
    build: Callable[[MemberShape, Iterable[object]], tuple[object, ...]],
) -> Callable[[MemberShape, Iterable[object]], tuple[object, ...]]:
    def built(shape: MemberShape, values: Iterable[object]) -> tuple[object, ...]:
        row = build(shape, values)
        _REGISTRY.kept.append(
            {member.name: value for member, value in zip(shape.members, row, strict=True)}
        )
        return row

    return built


def _copying_answered_rows(project: Callable[..., Any]) -> Callable[..., Any]:
    def projected(*args: object, **kwargs: object) -> Any:
        rows = project(*args, **kwargs)
        _REGISTRY.latest = detach_json_container(rows)
        return rows

    return projected


def _planning_into_a_second_cache(plan: Callable[[ColdPlan], Any]) -> Callable[[ColdPlan], Any]:
    def planned(prepared: ColdPlan) -> Any:
        result = plan(prepared)
        spare = ReadPlanCache(DEFAULT_READ_PLAN_CACHE_CAPACITY)
        spare.plan(
            edition=PLAN_EDITION,
            model=prepared.model,
            dialect=POSTGRES,
            query=prepared.query,
            result_form="instance",
            preference=None,
        )
        _REGISTRY.kept.append(spare)
        return result

    return planned


@in_a_child_interpreter
def test_the_depth_reads_stay_within_their_memory_gates() -> None:
    _within_gates(gate_support.owner_of(test_the_depth_reads_stay_within_their_memory_gates))


@in_a_child_interpreter
def test_the_many_reads_stay_within_their_memory_gates() -> None:
    _within_gates(gate_support.owner_of(test_the_many_reads_stay_within_their_memory_gates))


@in_a_child_interpreter
def test_the_width_and_sparse_reads_stay_within_their_memory_gates() -> None:
    _within_gates(
        gate_support.owner_of(test_the_width_and_sparse_reads_stay_within_their_memory_gates)
    )


@in_a_child_interpreter
def test_the_cold_read_plans_stay_within_their_memory_gates() -> None:
    _within_gates(gate_support.owner_of(test_the_cold_read_plans_stay_within_their_memory_gates))


@in_a_child_interpreter
def test_a_seeded_reduced_tree_beside_every_positional_row_trips_the_retained_gate() -> None:
    # A reduced dictionary kept beside each positional row is the intermediate
    # tree the direct positional decoding removed, retained. It grows the
    # delivered page by one name-keyed mapping per occurrence — every declared
    # position of it, populated or not — so the sparse wide level pays its full
    # declared width, and every level it is proved on must leave its retained
    # gate behind under both layouts.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            prepared_reads,
            "build_positional_object",
            _keeping_a_reduced_tree(build_positional_object),
        )
        for workload in DUPLICATED_READS:
            for layout in geometry_support.LAYOUTS:
                assert _outside(workload, f"{layout}.retainedKiB"), (workload, layout)
    _REGISTRY.clear()


@in_a_child_interpreter
def test_a_seeded_copy_of_the_answered_rows_trips_the_peak_gate_and_not_the_retained() -> None:
    # A provider port that holds a detached copy of the rows it last answered
    # keeps that copy alive while production materializes them, so the high-water
    # mark rises by the rows' own size; the next statement replaces it, so the
    # retained page is unmoved. That is the separation the two gates make —
    # peak coexistence beside retained reachability — proved on the shallow
    # baseline and on the widest rows.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            geometry_support,
            "projected_rows",
            _copying_answered_rows(geometry_support.projected_rows),
        )
        for workload in COPIED_READS:
            for layout in geometry_support.LAYOUTS:
                assert _outside(workload, f"{layout}.peakKiB"), (workload, layout)
                assert not _outside(workload, f"{layout}.retainedKiB"), (workload, layout)
    _REGISTRY.clear()


@in_a_child_interpreter
def test_a_seeded_second_plan_cache_trips_the_cold_plan_retained_gate() -> None:
    # A second cache compiling every plan again is a whole compiled plan retained
    # beside the one production keeps: the cold checkpoint doubles and must trip
    # at every level under both layouts.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(ColdPlan, "plan", _planning_into_a_second_cache(ColdPlan.plan))
        for level in plan_levels():
            for layout in geometry_support.LAYOUTS:
                assert _outside(f"plan-{level.id}", f"{layout}.retainedKiB"), (level.id, layout)
    _REGISTRY.clear()


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
