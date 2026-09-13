"""What a prepared read keeps, and what it refuses to keep per row, per Page,
and per execution.

`spec/python.md`'s *Exact-model member layouts* fixes which members a resolved
concrete Entity carries by the accepted Metamodel alone, requires them derived per
exact Entity and shared — "never rebuilt per row, per Page, or per execution" —
and states that retained layout count and size are independent of the number of
Pages materialized. Beside it, *execution-owned view slots* draws the other line:
a query shape belongs to one execution and MUST NOT be cached for the lifetime of
a model. This is the SIZE half of those two requirements measured over the
production materialization path, from ``prepare_model`` through ``compile_read``
and ``bind`` to ``PreparedRead.materialize`` and conversion: what is retained
must not grow with rows, with Pages, or with executions.

**Two axes, one claim each.** The first varies rows through one prepared
selection, one set of compiled reads, and the levels bound from them: nothing
prepared may grow with the rows materialized through it. The second varies whole
executions — a fetch plan, its compiled reads, and a Page, each unreachable
before the next begins — with only the prepared selection held: nothing
model-fixed may grow with Pages or with executions, which is what forbids a
query shape retained PER EXECUTION.

Both axes grade a SIZE, so what they reach is bounded by what varies across the
thing they vary. A holder whose entry count is fixed by the model — one banked
query shape every execution after the first then shares — grows with neither
Pages nor executions nor rows, and is therefore not something a size separates
from state the model legitimately owns. That such a shape is not banked at all is
a structural property of the code that owns it, asserted where that code is, and
outside what any measurement of size can say.

**Preparation is entered whole.** Every arm derives its cataloged model from
``prepare_model``, and the closure is taken over the selection that answers rather
than over the catalog inside it, so the read and write projections, the Entity
Graph Construction, the row codec, and the write planner are all state a reading
can reach. A catalog constructed directly would leave everything else preparation
composed outside the claim.

**Two instruments: one bounded by the arm, one bounded by nothing.** What each
arm holds is read as a closure — every object one prepared structure reaches
without crossing into another, and every reference between them. A closure is a
total of one participant's own state rather than a difference between two sums,
so it answers exactly what the claim asks. Beside it, each axis marks a REGION
and reads what every Python object in the process weighs at each end of it. A
holder older than every arm is no survivor of any of them and no window's
difference contains it, so a process-global or data-keyed cache taking entries
per row or per execution is visible only as a total — and it is visible there
whether or not the collector tracks what it took, which a survivor sample cannot
say.

**A region rather than two arms, because a first-reach cache saturates.** A
process-global cache keyed by what a row holds stops growing once the rows come
back, so two arms compared in one process both read it already full. The region
instead warms over one generated range and then converts a disjoint fixture
range whose keys and authored names and labels have not reached conversion in
this process. An entry taken for those rows lands between the two marks. The
region releases every Page it builds, so what separates the marks is what
something OUTSIDE the region kept.

The disjoint generated ranges bound that claim. Every key and authored string in
the later range is new, as are its composed rows and documents, so a container
taking an entry per row, per key, or per composed value grows between the marks.
The fixture intentionally omits its other declared scalar and nested members;
the instrument therefore claims no coverage of caches keyed by values the
workload does not author. A holder bounded by any fixed value domain grows with
neither rows, Pages, nor executions once full and is outside this size claim.

An ALLOCATOR total remains a report rather than this gate: its byte level is
machine- and interpreter-relative, while this class requires exact equality and
admits no tolerance. The ``tracemalloc`` totals therefore live in the non-gating
``just python-report-snapshot-materialization``. What is gated here instead is
what the heap's own objects report through :func:`sys.getsizeof`, which two
points of one process answer exactly. The neighbouring 64-Page item asserts
allocator bytes because it grades a bounded maximum rather than equality between
two process-wide states.

Both layouts run in one child per axis: the equality is exact per layout, and a
second child would pay for one more interpreter to prove the same thing twice.
"""

from __future__ import annotations

import gc
import sys
from collections.abc import Callable, Sequence
from typing import Final

from parallax.core.db_port import Row
from parallax.core.entity._layout import CatalogedModel
from parallax.snapshot import ModelSelection, prepare_model
from parallax.snapshot.handle._publication import read_projection
from tests.unit._snapshot_materialization_support import (
    LAYOUTS,
    OWNERS,
    Layout,
    batch,
    compiled_levels,
    fetch_plan,
    prepared_levels,
    query,
    rows_per_level,
    workload,
)
from tests.unit.memory_instruments import (
    WARMUP,
    Closure,
    Span,
    closure,
    in_a_child_interpreter,
    serve_one_measurement,
    whole_heap_across,
)

_ONE_ROOT: Final = 1
"""Root objects the smaller row arm materializes, against :data:`OWNERS` in the
larger one — eight rows against sixty-four, over the same five levels."""

