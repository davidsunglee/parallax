"""What write planning costs for what the flush did not hand it.

The shape graded here is a structure planning derives whose size comes from
something other than the writes it was given: the model's Entity count, for
Entities no write in the flush names.

A prepared write carries the exact target Metadata its ingress resolved, and the
model's Inheritance and Temporal facets were compiled when the model was
accepted; the planner and its settlement module hold the model and those facets
by reference. Between them nothing planning needs about a target has to be
searched for — so what the accepted model declares BESIDE the target is not
planning's to pay for, and
planning builds no spelling index — a canonical/bare spelling map or a name-count
dictionary, sized by the model's Entity count — to resolve a spelling no prepared
input carries.

`test_write_planner.py` proves the absence structurally, by failing the flush
that reaches the spelling scan at all. This prices the same claim from the other
side, where a lookup that stopped being a dictionary and became something else
sized the same way would still be caught, and where a per-flush index REPLACED by
a per-planner one — a removal that only moves what it costs — is the difference
between the readings taken here.

Three readings of the Entity count. What one key derivation allocates and what
one flush allocates, empty or settling a write, which are the sites a spelling
index or a dependency graph would be built per call. And what a model-scoped
planner KEEPS when it is built, which is where either would be held instead.
Dependency ordering reads the referential rank the relationship module compiled
with the model, so a flush builds no rank map either.

One reading of the write count, over one fixed model: what a finalized plan
keeps while it is alive, for writes that hold no source. Each settled write it
plans shares the one empty evidence tuple, and nothing of the writes the plan
was handed survives beside it.
"""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import Final

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core._execution._unit_work.write_items import ComposedWrite, KeyedInsert
from parallax.core._formation_profile import form_metamodel
from parallax.core.metamodel import (
    Metamodel,
    Table,
)
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    WritePlanningRequest,
    object_key,
)
from parallax.core.write_plan.plan import SettledWrite
from tests._support.clock_probes import inert_instant, instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer, settled_writes
from tests.unit._corpus_model_support import formed, records
from tests.unit._metamodel_support import Declaration, attribute, identity, key, source
from tests.unit.memory_instruments import (
    REPEATS,
    Seam,
    allocation,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
    survivors,
    warmed,
)

FEW: Final = 8
"""The floor every reading below is compared against."""

MANY: Final = 800
"""A hundred times the floor, for the readings whose seam is linear in nothing.

An index over this model would be two dictionaries of eight hundred entries
against two of eight, which is tens of thousands of bytes against hundreds — no
threshold is needed to tell the two readings apart, and none is used.
"""

SOURCE_FREE_ARMS: Final = (0, 8, 128)
"""Write counts of the source-free readings: empty, small, and larger, over
:data:`SOURCE_FREE_MODEL` alone."""

INSTANT: Final = inert_instant()
"""One unresolved holder for every request below.

Non-temporal settlement never reads the instant, so the holder is shared rather
than re-created per seam, which would put its own allocation inside the window.
"""


SOURCE_FREE_INSTANT: Final = instant_at("2024-01-01T00:00:00+00:00")
"""The instant every source-free temporal insert opens at, shared like
:data:`INSTANT`; the first plan captures it, outside every window."""

SOURCE_FREE_MODEL: Final = formed(records("balance"))
"""The one Transaction-Time-Only model every source-free reading plans against."""


def _model(entities: int) -> Metamodel:
    """An accepted model of ``entities`` independent single-key Entities.

    Independent, so no relationship adds an edge, and the compiled ranks fall
    back to the model's own canonical order.
    """
    declarations: list[Declaration] = []
    for index in range(entities):
        entity = identity(f"Entity{index}")
        declarations.append(
            Declaration(
                identity=entity,
                container=Table(f"entity{index}"),
                attributes=(key(entity), attribute(entity, "value")),
            )
        )
    return form_metamodel(source(*declarations))


def _prepared_writes(model: Metamodel, count: int) -> Sequence[ComposedWrite]:
    return observed_buffer(
        [
            KeyedWriteInstruction("amend", "Entity0", ({"id": row + 1, "value": row},))
            for row in range(count)
        ],
        model,
        None,
    )


