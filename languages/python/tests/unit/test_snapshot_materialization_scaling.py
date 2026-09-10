"""What a prepared read keeps, and what it refuses to keep per row, per graph,
and per execution.

`spec/python.md`'s *Exact-model member layouts* fixes which members a resolved
concrete Entity carries by the accepted Metamodel alone, requires them derived per
exact Entity and shared — "never rebuilt per row, per graph, or per execution" —
and states that retained layout count and size are independent of the number of
graphs materialized. Beside it, *execution-owned view slots* draws the other line:
a query shape belongs to one execution and MUST NOT be cached for the lifetime of
a model. This is those two requirements measured over the production
materialization path, from ``prepare_model`` through ``compile_read`` to
``CompiledRead.materialize_row`` and conversion.

**Two axes, one claim each.** The first varies rows through one prepared selection
and one set of compiled reads: nothing prepared may grow with the rows
materialized through it. The second varies whole executions — a fetch plan, its
compiled reads, and a graph, each unreachable before the next begins — with only
the prepared selection held: nothing model-fixed may grow with graphs or with
executions, which is also what states that no query shape was cached for the
model's lifetime.

**Preparation is entered whole.** Every arm derives its cataloged model from
``prepare_model``, and the closure is taken over the selection that answers rather
than over the catalog inside it, so the read and write projections, the Entity
Graph Construction, the row codec, and the write planner are all state a reading
can reach. A catalog constructed directly would leave everything else preparation
composed outside the claim.

**Two instruments: one bounded by the arm, one bounded by nothing.** What each
arm holds is read as a closure — every object one prepared structure reaches
without crossing into another, and every reference between them — and as what the
whole process's Python objects weigh at the arm's sample point. A closure is a
total of one participant's own state rather than a difference between two sums,
so it answers exactly what the claim asks; the whole-process total answers the
other half, which is a container the arm does not reach at all. A holder older
than every arm is no survivor of any of them and no window's difference contains
it, so a process-global or data-keyed cache taking entries per row or per
execution is visible only as a total — and it is visible there whether or not the
collector tracks what it took, which a survivor sample cannot say.

An ALLOCATOR reading cannot be the gate here, and the reason is a measurement
rather than a preference. This workload declares every Neutral Type, so its
conforming path runs the canonical Wire codec's ``Timestamp`` leg, and the
interpreter's own ``datetime`` formatting leaves a slowly saturating residue
behind it: two runs of one identical seam read four hundred bytes apart on a
forty-kilobyte window, in either direction, after eight hundred warm-up batches.
An exact equality over that window would be a coin toss, and a tolerance is not
what this class asserts. The ``tracemalloc`` totals therefore live where a
machine-relative number belongs — the non-gating
``just python-report-snapshot-materialization``. What is gated here instead is
what the heap's own objects report through :func:`sys.getsizeof`, which no
allocator residue is inside and which two arms of one process answer exactly. The
neighbouring 64-graph item still asserts allocator bytes because its workload
declares four Neutral Types and reaches none of that codec leg.

Both layouts run in one child per axis: the equality is exact per layout, and a
second child would pay for one more interpreter to prove the same thing twice.
"""

from __future__ import annotations

import gc
import sys
from collections.abc import Callable, Sequence
from typing import Final

from _snapshot_materialization_support import (
    LAYOUTS,
    OWNERS,
    Layout,
    batch,
    compiled_levels,
    fetch_plan,
    query,
    rows_per_level,
    workload,
)
from memory_instruments import (
    Closure,
    Seam,
    closure,
    in_a_child_interpreter,
    serve_one_measurement,
    whole_heap,
)

from parallax.core.db_port import Row
from parallax.core.entity._layout import CatalogedModel
from parallax.snapshot import ModelSelection, prepare_model
from parallax.snapshot.handle._publication import read_projection

_ONE_ROOT: Final = 1
"""Root objects the smaller row arm materializes, against :data:`OWNERS` in the
larger one — eight rows against sixty-four, over the same five levels."""

_EXECUTIONS: Final = 64
"""Whole executions the larger execution arm runs and discards, against one."""

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


def _rows(model: CatalogedModel, owners: int) -> tuple[tuple[Row, ...], ...]:
    """One arm's stored rows, built here so no measured window allocates them."""
    meta = model.meta
    plan = fetch_plan(query(meta), meta)
    return rows_per_level(model, plan, compiled_levels(plan, meta), owners)


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


def _execute(model: CatalogedModel, rows: Sequence[Sequence[Row]]) -> None:
    """One whole execution: its own plan, its own compiled reads, its own graph,
    none of which outlives this call."""
    plan = fetch_plan(query(model.meta), model.meta)
    batch(model, plan, compiled_levels(plan, model.meta), rows)


