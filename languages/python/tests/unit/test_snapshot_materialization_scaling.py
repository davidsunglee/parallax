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

**Two axes, one claim each.** The first varies rows through one prepared model and
one set of compiled reads: nothing prepared may grow with the rows materialized
through it. The second varies whole executions — a fetch plan, its compiled reads,
and a graph, each unreachable before the next begins — with only the model's
layout catalog held: nothing model-fixed may grow with graphs or with executions,
which is also what states that no query shape was cached for the model's lifetime.

**Two instruments, and deliberately not a byte total.** What each arm holds is
read as a closure — every object one prepared structure reaches without crossing
into another, and every reference between them — and as a survivor census over the
window that built it. A closure is a total of one participant's own state rather
than a difference between two sums, so it answers exactly what the claim asks; the
census answers the other half, which is a per-row reference taken by something
already alive.

A byte reading cannot be the gate here, and the reason is a measurement rather than
a preference. This workload declares every Neutral Type, so its conforming path
runs the canonical Wire codec's ``Timestamp`` leg, and the interpreter's own
``datetime`` formatting leaves a slowly saturating residue behind it: two runs of
one identical seam read four hundred bytes apart on a forty-kilobyte window, in
either direction, after eight hundred warm-up batches. An exact equality over that
window would be a coin toss, and a tolerance is not what this class asserts. The
byte totals therefore live where a machine-relative number belongs — the
non-gating ``just python-report-snapshot-materialization`` — and what is gated
here is the shape, which references and positions answer definitely. The
neighbouring 64-graph item still asserts bytes because its workload declares four
Neutral Types and reaches none of that codec leg.

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
    metamodel,
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
    survivors,
    warmed,
)

from parallax.core.db_port import Row
from parallax.core.entity._layout import CatalogedModel
from parallax.snapshot import prepare_model

_ONE_ROOT: Final = 1
"""Root objects the smaller row arm materializes, against :data:`OWNERS` in the
larger one — eight rows against sixty-four, over the same five levels."""

_EXECUTIONS: Final = 64
"""Whole executions the larger execution arm runs and discards, against one."""

_EDITION: Final = "snapshot-materialization-scaling"


def _rows(layout: Layout, owners: int) -> tuple[tuple[Row, ...], ...]:
    """One arm's stored rows, built here so no measured window allocates them."""
    meta = metamodel(layout)
    prepare_model(workload(layout), edition=_EDITION)
    model = CatalogedModel(meta)
    plan = fetch_plan(query(meta), meta)
    return rows_per_level(model, plan, compiled_levels(plan, meta), owners)


def _root_only(rows: Sequence[Sequence[Row]]) -> tuple[tuple[Row, ...], ...]:
    """``rows`` with every level below the root emptied, which the loop attaches
    as a loaded-empty relationship result.

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
    """One model and one set of compiled reads derived inside the window,
    ``owners`` roots' worth of rows materialized through them, and only the
    prepared state reachable at the sample."""
    meta = metamodel(layout)
    rows = _rows(layout, owners)

    def run(sample: Callable[[], None]) -> None:
        model = CatalogedModel(meta)
        plan = fetch_plan(query(meta), meta)
        reads = compiled_levels(plan, meta)
        batch(model, plan, reads, rows)
        sample()
        assert reads is not None

    return run


def _execution_seam(layout: Layout, executions: int) -> Seam:
    """A layout catalog derived inside the window, ``executions`` whole executions
    run and discarded against it, and only the catalog reachable at the sample."""
    meta = metamodel(layout)
    rows = _root_only(_rows(layout, _ONE_ROOT))

    def run(sample: Callable[[], None]) -> None:
        model = CatalogedModel(meta)
        for _ in range(executions):
            _execute(model, rows)
        sample()
        assert model is not None

    return run


def _held(layout: Layout, owners: int, executions: int) -> tuple[Closure, Closure]:
    """What the compiled reads hold of their own, and what the layout catalog
    does, once ``owners`` roots have been materialized through them ``executions``
    times.

    Collected first, because a tuple holding only untracked items is itself
    untracked only after a collection has passed over it — so the tracked half of
    a closure taken before one answers when the collector last ran rather than
    what the structure holds.
    """
    meta = metamodel(layout)
    model = CatalogedModel(meta)
    plan = fetch_plan(query(meta), meta)
    reads = compiled_levels(plan, meta)
    rows = rows_per_level(model, plan, reads, owners)
    for _ in range(executions):
        batch(model, plan, reads, rows)
    gc.collect()
    gc.collect()
    return closure(reads, (meta, model, plan)), closure(model, (meta,))


def _own_survivors(seam: Seam) -> list[object]:
    """Every object of Parallax's own that ``seam`` leaves alive at its sample
    point, whatever kind it is."""
    return [obj for obj in survivors(seam) if type(obj).__module__.startswith("parallax.")]


def _same_census(few: Sequence[object], many: Sequence[object], where: str) -> None:
    assert len(few) == len(many) > 0, where
    assert sorted(type(obj).__qualname__ for obj in few) == sorted(
        type(obj).__qualname__ for obj in many
    ), where


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_row_and_after_many() -> None:
    # The ticket's invariant at the materialization interface: what preparation
    # holds is fixed by the model's exact Entity layouts and by the compiled
    # reads, so eight times the rows through one prepared read must leave the
    # prepared side holding the same objects through the same references — and
    # leave the same objects of Parallax's own alive behind the window that built
    # it. A per-row shape, dispatch table, or classified-key set attached to
    # either would move one reading or the other.
    for layout in LAYOUTS:
        one_reads, one_catalog = _held(layout, _ONE_ROOT, 1)
        many_reads, many_catalog = _held(layout, OWNERS, 1)
        assert one_reads.tracked > 0 and one_reads.references > 0, layout
        assert one_reads == many_reads, layout
        assert one_catalog == many_catalog, layout
    for layout in LAYOUTS:
        _same_census(
            _own_survivors(warmed(_row_seam(layout, _ONE_ROOT))),
            _own_survivors(warmed(_row_seam(layout, OWNERS))),
            layout,
        )


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_execution_and_after_sixty_four() -> None:
    # The other half: what the MODEL keeps is independent of the number of graphs
    # materialized and of the executions that materialized them. Sixty-four whole
    # executions — each planning, compiling, converting, and sealing a graph of
    # its own — must leave the catalog they were all resolved through holding what
    # one execution left it holding. A query shape cached for the model's lifetime
    # is exactly what would move it.
    for layout in LAYOUTS:
        _, once = _held(layout, _ONE_ROOT, 1)
        _, often = _held(layout, _ONE_ROOT, _EXECUTIONS)
        assert once.tracked > 0 and once.references > 0, layout
        assert once == often, layout
    for layout in LAYOUTS:
        _same_census(
            _own_survivors(warmed(_execution_seam(layout, 1))),
            _own_survivors(warmed(_execution_seam(layout, _EXECUTIONS))),
            layout,
        )


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