_EXECUTIONS: Final = 64
"""Whole executions the larger execution arm runs and discards, against one."""

_UNSEEN: Final = OWNERS
"""The first root after every range the closure readings convert, so its
fixture-generated keys, names, and labels are new to conversion whatever order
the readings run in."""

_EDITION: Final = "snapshot-materialization-scaling"


def _prepared(layout: Layout) -> ModelSelection:
    """``layout``'s whole prepared selection.

    The measured seams enter through this rather than through a bare
    :class:`CatalogedModel`, because everything preparation composed — the read
    and write projections, the exact-model layouts, the Entity Graph
    Construction, the row codec, and the write planner — is state a later
    preparation change could grow per row or per execution, and only what a
    reading can reach can be graded.
    """
    return prepare_model(workload(layout), edition=_EDITION)


def _catalog(selection: ModelSelection) -> CatalogedModel:
    """The cataloged model ``selection``'s read projection resolves against."""
    return read_projection(selection).model


def _boundary(layout: Layout, selection: ModelSelection) -> tuple[object, ...]:
    """What a closure over ``selection`` stops at: the two structures preparation
    was handed rather than composed.

    Both are shared and older than any arm, so a sample crossing into either
    would answer what the process accumulated around the Domain Model rather than
    what this preparation holds.
    """
    return (_catalog(selection).meta, workload(layout))


def _rows(
    layout: Layout, model: CatalogedModel, owners: int, first: int = 0
) -> tuple[tuple[Row, ...], ...]:
    """``owners`` roots' stored rows beginning at root ``first``, built here so no
    measured window or marked region allocates them.

    ``first`` makes a region's rows unseen: :data:`_UNSEEN` starts past every root
    any other reading converts, so its keys and authored strings reach conversion
    first inside the region."""
    meta = model.meta
    plan = fetch_plan(query(layout, meta), meta)
    return rows_per_level(layout, model, plan, compiled_levels(layout, plan, meta), owners, first)


def _root_only(rows: Sequence[Sequence[Row]]) -> tuple[tuple[Row, ...], ...]:
    """``rows`` with every level below the root emptied, which the loop still
    compiles, converts, and fans back as the empty result a child statement
    returning nothing produces.

    The execution axis repeats its whole window sixty-four times, so what it
    converts per execution decides this item's duration outright. What it claims
    is a property of preparation rather than of how much conversion ran beneath
    it, and the row axis is what carries the whole five-level loop.
    """
    return (tuple(rows[0]), *((),) * (len(rows) - 1))


def _execute(layout: Layout, model: CatalogedModel, rows: Sequence[Sequence[Row]]) -> None:
    """One whole execution: its own plan, its own compiled reads, its own
    prepared reads, its own Page, none of which outlives this call."""
    plan = fetch_plan(query(layout, model.meta), model.meta)
    reads = compiled_levels(layout, plan, model.meta)
    batch(model, plan, prepared_levels(model, reads), rows)


