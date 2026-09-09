"""What write planning costs for Entities no write in the flush names.

A prepared write carries the exact target Metadata its ingress resolved, and the
model's Inheritance Facet was compiled when the model was accepted. Between them
nothing planning needs about a target has to be searched for — so what the
accepted model declares BESIDE the target is not planning's to pay for. Planning
used to pay for it twice over on every call: a canonical/bare spelling map and a
name-count dictionary built per flush and per key derivation, both sized by the
model's Entity count, to resolve a spelling no prepared input carries.

`test_write_planner.py` proves the absence structurally, by failing the flush
that reaches the spelling scan at all. This prices the same claim from the other
side, where a lookup that stopped being a dictionary and became something else
sized the same way would still be caught, and where a per-flush index REPLACED by
a per-planner one — the shape the ticket's memory contract forbids specifically —
is the difference between the two readings taken here.

Three readings, because the cost has three places to hide. What one key
derivation allocates, which is where the dictionaries were built. What a
model-scoped planner KEEPS, which is where a cache would move them to rather than
remove them. And what one flush allocates over what an empty flush already
allocated, which is where a per-write derivation would sit.

The flush reading is a DIFFERENCE rather than a flat line, and the reason is
named rather than absorbed: dependency ordering builds one topological rank per
Entity on every flush, empty or not, and that stage is outside this ticket. So
the flush reading grades what SETTLING a write adds to a flush that already paid
for ordering, and it is read at an entity count a repeated measurement of a
quadratic ordering stage can afford, while the key derivation — the seam the
index was removed from — is read at a hundred times as many Entities.
"""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable, Sequence
from typing import Final

from _metamodel_support import Declaration, attribute, identity, key, source
from memory_instruments import (
    REPEATS,
    Seam,
    allocation,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
)

from _support.clock_probes import inert_instant
from _support.planner_probes import TEST_SUBJECT_IDENTITY, observed_buffer
from parallax.core._formation_profile import form_metamodel
from parallax.core.metamodel import Metamodel, Table
from parallax.core.unit_work import BufferItem, KeyedWrite, PlanningRequest, object_key
from parallax.core.unit_work.instructions import prepare_typed_write
from parallax.snapshot.handle import build_write_planner

FEW: Final = 8
"""The floor every reading below is compared against."""

MANY: Final = 800
"""A hundred times the floor, for the readings whose seam is linear in nothing.

An index over this model would be two dictionaries of eight hundred entries
against two of eight, which is tens of thousands of bytes against hundreds — no
threshold is needed to tell the two readings apart, and none is used.
"""

ORDERED_MANY: Final = 128
"""What the flush readings use instead of :data:`MANY`.

Dependency ordering ranks every Entity against every other, so a flush against
:data:`MANY` costs milliseconds and the instruments run their seam four hundred
times. Sixteen times the floor is enough for a per-Entity structure to be
hundreds of times the constant it would hide behind.
"""

INSTANT: Final = inert_instant()
"""One unresolved holder for every request below.

Non-temporal settlement never reads the instant, so the holder is shared rather
than re-created per seam, which would put its own allocation inside the window.
"""


def _model(entities: int) -> Metamodel:
    """An accepted model of ``entities`` independent single-key Entities.

    Independent, so dependency ordering's rank map is the only structure their
    number can grow: no relationship means no edge, and the ranks fall back to
    the model's own canonical order.
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


def _prepared_writes(model: Metamodel, count: int) -> Sequence[BufferItem]:
    return observed_buffer(
        [KeyedWrite("update", "Entity0", ({"id": row + 1, "value": row},)) for row in range(count)],
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
    request = PlanningRequest(
        subject_identity=TEST_SUBJECT_IDENTITY,
        transaction_instant=INSTANT,
        concurrency="optimistic",
        buffered_writes=tuple(_prepared_writes(model, writes)),
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
    raw = KeyedWrite("update", "Entity0", ({"id": 1, "value": 2},))
    instruction = prepare_typed_write(raw, model) if prepared else raw

    def run(sample: Callable[[], None]) -> None:
        object_key(instruction, model)
        sample()

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
    # it holds is two references and the strategies wired into it.
    tracemalloc.start()
    try:
        few = retained(_planner_over(FEW))
        many = retained(_planner_over(MANY))
    finally:
        tracemalloc.stop()
    assert few > 0, "a planner is not free, or nothing is being measured"
    assert many == few


@in_a_child_interpreter
def test_settling_a_write_adds_nothing_per_entity_to_a_flush() -> None:
    # An empty flush is the control because it runs every stage a flush runs and
    # settles nothing: whatever it pays per Entity is dependency ordering's rank
    # map, which this ticket does not own. Subtracting it leaves what SETTLING
    # one write costs per Entity, and settlement reads its target through the
    # Metadata the write already carries, so the two grow by the same bytes.
    tracemalloc.start()
    try:
        settled_few = allocation(_flush_of(FEW, 1))
        settled_many = allocation(_flush_of(ORDERED_MANY, 1))
        empty_few = allocation(_flush_of(FEW, 0))[1]
        empty_many = allocation(_flush_of(ORDERED_MANY, 0))[1]
    finally:
        tracemalloc.stop()
    assert empty_many - empty_few > 0, "ordering's own growth is the control, and it is missing"
    assert settled_many[1] - settled_few[1] == empty_many - empty_few
    assert settled_few[0] < REPEATS
    assert settled_many[0] < REPEATS


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
