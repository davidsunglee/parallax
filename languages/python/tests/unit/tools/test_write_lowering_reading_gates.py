"""The memory gates over the structural write windows, and what they can see.

`spec/memory-gates.yaml` holds one blocking ceiling per retained checkpoint and
per high-water mark of every keyed-write, predicate-acquisition, and
model-preparation case, derived from the retained capture the file names as its
basis. Each family below reads its cases through the same child the report
measures with —
:func:`write_lowering_reading.measure`, the identical windows, roots, and
warm-ups — and grades the retained and transient readings against their gates.
The acquisition family additionally grades its scaling domain: the per-row
readings must not grow with the row count, since the resolving read's planning
is a fixed cost the rows amortize and nothing production keeps is sized by rows
squared.

Beside the gates, seeded regressions prove what each one detects. A retained
duplication is seeded at the preparation seam as a per-instruction registry
holding a detached copy of every prepared row; a peak-increasing copy is seeded
at the serialization seam as a complete mutable copy of every document bind held
across the driver dump; the acquisition scaling seeds are a resolving port that
keeps every row it answered and one that keeps a key tuple per row, sized by the
row count. Every seed is a monkeypatch inside the child and ships nowhere.

What the gates cannot see is pinned as well: a duplicate traversal that
allocates and frees inside the window moves neither the checkpoint nor the
high-water mark, so it stays within every gate; only the pass observations and
the advisory timing reflect it, and neither gates.

Timing is never asserted here. Elapsed samples are taken because the reading
child takes them; what a seed does to them is stated in the evidence README as
an advisory sensitivity, not graded.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from itertools import pairwise
from statistics import median
from typing import Any, Final, cast

import pytest

import write_lowering_reading
from parallax.conformance.budget import MemoryGates
from parallax.core.base import detach_json_container
from parallax.core.db_port import JsonDocument
from tests.unit import _memory_gate_support as gate_support
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _write_lowering_support as lowering_support
from tests.unit.memory_instruments import in_a_child_interpreter, serve_one_measurement

WARMUPS: Final = 1
MEASURED: Final = 3
"""The sampling a gate reading takes. The retained checkpoint is one sample after
the child's own two hundred warm-ups whatever these say, and the high-water mark
is exact per run, so three measured runs settle a median; the report's nine are
for timing, which nothing here grades."""

RETAINED: Final = "retainedBytes"
TRANSIENT: Final = "transientBytes"
GATED_CELLS: Final = (RETAINED, TRANSIENT)

DUPLICATED_CASES: Final = (
    "txtime.opening.columns.typed",
    "txtime.changed.columns.wire",
    "txtime.changed.document.wire",
    "bitemporal.interior.document.wire",
)
"""Where the retained-duplication seed is proved to trip. The seed adds one
prepared row per row, which is 17% to 35% of a categorical checkpoint against a 10%
headroom: the smallest Typed checkpoint and the three Wire successors, whose
checkpoints are the largest of the categorical cases."""

COPIED_CASES: Final = (
    "geometry.width-64.document.typed",
    "geometry.many-32.columns.typed",
    "ancestor.width-64.document.typed",
)
"""Where the peak-copy seed is proved to trip: the cases whose document binds are
widest, so that :data:`BIND_COPIES` complete copies of them exceed the headroom."""

BIND_COPIES: Final = 1
"""How many complete mutable copies of each document bind the peak seed holds
across the driver dump. One copy is what the immutable-serialization bridge
removed, and on the widest cases it is 19% to 23% of the high-water mark against a
10% headroom."""

TRAVERSED_CASE: Final = "txtime.changed.document.wire"
"""The changed Relational Document successor, whose successor patches are the
pass observation a duplicate lowering doubles."""


class _Reading:
    """One case's gated readings and its pass observations."""

    __slots__ = ("calls", "values")

    def __init__(self, workload: str) -> None:
        reading = write_lowering_reading.measure(workload, warmups=WARMUPS, measured=MEASURED)
        samples = cast("Mapping[str, Sequence[float]]", reading["samples"])
        self.values: dict[str, float] = {cell: median(samples[cell]) for cell in GATED_CELLS}
        self.calls: Mapping[str, float] = cast("Mapping[str, float]", reading["calls"])