def _row_seam(layout: Layout, owners: int) -> Seam:
    """One prepared selection and one set of compiled reads derived inside the
    window, ``owners`` roots' worth of rows materialized through them, and only
    the prepared state reachable at the sample."""
    rows = _rows(_catalog(_prepared(layout)), owners)

    def run(sample: Callable[[], None]) -> None:
        selection = _prepared(layout)
        model = _catalog(selection)
        meta = model.meta
        plan = fetch_plan(query(meta), meta)
        reads = compiled_levels(plan, meta)
        batch(model, plan, reads, rows)
        sample()
        assert reads is not None

    return run


def _execution_seam(layout: Layout, executions: int) -> Seam:
    """A prepared selection derived inside the window, ``executions`` whole
    executions run and discarded against it, and only that selection reachable at
    the sample."""
    rows = _root_only(_rows(_catalog(_prepared(layout)), _ONE_ROOT))

    def run(sample: Callable[[], None]) -> None:
        selection = _prepared(layout)
        for _ in range(executions):
            _execute(_catalog(selection), rows)
        sample()
        assert selection is not None

    return run


def _settled() -> None:
    """Two collections, because a tuple holding only untracked items is itself
    untracked only after a collection has passed over it — so the tracked half of
    a closure taken before one answers when the collector last ran rather than
    what the structure holds."""
    gc.collect()
    gc.collect()


def _held_after_rows(layout: Layout, owners: int) -> tuple[Closure, Closure]:
    """What the compiled reads hold of their own, and what the whole prepared
    selection does, once ``owners`` roots have been materialized through them."""
    selection = _prepared(layout)
    model = _catalog(selection)
    meta = model.meta
    plan = fetch_plan(query(meta), meta)
    reads = compiled_levels(plan, meta)
    batch(model, plan, reads, _rows(model, owners))
    _settled()
    return closure(reads, (meta, selection, model, plan)), closure(
        selection, _boundary(layout, selection)
    )


def _held_after_executions(layout: Layout, executions: int) -> Closure:
    """What the prepared selection holds once ``executions`` whole executions —
    each with its own fetch plan, its own compiled reads, and its own sealed
    graph — have resolved through it and been discarded."""
    selection = _prepared(layout)
    model = _catalog(selection)
    rows = _root_only(_rows(model, _ONE_ROOT))
    for _ in range(executions):
        _execute(model, rows)
    _settled()
    return closure(selection, _boundary(layout, selection))


def _same_whole_heap(few: Seam, many: Seam, where: str) -> None:
    """What the whole process's Python objects weigh at ``few``'s sample point
    and at ``many``'s, which must be the same number.

    Both arms are built before either is sampled, so each one's stored rows are
    alive at both points and the only thing that can separate the two readings is
    what an arm left behind — in any container anywhere, whether the arm reaches
    it or not.

    The gated number is what the heap holds and not the object or reference
    counts beside it, for a measurement reason rather than a preference. A
    collection untracks a tuple holding only untracked items, so whether one is
    counted as an object follows how many automatic collections landed while an
    arm ran; the walk prices it through its holder either way, so the counts move
    by a handful between the arms and the weight does not move at all.
    """
    lighter, heavier = whole_heap(few, many)
    assert lighter.held == heavier.held, where


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_row_and_after_many() -> None:
    # What preparation holds is fixed by the model's exact Entity layouts and by
    # the compiled reads: eight times the rows through one prepared read must
    # leave the prepared side holding the same objects through the same
    # references, and leave the process weighing what one row's worth left it
    # weighing. A per-row shape, dispatch table, or classified-key set attached to
    # either would move one reading, and a per-row entry banked in a container
    # neither of them reaches would move the other.
    for layout in LAYOUTS:
        one_reads, one_prepared = _held_after_rows(layout, _ONE_ROOT)
        many_reads, many_prepared = _held_after_rows(layout, OWNERS)
        assert one_reads.tracked > 0 and one_reads.references > 0, layout
        assert one_reads == many_reads, layout
        assert one_prepared == many_prepared, layout
    for layout in LAYOUTS:
        _same_whole_heap(_row_seam(layout, _ONE_ROOT), _row_seam(layout, OWNERS), layout)


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_execution_and_after_sixty_four() -> None:
    # The other half: what preparation keeps is independent of the number of
    # graphs materialized and of the executions that materialized them. Sixty-four
    # whole executions — each planning, compiling, converting, and sealing a graph
    # of its own — must leave the selection they were all resolved through holding
    # what one execution left it holding, and leave the process weighing what one
    # execution left it weighing. A query shape cached for the model's lifetime is
    # exactly what would move the closure, and a process-global cache keyed by row
    # or query primitives — which no prepared structure reaches at all, and whose
    # entries the collector need not track — is what the whole-heap reading beside
    # it is taken for.
    for layout in LAYOUTS:
        once = _held_after_executions(layout, 1)
        often = _held_after_executions(layout, _EXECUTIONS)
        assert once.tracked > 0 and once.references > 0, layout
        assert once == often, layout
    for layout in LAYOUTS:
        _same_whole_heap(_execution_seam(layout, 1), _execution_seam(layout, _EXECUTIONS), layout)


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