def _flush_of(entities: int, writes: int) -> Seam:
    """One ``finalize`` over ``writes`` prepared writes against ``entities``.

    The planner, the buffer, and the request are built before the window, which
    is where a caller builds them: a planner is model-scoped and a Planning
    Request is the value a unit of work hands across the seam, so measuring
    their construction would measure the caller rather than the flush.
    """
    model = _model(entities)
    planner = build_write_planner(model)
    request = WritePlanningRequest(
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=INSTANT,
        concurrency="optimistic",
        composed_writes=tuple(_prepared_writes(model, writes)),
    )

    def run(sample: Callable[[], None]) -> None:
        planner.finalize(request)
        sample()

    return run


def _key_derivation_over(entities: int, *, prepared: bool) -> Seam:
    """One ``object_key`` against a model of ``entities``.

    Both entry points, because the branch that still resolves a spelling is the
    one this reading has to reach as well: a prepared write names its target by
    Metadata and a raw authored one names it by string, and neither may build an
    index over the model to answer with.
    """
    model = _model(entities)
    raw = KeyedWriteInstruction("amend", "Entity0", ({"id": 1, "value": 2},))
    instruction = prepare_typed_write(raw, model) if prepared else raw

    def run(sample: Callable[[], None]) -> None:
        object_key(instruction, model)
        sample()

    return run


def _source_free_inserts(writes: int) -> WritePlanningRequest:
    """A Planning Request buffering ``writes`` Transaction-Time-Only inserts of
    distinct objects of one fixed model.

    An insert holds no source, and a temporal insert neither batches nor shares
    a settled write, so each settles into a settled write of its own that keeps
    no Read Evidence.
    """
    return WritePlanningRequest(
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=SOURCE_FREE_INSTANT,
        concurrency="optimistic",
        composed_writes=tuple(
            observed_buffer(
                [
                    KeyedWriteInstruction(
                        "insert", "Balance", ({"id": row + 1, "acctNum": "A", "value": row},)
                    )
                    for row in range(writes)
                ],
                SOURCE_FREE_MODEL,
                None,
            )
        ),
    )


def _source_free_plan_kept(writes: int) -> Seam:
    """One ``finalize`` over ``writes`` source-free inserts, sampled while the
    plan it answered is still alive.

    The request is built before the window, as :func:`_flush_of`'s is, so what
    the sample reaches is what the plan keeps of its own.
    """
    planner = build_write_planner(SOURCE_FREE_MODEL)
    request = _source_free_inserts(writes)

    def run(sample: Callable[[], None]) -> None:
        plan = planner.finalize(request)
        sample()
        del plan

    return run


def _source_free_plan_handed(writes: int) -> Seam:
    """:func:`_source_free_plan_kept` with the request built inside the window
    and dropped before the sample, so what survives of it is what the plan
    keeps of what it was handed."""
    planner = build_write_planner(SOURCE_FREE_MODEL)

    def run(sample: Callable[[], None]) -> None:
        request = _source_free_inserts(writes)
        plan = planner.finalize(request)
        del request
        sample()
        del plan

    return run


def _planner_over(entities: int) -> Seam:
    """One ``build_write_planner`` against a model of ``entities``, sampled while
    the planner it built is still alive.

    The model is built before the window, so every byte still reachable at the
    sample is a byte the planner's own construction allocated — a facet the
    model already carried is reached by reference and weighs nothing here, and an
    index derived from it weighs everything.
    """
    model = _model(entities)

    def run(sample: Callable[[], None]) -> None:
        planner = build_write_planner(model)
        sample()
        del planner

    return run


"""Both arms a Materialized Write Group settles into, under the same readings.

A resolved row is a resolved row whether its step assigns an advanced version or
closes a predecessor, so a reading taken of one arm says nothing about the other.
A deferred group's plan holds its selected rows only by reference, for the
continuation that settles them.
"""


