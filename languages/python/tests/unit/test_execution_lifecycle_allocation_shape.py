"""What an unobserved operation costs the lifecycle, measured as one number.

`core/spec/m-execution-lifecycle.md` states the cost of observation as a
contract: with no installed Provider "no allocation, clock read, or I/O occurs",
and a declining Provider "costs only the UUID, descriptor, and opening call".
The site tests in ``test_execution_lifecycle_read.py`` each name ONE cost — a
lifecycle class, a canonical spelling, a row count, a bound method — which is
what makes a failure there actionable. This one names only *that* a cost exists,
over the whole sequence a read drives the seam through, so a cost of a kind
nobody has named yet fails here without a reviewer finding it first.

The seam is driven with the values a real read hands it: a namespaced
:class:`~parallax.core.metamodel.EntityIdentity` whose canonical spelling has to
be BUILT, a real Lowered Statement, and a row list far longer than the
interpreter's small-integer cache. Those are the inputs whose spelling and
sizing were themselves the last two defects, so a seam that touches either
allocates — and allocating is the whole assertion.

**Observed.** Every object allocated inside the window, including one freed
before the window closes: :func:`tracemalloc.reset_peak` is what makes a
transient allocation visible, because the high-water mark rises when the object
is born and does not fall when it dies. Retention is measured beside it over
repeated runs, so a byte kept per run cannot hide in the floor. Neither number
is compared against a byte count that would drift: the free paths are graded at
zero, and the declined path against the cost of exactly one permitted opening.

**Not observed.** The allocation of the read AROUND the seam: the driver SQL,
the binds, the rows, the graph. That is the query's own cost, it is not zero,
and end to end it swamps the seam's by three orders of magnitude — which is why
the window holds the sequence a read drives the seam through rather than a whole
``find``. An allocation served from a CPython free list would also be invisible,
since it reaches no allocator; the bound-method shape is measurably not one of
those, but a future one could be, which is why the site tests stay.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
from collections.abc import Callable
from typing import Final
from uuid import uuid4

from parallax.core.execution_lifecycle import ExecutionLifecycleHandler, RootExecution
from parallax.core.execution_lifecycle._activity import (
    INERT,
    ReadActivity,
    WriteBatchActivity,
    open_read_root,
)
from parallax.core.metamodel import EntityIdentity
from parallax.core.sql_gen import LoweredStatement

TARGET: Final = EntityIdentity("parallax.compatibility", "Account")
STATEMENT: Final = LoweredStatement("select id from account where id = $1", (7,))
ROWS: Final = [{"id": index} for index in range(1_000)]
AFFECTED: Final = 5_000
"""A driver's affected-row count, likewise past the small-integer cache."""

WARMUP: Final = 200
"""Runs before every window, so import, cache-fill, and first-call costs are outside it."""

REPEATS: Final = 200
"""Runs inside the retention window. The floor is the harness's own handful of
bytes, so anything kept per run — the smallest object is tens of bytes — clears
it by two orders of magnitude, and "under one byte per run" needs no threshold
anyone has to justify."""


class _DecliningProvider:
    """A Provider that refuses every root, which is the second costed path."""

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return None

    def report_handler_error(self, error: object, /) -> None:
        return None


DECLINING: Final = _DecliningProvider()


def _allocation(work: Callable[[], None]) -> tuple[int, int]:
    """Bytes ``work`` keeps over :data:`REPEATS` runs, and bytes one run
    allocates and frees again.

    The two are measured in separate windows because they need opposite things:
    retention needs repetition, so a byte kept per run cannot hide in the floor,
    while a transient allocation is a high-water mark that repetition does not
    accumulate.

    The tracer is uninstalled around both: under branch coverage it allocates per
    executed line, which would be the only thing this measures. Every line inside
    a window is covered by the suites grading its behavior.
    """
    tracer = sys.gettrace()
    sys.settrace(None)
    try:
        for _ in range(WARMUP):
            work()
        gc.collect()
        gc.collect()
        before, _ = tracemalloc.get_traced_memory()
        for _ in range(REPEATS):
            work()
        gc.collect()
        gc.collect()
        after, _ = tracemalloc.get_traced_memory()

        gc.collect()
        tracemalloc.reset_peak()
        work()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        sys.settrace(tracer)
    return after - before, peak - current