def _within_gates(owner: gate_support.GateOwner) -> dict[str, _Reading]:
    """Read every workload the owner claims and grade each against its gates and
    the owner's scaling domains; answer the readings for a seed to compare with."""
    gates = MemoryGates.load()
    readings = {workload: _Reading(workload) for workload in owner.workloads(gates)}
    for workload, reading in readings.items():
        for gate in gates.workload_gates(owner.subject, workload):
            assert gate.within(reading.values[gate.cell]), (
                workload,
                gate.cell,
                reading.values[gate.cell],
                gate.max_bytes,
            )
    for domain in owner.scaling(gates):
        for cell in domain.non_increasing:
            per_unit = [readings[workload].values[cell] for workload in domain.ordered]
            assert all(later <= earlier for earlier, later in pairwise(per_unit)), (
                domain.name,
                cell,
                per_unit,
            )
    return readings


def _outside(workload: str, cell: str, reading: _Reading) -> bool:
    gate = MemoryGates.load().gate(gate_support.WRITE_SUBJECT, workload, cell)
    return not gate.within(reading.values[cell])


class _Registry:
    """The holder a seeded regression keeps its duplicates in: what a
    per-instruction registry, a retained provider batch, or an eager per-row
    structure would own. It accumulates, as a retained regression does — a
    checkpoint counts what the sampled run added to it, and a holder that merely
    replaced its previous entry would show no growth at all."""

    __slots__ = ("kept",)

    def __init__(self) -> None:
        self.kept: list[object] = []

    def keep(self, value: object) -> None:
        self.kept.append(value)

    def clear(self) -> None:
        self.kept.clear()


_REGISTRY: Final = _Registry()


def _duplicating(prepare: Callable[..., Any]) -> Callable[..., Any]:
    def prepared(*args: object, **kwargs: object) -> Any:
        result = prepare(*args, **kwargs)
        _REGISTRY.keep(tuple(detach_json_container(row) for row in result.rows))
        return result

    return prepared


def _forming_twice(form: Callable[..., Any]) -> Callable[..., Any]:
    def formed(*args: object, **kwargs: object) -> Any:
        _REGISTRY.keep(form(*args, **kwargs))
        return form(*args, **kwargs)

    return formed


def _copying_binds(serialize: Callable[..., Any]) -> Callable[..., Any]:
    def serialized(statement: Any) -> Any:
        copies = [
            detach_json_container(bind.value)
            for _ in range(BIND_COPIES)
            for bind in statement.binds
            if isinstance(bind, JsonDocument)
        ]
        result = serialize(statement)
        del copies
        return result

    return serialized


def _keeping_rows(project: Callable[..., Any]) -> Callable[..., Any]:
    def projected(*args: object, **kwargs: object) -> Any:
        rows = project(*args, **kwargs)
        _REGISTRY.keep(rows)
        return rows

    return projected


def _keeping_keys_per_row(project: Callable[..., Any]) -> Callable[..., Any]:
    def projected(*args: object, **kwargs: object) -> Any:
        rows = project(*args, **kwargs)
        _REGISTRY.keep([tuple(range(len(rows))) for _ in rows])
        return rows

    return projected


def _lowering_twice(stream: Callable[..., Iterator[Any]]) -> Callable[..., Iterator[Any]]:
    def streamed(*args: object, **kwargs: object) -> Iterator[Any]:
        yield from stream(*args, **kwargs)
        yield from stream(*args, **kwargs)

    return streamed


@in_a_child_interpreter
def test_the_categorical_keyed_writes_stay_within_their_memory_gates() -> None:
    _within_gates(
        gate_support.owner_of(test_the_categorical_keyed_writes_stay_within_their_memory_gates)
    )


@in_a_child_interpreter
def test_the_geometry_inserts_stay_within_their_memory_gates() -> None:
    _within_gates(gate_support.owner_of(test_the_geometry_inserts_stay_within_their_memory_gates))


@in_a_child_interpreter
def test_the_changed_ancestor_successors_stay_within_their_memory_gates() -> None:
    _within_gates(
        gate_support.owner_of(test_the_changed_ancestor_successors_stay_within_their_memory_gates)
    )


@in_a_child_interpreter
def test_predicate_acquisition_stays_within_its_gates_and_amortizes_over_rows() -> None:
    _within_gates(
        gate_support.owner_of(
            test_predicate_acquisition_stays_within_its_gates_and_amortizes_over_rows
        )
    )


@in_a_child_interpreter
def test_the_prepared_model_stays_within_its_memory_gates() -> None:
    _within_gates(gate_support.owner_of(test_the_prepared_model_stays_within_its_memory_gates))