@in_a_child_interpreter
def test_a_key_derivation_costs_the_same_whatever_else_the_model_declares() -> None:
    # The reading the removed dictionaries would fail outright: they were built
    # per call, so a hundred times the Entities cost a hundred times the entries.
    # Equality rather than a bound, because what the derivation reads now is the
    # target's own family-effective primary key and one row, and neither is sized
    # by anything else the model declares.
    tracemalloc.start()
    try:
        few_kept, few_transient = allocation(_key_derivation_over(FEW, prepared=True))
        many_kept, many_transient = allocation(_key_derivation_over(MANY, prepared=True))
        raw_few = allocation(_key_derivation_over(FEW, prepared=False))[1]
        raw_many = allocation(_key_derivation_over(MANY, prepared=False))[1]
    finally:
        tracemalloc.stop()
    assert few_transient > 0, "a key derivation is not free, or nothing is being measured"
    assert many_transient == few_transient
    assert raw_many == raw_few
    assert few_kept < REPEATS
    assert many_kept < REPEATS


@in_a_child_interpreter
def test_a_model_scoped_planner_keeps_nothing_per_entity() -> None:
    # The contract the reading above cannot make on its own: a per-flush index
    # removed by being MOVED into the planner would leave every flush cheaper and
    # every planner heavier by the same shape. What the planner keeps of an
    # eight-hundred-Entity model is what it keeps of an eight-Entity one, so what
    # it holds is references to the model and its compiled facets, and the
    # strategies wired into it.
    tracemalloc.start()
    try:
        few = retained(_planner_over(FEW))
        many = retained(_planner_over(MANY))
    finally:
        tracemalloc.stop()
    assert few > 0, "a planner is not free, or nothing is being measured"
    assert many == few


@in_a_child_interpreter
def test_a_flush_allocates_nothing_per_entity() -> None:
    # Settlement reads its target through the Metadata the write already
    # carries, and ordering reads each ranked write's compiled rank, so neither
    # an empty flush nor one settling a write grows with the model.
    tracemalloc.start()
    try:
        settled_few = allocation(_flush_of(FEW, 1))
        settled_many = allocation(_flush_of(MANY, 1))
        empty_few = allocation(_flush_of(FEW, 0))[1]
        empty_many = allocation(_flush_of(MANY, 0))[1]
    finally:
        tracemalloc.stop()
    assert empty_few > 0, "an empty flush is free, or nothing is being measured"
    assert empty_many == empty_few
    assert settled_few[1] > empty_few
    assert settled_many[1] == settled_few[1]
    assert settled_few[0] < REPEATS
    assert settled_many[0] < REPEATS


@in_a_child_interpreter
def test_a_live_source_free_plan_keeps_its_settled_writes_and_nothing_it_was_handed() -> None:
    # Every source-free write settles into a settled write of its own, which
    # shares the one empty evidence tuple rather than holding a collection of
    # its own; what the live plan keeps grows with those writes, and neither
    # an admitted write nor its prepared instruction survives beside them.
    planner = build_write_planner(SOURCE_FREE_MODEL)
    planned = {
        writes: settled_writes(planner.finalize(_source_free_inserts(writes)))
        for writes in SOURCE_FREE_ARMS
    }
    tracemalloc.start()
    try:
        kept = [retained(_source_free_plan_kept(writes)) for writes in SOURCE_FREE_ARMS]
        handed = survivors(warmed(_source_free_plan_handed(max(SOURCE_FREE_ARMS))))
    finally:
        tracemalloc.stop()
    shared: tuple[()] = ()
    for writes, settled in planned.items():
        assert len({id(write) for write in settled}) == writes
        assert all(write.source_evidence is shared for write in settled)
    assert kept[0] > 0, "an empty plan is free, or nothing is being measured"
    assert all(fewer < more for fewer, more in pairwise(kept))
    assert sum(isinstance(held, SettledWrite) for held in handed) == max(SOURCE_FREE_ARMS)
    assert not any(isinstance(held, KeyedInsert | PreparedKeyedInstruction) for held in handed)


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
