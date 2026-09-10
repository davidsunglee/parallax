"""What write planning costs for what the flush did not hand it.

Two shapes are graded here, and both are the same mistake at different scales: a
structure planning derives whose size comes from something other than the writes
it was given. The first is the model's Entity count, for Entities no write in the
flush names; the second is a Materialized Write Group's resolved-row count, for
rows the group already holds.

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
a per-planner one — a removal that only moves what it costs — is the difference
between the readings taken here.

Four readings of the Entity count, because that cost has four places to hide.
What one key derivation allocates, which is where the dictionaries were built.
What a model-scoped
planner KEEPS when it is built, which is where a cache filled up front would move
them to rather than remove them. What that planner keeps once it has settled a
write against every Entity the model declares, which is where a cache filled one
Entity at a time would show instead. And what one flush allocates over what an
empty flush already allocated, which is where a per-write derivation would sit.

The flush reading is a DIFFERENCE rather than a flat line, and the reason is
named rather than absorbed: dependency ordering builds one topological rank per
Entity on every flush, empty or not, and that structure is not what is graded
here. So the flush reading grades what SETTLING a write adds to a flush that
already paid for ordering, and it is read at an entity count a repeated
measurement of a quadratic ordering stage can afford, while the key derivation —
the seam the index was removed from — is read at a hundred times as many
Entities.

The row reading is the one whose seam is a settled plan rather than a call. A
versioned group's segment holds no strategy, so every row's ADVANCED version
used to be computed up front into a second tuple beside the observed column the
group already carried — retained for the flush's whole life. The strategy now
answers its arithmetic as a value the plan may keep, so the advance is an
addition performed when a row's step is asked for, and what the plan retains
beyond the group's own columns is the same bytes at a hundred times the rows.

Three times over, because a per-row structure is forbidden even transiently and
what a byte reading can see shrinks as the structure's life does. Beside what the
plan KEEPS, the settlement window is read as a high-water mark, which prices a
row-sized structure built and released inside the call. And beside that, what
settling DOES is counted rather than weighed: a loop that builds one wrapper per
row and releases it before building the next leaves the level unmoved, so neither
byte reading can see it, while it cannot avoid instantiating the class and
running the loop. The census counts every class a call bytecode instantiated and
every bytecode instruction executed, naming no class of its own, so an
intermediary introduced under any name — a binding, an adapter, a frame, a tuple
built inline — is counted the round it appears.

The census reads bytecode, so what a C consumer does internally is outside it:
`deque(map(dict, rows), maxlen=0)` builds and drops one mapping per row while
executing no instruction per row. That is outside the census and not outside the
three readings together. A frame, a source, an adapter, or a binding is a class
declared in this repository, and instantiating one runs its own `__init__`, so
no C pipeline builds one without the census counting the instructions that do
it. What a C pipeline can build unseen is a builtin container, and a builtin
container built per row is kept (the retained reading), alive beside its
neighbours (the high-water reading), or read by Python code per row (the
instruction count) — unless it is dropped unread, which is per-row work whose
result nothing observes.

All three are read of both materialized shapes, a versioned group settling into
updates and a temporal one settling into closes, because the prohibition is on
the resolved row rather than on the arm that addresses it.
"""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final, NamedTuple

from _metamodel_support import Declaration, attribute, identity, key, source
from _metamodel_support import instant as timestamp
from memory_instruments import (
    REPEATS,
    Seam,
    Span,
    allocation,
    high_water,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
)