def _unseen_rows(layout: Layout) -> Span:
    """One prepared selection and one set of compiled and bound reads, warmed over
    :data:`OWNERS` roots' rows until every cost paid once is paid, and then handed
    the rows of :data:`OWNERS` FURTHER roots inside the marked region.

    Warmed at the region's own size and over its own levels, so the one thing the
    region varies is that its fixture-generated keys, names, and labels are new.
    A container keyed by a row, key, or composed value takes its entries between
    the two marks rather than before them. The fixture-authored omissions stay
    omissions in both ranges. The region's Page is released where it is built,
    which is what leaves the two marks comparable at all."""
    selection = _prepared(layout)
    model = _catalog(selection)
    meta = model.meta
    plan = fetch_plan(query(layout, meta), meta)
    prepared = prepared_levels(model, compiled_levels(layout, plan, meta))
    warm = _rows(layout, model, OWNERS)
    unseen = _rows(layout, model, OWNERS, _UNSEEN)

    def span(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        for _ in range(WARMUP):
            batch(model, plan, prepared, warm)
        opened()
        batch(model, plan, prepared, unseen)
        closed()

    return span


def _unseen_executions(layout: Layout) -> Span:
    """A prepared selection warmed over :data:`OWNERS` roots' executions, and then
    :data:`_EXECUTIONS` whole executions inside the marked region — each with its
    own fetch plan, its own compiled and bound reads, and its own sealed Page,
    none of which outlives it.

    The warm executions run the region's own row count, while the marked region's
    fixture-generated keys, names, and labels are new to conversion. Its first
    execution is where a container keyed by what a row holds takes its entries,
    and the sixty-four together are what an entry banked per execution accrues
    across."""
    selection = _prepared(layout)
    model = _catalog(selection)
    warm = _root_only(_rows(layout, model, OWNERS))
    unseen = _root_only(_rows(layout, model, OWNERS, _UNSEEN))

    def span(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        for _ in range(WARMUP):
            _execute(layout, model, warm)
        opened()
        for _ in range(_EXECUTIONS):
            _execute(layout, model, unseen)
        closed()
        assert selection is not None

    return span


def _settled() -> None:
    """Two collections, because a tuple holding only untracked items is itself
    untracked only after a collection has passed over it — so the tracked half of
    a closure taken before one answers when the collector last ran rather than
    what the structure holds."""
    gc.collect()
    gc.collect()


def _held_after_rows(layout: Layout, owners: int) -> tuple[Closure, Closure]:
    """What the compiled reads and the prepared reads bound from them hold of
    their own, and what the whole prepared selection does, once ``owners`` roots
    have been materialized through them."""
    selection = _prepared(layout)
    model = _catalog(selection)
    meta = model.meta
    plan = fetch_plan(query(layout, meta), meta)
    reads = compiled_levels(layout, plan, meta)
    prepared = prepared_levels(model, reads)
    batch(model, plan, prepared, _rows(layout, model, owners))
    _settled()
    return closure((reads, prepared), (meta, selection, model, plan)), closure(
        selection, _boundary(layout, selection)
    )


def _held_after_executions(layout: Layout, executions: int) -> Closure:
    """What the prepared selection holds once ``executions`` whole executions —
    each with its own fetch plan, its own compiled and bound reads, and its own
    sealed Page — have resolved through it and been discarded."""
    selection = _prepared(layout)
    model = _catalog(selection)
    rows = _root_only(_rows(layout, model, _ONE_ROOT))
    for _ in range(executions):
        _execute(layout, model, rows)
    _settled()
    return closure(selection, _boundary(layout, selection))


def _region_added_nothing(span: Span, where: str) -> None:
    """That nothing in the process holds MORE where ``span``'s region closes than
    where it opened — in any container anywhere, whether the region reaches it or
    not, counted as objects, as the references among them, and as what they and
    everything untracked they reach weigh.

    A reading across ONE region rather than between two arms catches a first-reach
    cache that would be full in both arms. The region uses fixture-generated keys,
    names, and labels this process has not converted, so entries taken per row,
    key, or composed value land between the marks. A holder bounded by the model
    or by any fixed value domain grows along none of the graded axes once full.

    All three numbers gate rather than the weight alone: a container banking
    untracked keys adds no object at all and moves the reference count by one for
    every entry it takes.

    One-sided, because the claim is one-sided. A FALL means the process released
    something it held before the region opened — what a bounded container reaching
    its own size does — and no requirement here forbids that, so gating it would
    fail this item for a reading it does not make. There is no threshold in either
    direction: one entry taken anywhere fails the comparison.
    """
    opened, closed = whole_heap_across(span)
    assert closed.objects <= opened.objects, (where, opened, closed)
    assert closed.references <= opened.references, (where, opened, closed)
    assert closed.held <= opened.held, (where, opened, closed)


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_row_and_after_many() -> None:
    # What preparation holds is fixed by the model's exact Entity layouts and by
    # the compiled reads it bound its levels from: eight times the rows through
    # one prepared read must leave the prepared side holding the same objects
    # through the same references, and eight roots' worth of rows this process
    # has never decoded must leave nothing anywhere in it holding more than
    # before they arrived. A per-row shape, dispatch table, or classified-key set
    # attached to either would move the closure, and a per-row entry banked in a
    # container neither of them reaches — keyed by what the row holds, so it
    # never grows again once the same rows come back — would move the region.
    for layout in LAYOUTS:
        one_reads, one_prepared = _held_after_rows(layout, _ONE_ROOT)
        many_reads, many_prepared = _held_after_rows(layout, OWNERS)
        assert one_reads.tracked > 0 and one_reads.references > 0, layout
        assert one_reads == many_reads, layout
        assert one_prepared == many_prepared, layout
    for layout in LAYOUTS:
        _region_added_nothing(_unseen_rows(layout), layout)


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_execution_and_after_sixty_four() -> None:
    # The other half: what preparation keeps is independent of the number of
    # Pages materialized and of the executions that materialized them. Sixty-four
    # whole executions — each planning, compiling, binding, converting, and
    # sealing a Page of its own — must leave the selection they were all
    # resolved through holding what one execution left it holding, and must leave
    # nothing anywhere in the process holding more than before the first of them
    # opened. A query shape
    # retained per execution is exactly what would move the closure — one banked
    # once for the model and shared by every execution after it leaves both arms
    # holding one, so a size equality answers nothing about it — and a
    # process-global cache keyed by row or query primitives, which no prepared
    # structure reaches at all and whose entries the collector need not track, is
    # what the region beside it is marked for.
    for layout in LAYOUTS:
        once = _held_after_executions(layout, 1)
        often = _held_after_executions(layout, _EXECUTIONS)
        assert once.tracked > 0 and once.references > 0, layout
        assert once == often, layout
    for layout in LAYOUTS:
        _region_added_nothing(_unseen_executions(layout), layout)


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