@in_a_child_interpreter
def test_a_seeded_retained_duplicate_of_every_prepared_row_trips_the_retained_gate() -> None:
    # A per-instruction registry holding a detached copy of each prepared row is
    # the regression class preparation used to pay and the unification removed:
    # a second tree of the authored value alive at the settled checkpoint. It
    # must move the checkpoint past its gate on every case it is proved on; the
    # high-water mark it also raises is not what this seed is proved on.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            lowering_support,
            "prepare_typed_write",
            _duplicating(lowering_support.prepare_typed_write),
        )
        patched.setattr(
            lowering_support,
            "prepare_wire_write",
            _duplicating(lowering_support.prepare_wire_write),
        )
        for workload in DUPLICATED_CASES:
            assert _outside(workload, RETAINED, _Reading(workload)), workload
    _REGISTRY.clear()


@in_a_child_interpreter
def test_a_seeded_second_formed_model_trips_the_model_gate() -> None:
    # Structural retention is gated as one checkpoint over the whole prepared
    # model, and formation is most of it: the accepted metadata, its bindings,
    # the effective selections, and the storage residency. A second formation
    # retained beside the first — what a duplicate accepted model, a second set
    # of selections, or a copied residency view amounts to at the limit —
    # doubles the checkpoint and must trip.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            write_lowering_reading,
            "DomainModel",
            _forming_twice(write_lowering_reading.DomainModel),
        )
        assert _outside(
            write_lowering_reading.MODEL_CASE, RETAINED, _Reading(write_lowering_reading.MODEL_CASE)
        )
    _REGISTRY.clear()


@in_a_child_interpreter
def test_a_seeded_mutable_copy_of_every_document_bind_trips_the_transient_gate() -> None:
    # A complete mutable copy of each document bind held across the driver dump
    # is the preliminary tree the immutable-serialization bridge exists to avoid.
    # It leaves the checkpoint untouched — the copies are gone before any sample
    # — and raises the high-water mark by the documents' own size times the
    # copies held, which on the wide and Many-heavy cases exceeds the headroom
    # above the reading.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(lowering_support, "serialize", _copying_binds(lowering_support.serialize))
        for workload in COPIED_CASES:
            reading = _Reading(workload)
            assert _outside(workload, TRANSIENT, reading), workload
            assert not _outside(workload, RETAINED, reading), workload


@in_a_child_interpreter
def test_seeded_per_row_retention_trips_the_acquisition_gates_and_their_amortization() -> None:
    # Two scaling regressions at the resolving read. A port that keeps every row
    # it answered adds one row's worth per resolved row, which the per-row gates
    # see at every level. A structure sized by the row count and kept per row
    # grows with rows squared: per row it is small at eight rows and large at a
    # hundred and twenty-eight, so the per-row readings stop falling with the
    # row count, which is the amortization the scaling domain requires.
    levels = acquisition_support.CASES
    domain_columns = [case.name for case in levels if case.layout == "columns"]
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            acquisition_support, "projected_rows", _keeping_rows(acquisition_support.projected_rows)
        )
        for workload in ("acquisition.rows-32.columns", "acquisition.rows-128.document"):
            assert _outside(workload, RETAINED, _Reading(workload)), workload
    _REGISTRY.clear()
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            acquisition_support,
            "projected_rows",
            _keeping_keys_per_row(acquisition_support.projected_rows),
        )
        per_row = [_Reading(workload).values[RETAINED] for workload in domain_columns]
        assert not all(later <= earlier for earlier, later in pairwise(per_row)), per_row
        assert _outside(domain_columns[-1], RETAINED, _Reading(domain_columns[-1]))
    _REGISTRY.clear()


@in_a_child_interpreter
def test_a_duplicate_lowering_traversal_stays_within_every_gate_and_doubles_its_passes() -> None:
    # A second lowering of the settled plan allocates and frees everything the
    # first did, inside the window and before any sample: the checkpoint is
    # taken before lowering and the high-water mark is a maximum, so neither
    # gate moves. What does move is the pass observation — the successor patches
    # per row double — and the elapsed time, both of which the report carries as
    # advisories and nothing gates. That is the blind spot the evidence README
    # states, pinned: the seeded memory readings are graded against their gates,
    # and the pass observation, exact per run, relative to the unseeded reading,
    # never against a production count. The retained checkpoint is one sample
    # per reading, so no two readings are compared within the noise allowance.
    unseeded = _Reading(TRAVERSED_CASE)
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            lowering_support, "stream_lowered", _lowering_twice(lowering_support.stream_lowered)
        )
        seeded = _Reading(TRAVERSED_CASE)
    assert not _outside(TRAVERSED_CASE, RETAINED, seeded)
    assert not _outside(TRAVERSED_CASE, TRANSIENT, seeded)
    assert seeded.calls["applyPatches"] == 2 * unseeded.calls["applyPatches"]


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