from _support.clock_probes import inert_instant
from _support.planner_probes import TEST_SUBJECT_IDENTITY, observed_buffer
from parallax.core._formation_profile import form_metamodel
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    Metamodel,
    Table,
    TemporalDimension,
)
from parallax.core.predicate import Comparison
from parallax.core.unit_work import (
    BufferItem,
    ChunkedColumnBuilder,
    KeyedWrite,
    MaterializedWriteGroup,
    PlanningRequest,
    PredecessorColumns,
    PredecessorShape,
    PredicateSelection,
    PredicateWrite,
    TemporalColumns,
    VersionColumns,
    WriteAssignment,
    WritePlanner,
    object_key,
    whole,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite, prepare_typed_write
from parallax.snapshot.handle import build_write_planner

FEW: Final = 8
"""The floor every reading below is compared against."""

MANY: Final = 800
"""A hundred times the floor, for the readings whose seam is linear in nothing.

An index over this model would be two dictionaries of eight hundred entries
against two of eight, which is tens of thousands of bytes against hundreds — no
threshold is needed to tell the two readings apart, and none is used.
"""

FEW_ROWS: Final = 300
"""The floor the resolved-row reading is compared against.

Above CPython's small-integer cache, so the plan's own step count — the one
value it keeps that the row count decides — is a freshly allocated integer at
BOTH readings. That is what lets them be compared exactly rather than through a
tolerance that a real per-row structure could hide under.
"""

MANY_ROWS: Final = FEW_ROWS * 100
"""A hundred times :data:`FEW_ROWS`.

An advanced-version tuple over this many rows is thirty thousand integer
references against three hundred, so no threshold is needed to tell the two
readings apart, and none is used.
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


def _versioned_model() -> Metamodel:
    """An accepted model of one Entity carrying an optimistic-lock version.

    One Entity, because the row reading grades a group's own resolved rows and
    nothing about what else the model declares.
    """
    entity = identity("Entity0")
    return form_metamodel(
        source(
            Declaration(
                identity=entity,
                container=Table("entity0"),
                attributes=(
                    key(entity),
                    attribute(entity, "value"),
                    replace(attribute(entity, "version"), optimistic_locking=True),
                ),
            )
        )
    )


def _temporal_model() -> Metamodel:
    """An accepted model of one Entity with a Transaction-Time as-of axis.

    The other arm a Materialized Write Group settles into: its rows close
    against a resolved instant rather than assign an advanced version, and it
    carries the same single Entity for the same reason the versioned model does.
    """
    entity = identity("Entity0")
    return form_metamodel(
        source(
            Declaration(
                identity=entity,
                container=Table("entity0"),
                attributes=(
                    key(entity),
                    attribute(entity, "value"),
                    timestamp(entity, "txStart"),
                    timestamp(entity, "txEnd"),
                ),
                as_of_axes=(
                    AsOfAxisMetadata(
                        TemporalDimension.TRANSACTION_TIME,
                        AttributeIdentity(entity, "txStart"),
                        AttributeIdentity(entity, "txEnd"),
                    ),
                ),
            )
        )
    )


_PREDECESSOR_MEMBERS: Final = ("id", "value", "txStart", "txEnd")


def _temporal_group(model: Metamodel, rows: int) -> MaterializedWriteGroup:
    """A temporal Materialized Write Group of ``rows`` observed predecessors.

    What a materializing terminate buffers: the key columns beside the whole
    predecessor state each close is derived from, all of it aligned storage the
    group already owns.
    """
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    members: dict[str, ChunkedColumnBuilder[object]] = {
        name: ChunkedColumnBuilder() for name in _PREDECESSOR_MEMBERS
    }
    for row in range(rows):
        keys.append(row + 1)
        members["id"].append(row + 1)
        members["value"].append(row)
        members["txStart"].append("2024-01-01T00:00:00+00:00")
        members["txEnd"].append("infinity")
    prepared = prepare_typed_write(
        PredicateWrite(
            "terminate",
            PredicateSelection("Entity0", Comparison("lessThan", "Entity0.value", 1_000_000)),
        ),
        model,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return MaterializedWriteGroup(
        mutation=prepared,
        key_attributes=("id",),
        key_columns=(whole(keys.build()),),
        observations=TemporalColumns(
            predecessors=PredecessorColumns(
                shape=PredecessorShape(attributes=_PREDECESSOR_MEMBERS, value_objects=()),
                attribute_columns=tuple(
                    whole(members[name].build()) for name in _PREDECESSOR_MEMBERS
                ),
                value_object_columns=(),
            )
        ),
    )


def _version_group(model: Metamodel, rows: int) -> MaterializedWriteGroup:
    """A versioned Materialized Write Group of ``rows`` resolved rows.

    Its key and observation columns are the compact aligned storage a
    materializing predicate write buffers, so a plan settled from it reaches
    every per-row value by reference.
    """
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    for row in range(rows):
        keys.append(row + 1)
        versions.append(row + 1)
    prepared = prepare_typed_write(
        PredicateWrite(
            "update",
            PredicateSelection("Entity0", Comparison("lessThan", "Entity0.value", 1_000_000)),
            assignments=(WriteAssignment("Entity0.value", 1),),
        ),
        model,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return MaterializedWriteGroup(
        mutation=prepared,
        key_attributes=("id",),
        key_columns=(whole(keys.build()),),
        observations=VersionColumns(versions=whole(versions.build())),
    )


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


def _planner_having_settled_every_entity(entities: int) -> Seam:
    """One planner that has settled a write against EVERY Entity of a model of
    ``entities``, sampled while the planner is alive and its plan is not.

    The model and the request are built before the window for the same reason
    they are at the flush reading. What the sample can still reach is what the
    planner kept of the writes it settled: the plan it answered is dropped
    unbound, and the collection the sample takes reclaims it.
    """
    model = _model(entities)
    request = PlanningRequest(
        subject_identity=TEST_SUBJECT_IDENTITY,
        transaction_instant=INSTANT,
        concurrency="optimistic",
        buffered_writes=tuple(
            observed_buffer(
                [
                    KeyedWrite("update", f"Entity{index}", ({"id": 1, "value": index},))
                    for index in range(entities)
                ],
                model,
                None,
            )
        ),
    )

    def run(sample: Callable[[], None]) -> None:
        planner = build_write_planner(model)
        planner.finalize(request)
        sample()
        del planner

    return run


class _Settlement(NamedTuple):
    """One materialized shape, ready to settle: the planner and the request.

    Both are built before any window opens, which is where a caller builds them:
    a planner is model-scoped and a Planning Request is the value a unit of work
    hands across the seam.
    """

    planner: WritePlanner
    request: PlanningRequest


def _versioned_settlement(rows: int) -> _Settlement:
    """Settling a versioned group of ``rows`` resolved rows.

    Its key and observation columns are the compact aligned storage a
    materializing predicate write buffers, so a plan settled from it reaches
    every per-row value by reference.
    """
    model = _versioned_model()
    return _Settlement(
        planner=build_write_planner(model),
        request=PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=INSTANT,
            concurrency="optimistic",
            buffered_writes=(_version_group(model, rows),),
        ),
    )


def _temporal_settlement(rows: int) -> _Settlement:
    """Settling a temporal group of ``rows`` observed predecessors.

    Its own Transaction Instant rather than the shared holder, because closing a
    predecessor resolves one — a holder resolved by an earlier settlement would
    put that resolution in one reading and not the other.
    """
    model = _temporal_model()
    return _Settlement(
        planner=build_write_planner(model),
        request=PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=(_temporal_group(model, rows),),
        ),
    )


_MATERIALIZED_SHAPES: Final = (
    ("a versioned group", _versioned_settlement),
    ("a temporal group", _temporal_settlement),
)
"""Both arms a Materialized Write Group settles into, under the same readings.

A resolved row is a resolved row whether its step assigns an advanced version or
closes a predecessor, so a reading taken of one arm says nothing about the other.
"""


def _settled_group_plan(settlement: _Settlement) -> Seam:
    """One ``finalize``, sampled while the plan it answered is alive.

    The model, the planner, the group, and its columns are all built before the
    window, so every byte still reachable at the sample is a byte the PLAN
    keeps: a column the group already owned is reached by reference and weighs
    nothing here, and a second structure sized by the resolved rows weighs
    everything.
    """

    def run(sample: Callable[[], None]) -> None:
        plan = settlement.planner.finalize(settlement.request).plan
        sample()
        del plan

    return run


def _settling_a_group(settlement: _Settlement) -> Span:
    """The same ``finalize`` with the region opened around the call itself.

    Everything the call reads is built before the region opens, and the plan it
    answers is still alive when the region closes, so the roof covers what
    settling ROSE to and not only what it kept: a row-sized structure built and
    dropped inside ``finalize`` — a wrapper array, a materialized row sequence,
    a comprehension over the resolved rows — is invisible to every reading taken
    at a point afterwards and is inside this one.
    """

    def span(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        opened()
        plan = settlement.planner.finalize(settlement.request).plan
        closed()
        del plan

    return span


class _Census(NamedTuple):
    """What a run DID, counted where a byte reading can only weigh what survives.

    ``constructions`` is every class a monitored call bytecode instantiated,
    whatever its name and whichever module defines it, so a wrapper settlement
    does not have yet is counted as readily as one it does. ``instructions`` is
    every bytecode instruction the run executed, which closes the one gap the
    first leaves: a tuple, a mapping, or a slice built inline is an intermediary
    no class call announces, and Python code cannot build one per row without
    executing the instructions that build it. Both readings are of bytecode, and
    what that bounds rather than sees is the module docstring's.
    """

    constructions: int
    instructions: int


_MONITORING_TOOL_IDS: Final = range(6)
"""Every id :mod:`sys.monitoring` admits a tool under."""


def _census_of(settling: Callable[[], Callable[[], None]]) -> _Census:
    """Count what one run of ``settling()`` constructs and executes.

    A run of its own is warmed first, so a module imported or a cache filled on
    first reach is counted in neither reading — and the warmed run settles a
    DIFFERENT planner and request from the counted one, because settlement is
    stateful: warming the run about to be counted would consume its first
    finalization, and per-row work that a first finalization alone performs
    would then land in neither reading. The counting tool takes whichever
    monitoring id is free, because a profiler or a coverage backend may already
    hold one.
    """
    constructions = 0
    instructions = 0
    monitoring = sys.monitoring

    def on_call(_code: object, _offset: int, called: object, _argument: object) -> None:
        nonlocal constructions
        if isinstance(called, type):
            constructions += 1

    def on_instruction(_code: object, _offset: int) -> None:
        nonlocal instructions
        instructions += 1

    settling()()
    run = settling()
    tool = next(
        identifier for identifier in _MONITORING_TOOL_IDS if monitoring.get_tool(identifier) is None
    )
    monitoring.use_tool_id(tool, "settlement census")
    try:
        monitoring.register_callback(tool, monitoring.events.CALL, on_call)
        monitoring.register_callback(tool, monitoring.events.INSTRUCTION, on_instruction)
        monitoring.set_events(tool, monitoring.events.CALL | monitoring.events.INSTRUCTION)
        run()
        monitoring.set_events(tool, 0)
    finally:
        monitoring.free_tool_id(tool)
    return _Census(constructions=constructions, instructions=instructions)


def _settling(
    shape: Callable[[int], _Settlement], rows: int, *, every_step: bool
) -> Callable[[], Callable[[], None]]:
    """A run settling a group of ``rows`` rows, freshly prepared each time it is
    asked for.

    A run rather than a call, and a fresh one per ask, because the census warms
    one run and counts another: preparing the planner and the request outside
    the run keeps building them out of the count, and preparing them again for
    the counted run keeps the warmed settlement's state out of it.
    """

    def settling() -> Callable[[], None]:
        prepared = shape(rows)

        def run() -> None:
            plan = prepared.planner.finalize(prepared.request).plan
            if every_step:
                for step in plan.steps:
                    assert step is not None

        return run

    return settling


@in_a_child_interpreter
def test_a_materialized_groups_plan_keeps_nothing_per_resolved_row() -> None:
    # A group's rows are already compact columns when planning receives them, so
    # settling them adds nothing sized by their number: what the plan keeps is
    # one segment over the facts settled for the whole group, and what each row's
    # step assigns — an advanced version, a closed axis — is derived from the
    # group's own columns when that step is asked for.
    tracemalloc.start()
    try:
        for shape, settlement in _MATERIALIZED_SHAPES:
            few = retained(_settled_group_plan(settlement(FEW_ROWS)))
            many = retained(_settled_group_plan(settlement(MANY_ROWS)))
            # What the sample above cannot see. It is taken after a collection,
            # so a row-sized structure `finalize` builds and drops again is gone
            # from it; the memory contract forbids such a structure "even
            # transiently", so the settlement window is read as a high-water
            # mark too.
            peak_few = high_water(_settling_a_group(settlement(FEW_ROWS)))
            peak_many = high_water(_settling_a_group(settlement(MANY_ROWS)))
            assert few > 0, f"settling {shape} keeps nothing, or nothing is being measured"
            assert many == few, shape
            assert peak_few > 0, f"settling {shape} is free, or nothing is being measured"
            assert peak_many == peak_few, shape
    finally:
        tracemalloc.stop()


@in_a_child_interpreter
def test_settling_a_materialized_group_constructs_nothing_per_resolved_row() -> None:
    # The third reading of the same claim, and the one neither reading above can
    # take: a Python loop that builds one intermediary per row and drops it
    # before building the next keeps the level flat, so it passes both. What it
    # cannot do is construct nothing and execute nothing. In an interpreter of
    # its own because `sys.monitoring` events are installed process-wide and
    # count every instruction the process executes while they are set, so
    # anything else running beside the reading is inside it.
    for shape, settlement in _MATERIALIZED_SHAPES:
        few = _census_of(_settling(settlement, FEW_ROWS, every_step=False))
        many = _census_of(_settling(settlement, MANY_ROWS, every_step=False))
        assert few.constructions > 0, f"settling {shape} constructs nothing at all"
        assert many == few, shape
        # And the census counts what it claims to: asking for every row's step
        # builds that row's own Planned Write, which is where that work belongs.
        on_access = _census_of(_settling(settlement, FEW_ROWS, every_step=True))
        assert on_access.constructions - few.constructions >= FEW_ROWS, shape


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
def test_a_planner_keeps_nothing_per_entity_it_has_settled() -> None:
    # The one shape the two readings above share a blind spot for: a per-Entity
    # structure filled LAZILY, as each Entity is first settled, is empty in a
    # planner that has never flushed and constant across a flush that settles the
    # same target however many Entities the model declares. Settling every Entity
    # of the model once is what makes such a structure visible, and what the
    # planner keeps after doing so is the same bytes for sixteen times as many
    # Entities.
    tracemalloc.start()
    try:
        few = retained(_planner_having_settled_every_entity(FEW))
        many = retained(_planner_having_settled_every_entity(ORDERED_MANY))
    finally:
        tracemalloc.stop()
    assert few > 0, "a planner that has settled a flush is not free, or nothing is measured"
    assert many == few


@in_a_child_interpreter
def test_settling_a_write_adds_nothing_per_entity_to_a_flush() -> None:
    # An empty flush is the control because it runs every stage a flush runs and
    # settles nothing: whatever it pays per Entity is dependency ordering's rank
    # map, which is not what this reading grades. Subtracting it leaves what
    # SETTLING one write costs per Entity, and settlement reads its target through
    # the Metadata the write already carries, so the two grow by the same bytes.
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
