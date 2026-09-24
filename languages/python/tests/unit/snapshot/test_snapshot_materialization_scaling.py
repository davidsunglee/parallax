"""What a prepared read keeps, and what it refuses to keep per row, per Page,
and per execution.

Prepared exact-Entity layouts are shared rather than rebuilt per row, Page, or
execution, while a query shape belongs to one execution and is not cached for a
model's lifetime. This is the SIZE half of those constraints measured over the
production materialization path, from ``prepare_model`` through ``compile_read``
and ``bind`` to ``PreparedRead.convert_driver`` and conversion: what is retained
must not grow with rows, with Pages, or with executions.

**Two axes, one claim each.** The first varies rows through one prepared
selection, one set of compiled reads, and the levels bound from them: nothing
prepared may grow with the rows materialized through it. The second varies whole
executions — a fetch plan, its compiled reads, and a Page, each unreachable
before the next begins — with only the prepared selection held: nothing
model-fixed may grow with Pages or with executions, which is what forbids a
query shape retained PER EXECUTION.

**Preparation is entered whole.** Every arm derives its cataloged model from
``prepare_model``, and the closure is taken over the selection that answers rather
than over the catalog inside it, so the read and write projections, the Entity
Graph Construction, the row codec, and the write planner are all state a reading
can reach. A catalog constructed directly would leave everything else preparation
composed outside the claim.

**Two instruments: one over structure, one over bytes.** What each arm holds is
read as a closure — every object one prepared structure reaches without crossing
into another, and every reference between them. A closure is a total of one
participant's own state rather than a difference between two sums, so it answers
exactly what the claim asks. Beside it, each axis reads with :func:`retained`
what one more conversion leaves reachable once its Page is gone, which is what
sees an entry taken by a holder no prepared structure reaches, and one the
collector does not track.

**Every conversion is of rows this process has never converted.** A holder keyed
by what a row holds stops growing once the same rows come back, so a byte reading
repeated over one root would read it already full. Each run the reading takes
instead converts a root whose fixture-generated keys and authored names and
labels no earlier run reached, built inside that run, so an entry taken for
those rows keeps bytes of that run alive at the sample point.

Each byte reading is graded against a control that generates a root's rows the
same way and converts none of them, so what is compared is the conversion alone.
No threshold is needed: with the child's hashing pinned, a run that keeps nothing
reads exactly what the control reads.

Both layouts run in one child per axis: the equality is exact per layout, and a
second child would pay for one more interpreter to prove the same thing twice.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from itertools import count, repeat
from typing import Any, Final, cast

from parallax.core.db_port import Row
from parallax.core.entity import UNLOADED, Entity
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ReadOrigin
from parallax.snapshot import ModelSelection, Snapshot, prepare_model
from parallax.snapshot._inspection import SnapshotNodeState
from parallax.snapshot.handle import Database
from parallax.snapshot.handle._publication import read_projection
from tests.unit import _delivery_control_support as control_support
from tests.unit._gc_reachability import Closure, closure, reachable_objects
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
    Seam,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
)

_ONE_ROOT: Final = 1
"""Root objects the smaller row arm materializes, against :data:`OWNERS` in the
larger one — eight rows against sixty-four, over the same five levels — and the
root each run of a byte reading converts."""

_EXECUTIONS: Final = 64
"""Whole executions the larger execution arm runs and discards, against one."""

_UNSEEN: Final = OWNERS
"""The first root after every range the closure readings convert, so the byte
readings' fixture-generated keys, names, and labels are new to conversion
whatever order the readings run in."""

_UNSEEN_ROOTS: Final[Iterator[int]] = count(_UNSEEN)
"""The root each run of a byte reading converts next, shared by every layout and
reading in the process, because two layouts generate the same keys for the same
root."""

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


def _generator(
    layout: Layout, model: CatalogedModel, roots: Iterator[int]
) -> Callable[[], tuple[tuple[Row, ...], ...]]:
    """Every level's rows for the next of ``roots``, built when called.

    Called inside a measured run, so the rows it builds are that run's own: a
    holder that keeps anything of them keeps bytes the reading counts. One root
    per run because the fixture generates every root before the one asked for,
    so what a run costs grows with how many roots every earlier run consumed."""
    meta = model.meta
    plan = fetch_plan(query(layout, meta), meta)
    reads = compiled_levels(layout, plan, meta)

    def rows() -> tuple[tuple[Row, ...], ...]:
        return rows_per_level(layout, model, plan, reads, _ONE_ROOT, next(roots))

    return rows


def _unseen(layout: Layout, model: CatalogedModel) -> Callable[[], tuple[tuple[Row, ...], ...]]:
    """Every level's rows for a root no earlier run reached, so no two runs share
    a key or an authored string."""
    return _generator(layout, model, _UNSEEN_ROOTS)


def _generating(layout: Layout) -> Seam:
    """The control: each run builds one root's rows and converts none of them.

    Always the same root, since nothing converts it: what the control prices is
    building and dropping rows, and a generation cost kept per new root would
    only fail the comparison rather than hide anything from it."""
    model = _catalog(_prepared(layout))
    rows = _generator(layout, model, repeat(0))

    def seam(sample: Callable[[], None]) -> None:
        rows()
        sample()

    return seam


def _converting_unseen_rows(layout: Layout) -> Seam:
    """One prepared selection and one set of compiled and bound reads, each run
    converting the next unseen root's rows into a Page it releases before the
    sample."""
    selection = _prepared(layout)
    model = _catalog(selection)
    meta = model.meta
    plan = fetch_plan(query(layout, meta), meta)
    prepared = prepared_levels(model, compiled_levels(layout, plan, meta))
    unseen = _unseen(layout, model)

    def seam(sample: Callable[[], None]) -> None:
        batch(model, plan, prepared, unseen())
        sample()

    return seam


def _executing_over_unseen_rows(layout: Layout) -> Seam:
    """One prepared selection, each run resolving one whole execution through it
    — its own fetch plan, its own compiled and bound reads, and its own sealed
    Page, none of which outlives it — over the next unseen root."""
    selection = _prepared(layout)
    model = _catalog(selection)
    unseen = _unseen(layout, model)

    def seam(sample: Callable[[], None]) -> None:
        _execute(layout, model, _root_only(unseen()))
        sample()
        assert selection is not None

    return seam


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


def _retains_nothing(seam: Seam, layout: Layout) -> None:
    """That one run of ``seam`` leaves reachable exactly what one run of the
    control does.

    No threshold in either direction: one entry anything keeps of a run's rows or
    of its execution fails the comparison.
    """
    tracemalloc.start()
    try:
        converted = retained(seam)
        generated = retained(_generating(layout))
    finally:
        tracemalloc.stop()
    assert converted == generated, (layout, converted, generated)


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_row_and_after_many() -> None:
    # What preparation holds is fixed by the model's exact Entity layouts and by
    # the compiled reads it bound its levels from: eight times the rows through
    # one prepared read must leave the prepared side holding the same objects
    # through the same references, and a root's rows this process has never
    # decoded must leave no byte of their conversion reachable once their Page
    # is gone. A per-row shape, dispatch table, or classified-key set
    # attached to either would move the closure, and a per-row entry banked in a
    # container neither of them reaches — keyed by what the row holds, so it
    # never grows again once the same rows come back — would move the bytes.
    for layout in LAYOUTS:
        one_reads, one_prepared = _held_after_rows(layout, _ONE_ROOT)
        many_reads, many_prepared = _held_after_rows(layout, OWNERS)
        assert one_reads.tracked > 0 and one_reads.references > 0, layout
        assert one_reads == many_reads, layout
        assert one_prepared == many_prepared, layout
    for layout in LAYOUTS:
        _retains_nothing(_converting_unseen_rows(layout), layout)


@in_a_child_interpreter
def test_prepared_state_is_the_same_size_after_one_execution_and_after_sixty_four() -> None:
    # The other half: what preparation keeps is independent of the number of
    # Pages materialized and of the executions that materialized them. Sixty-four
    # whole executions — each planning, compiling, binding, converting, and
    # sealing a Page of its own — must leave the selection they were all
    # resolved through holding what one execution left it holding, and one more
    # execution over rows this process has never converted must leave no byte of
    # it reachable. A query shape retained per execution is exactly what would
    # move the closure — one banked once for the model and shared by every
    # execution after it leaves both arms holding one, so a size equality answers
    # nothing about it — and an entry banked per execution, or a cache keyed by
    # what a row holds, which no prepared structure reaches and whose entries
    # the collector need not track, is what the byte reading beside it sees.
    for layout in LAYOUTS:
        once = _held_after_executions(layout, 1)
        often = _held_after_executions(layout, _EXECUTIONS)
        assert once.tracked > 0 and once.references > 0, layout
        assert once == often, layout
    for layout in LAYOUTS:
        _retains_nothing(_executing_over_unseen_rows(layout), layout)


@in_a_child_interpreter
def test_a_closed_eager_typed_result_retains_only_projection_metadata_not_execution() -> None:
    port = control_support.GuardedPort(control_support.GUARDED_ROOTS[0])
    root = Database(port.open(), control_support.GUARDED_MODEL)
    scope = root.using_database_login()
    result = scope.find(control_support.guarded_query(control_support.GUARD_WIDTHS[-1]))
    held = cast("Any", result)
    model = held._projection_model
    includes = held._includes
    root.close()
    del root, scope
    gc.collect()
    gc.collect()

    assert model is not None and includes is not None
    direct = gc.get_referents(result)
    assert any(value is model for value in direct)
    assert any(value is includes for value in direct)

    reached = reachable_objects(result, boundaries=(model, includes))

    def category(value: object) -> str:
        if value is model:
            return "model"
        if value is includes:
            return "includes"
        if value is UNLOADED:
            return "unloaded"
        if isinstance(value, Snapshot):
            return "snapshot"
        if isinstance(value, Entity):
            return "entity"
        if isinstance(value, SnapshotNodeState):
            return "node-state"
        if isinstance(value, ReadOrigin):
            return "origin"
        if isinstance(value, EntityIdentity):
            return "entity-identity"
        if isinstance(value, Pin):
            return "pin"
        if isinstance(value, type):
            return "shared"
        if type(value) is dict:
            return "views"
        if type(value) is tuple:
            return "tuple"
        if type(value) in (type(None), bool, int, str):
            return "shared"
        return f"unexpected:{type(value).__module__}.{type(value).__qualname__}"

    inventory = Counter(category(value) for value in reached)
    del inventory["shared"]
    unexpected = {
        name: count for name, count in inventory.items() if name.startswith("unexpected:")
    }
    assert unexpected == {}
    assert inventory == {
        "snapshot": 1,
        "model": 1,
        "includes": 1,
        "entity": 97,
        "node-state": 97,
        "origin": 84,
        "entity-identity": 4,
        "pin": 1,
        "unloaded": 1,
        "views": 97,
        "tuple": 215,
    }


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