def _nothing() -> None:
    """The control for a path the specification costs at nothing."""


def _unobserved_read() -> None:
    with (
        open_read_root(None, target=TARGET, interface="TYPED") as read,
        read.database_call(STATEMENT, "READ", TARGET) as call,
    ):
        call.read_completed(ROWS)


def _declined_read() -> None:
    with (
        open_read_root(DECLINING, target=TARGET, interface="TYPED") as read,
        read.database_call(STATEMENT, "READ", TARGET) as call,
    ):
        call.read_completed(ROWS)


def _one_declined_opening() -> None:
    """The control for the declined path: exactly the UUID, the descriptor, and
    the opening call the specification permits it, and nothing else."""
    execution = RootExecution(uuid4(), "READ")
    DECLINING.open(execution)


def _flush_under(batch: WriteBatchActivity) -> Callable[[], None]:
    """The other seam an unobserved operation drives: a flush's Database Call.

    The activity is closed over rather than named as a module global, which is
    how every call site receives it — and is not a detail: on CPython 3.12 an
    attribute call on a module global can leave the interpreter binding a method
    object, so the global spelling would measure that instead of the seam.
    """

    def run() -> None:
        with batch.database_call(STATEMENT, "WRITE", TARGET) as call:
            call.write_completed(AFFECTED)

    return run


def _scopes_under(root: ReadActivity) -> Callable[[], None]:
    def run() -> None:
        with root as read, read.database_call(STATEMENT, "READ", TARGET) as call:
            call.read_completed(ROWS)

    return run


def test_an_unobserved_read_allocates_nothing_at_all() -> None:
    tracemalloc.start()
    try:
        control_kept, control_transient = _allocation(_nothing)
        kept, transient = _allocation(_unobserved_read)
    finally:
        tracemalloc.stop()
    assert control_transient == 0 and control_kept < REPEATS, "the harness measures its own noise"
    assert transient == 0
    assert kept < REPEATS


def test_a_declined_root_costs_only_its_uuid_descriptor_and_opening_call() -> None:
    tracemalloc.start()
    try:
        permitted_kept, permitted_transient = _allocation(_one_declined_opening)
        kept, transient = _allocation(_declined_read)
    finally:
        tracemalloc.stop()
    assert permitted_transient > 0, "the permitted opening is not free, or nothing is measured"
    assert transient == permitted_transient
    assert kept < REPEATS
    assert permitted_kept < REPEATS


def test_after_a_decline_the_scopes_cost_what_the_default_path_costs() -> None:
    # "After decline it has the same event-, counter-, diagnostic-, and
    # clock-free path": the opening is the whole difference, so what a declined
    # root opens is costed exactly as the default path's scopes are.
    declined = open_read_root(DECLINING, target=TARGET, interface="TYPED")
    default = open_read_root(None, target=TARGET, interface="TYPED")
    tracemalloc.start()
    try:
        default_kept, default_transient = _allocation(_scopes_under(default))
        kept, transient = _allocation(_scopes_under(declined))
    finally:
        tracemalloc.stop()
    assert transient == default_transient == 0
    assert kept < REPEATS
    assert default_kept < REPEATS


def test_an_unobserved_write_batch_allocates_nothing_either() -> None:
    # A transaction's flush publishes under the same shared inert activity, so
    # the claim is one claim: the write seam is graded by the same measurement
    # rather than by a reader noticing that it looks like the read seam.
    tracemalloc.start()
    try:
        kept, transient = _allocation(_flush_under(INERT))
    finally:
        tracemalloc.stop()
    assert transient == 0
    assert kept < REPEATS
