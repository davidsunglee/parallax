"""What an unobserved operation costs the lifecycle, measured over the whole seam.

`core/spec/m-execution-lifecycle.md` states the cost of observation as a
contract: with no installed Provider "no allocation, clock read, or I/O occurs",
and a declining Provider "costs only the UUID, descriptor, and opening call".
The site tests in ``test_execution_lifecycle_read.py`` each name ONE cost — a
lifecycle class, a canonical spelling, a row count, a bound method, the objects a
real call site hands the seam — which is what makes a failure there actionable.
These name only *that* a cost exists, over the whole sequence a read drives the
seam through, so a cost no site test names still fails here.

The seam is driven with the values a real read hands it: a namespaced
:class:`~parallax.core.metamodel.EntityIdentity` whose canonical spelling has to
be BUILT, a real Lowered Statement, and a row list far longer than the
interpreter's small-integer cache. A seam that spells that target or sizes those
rows allocates, and allocating is the whole assertion.

Both instruments live in ``_lifecycle_cost_support``, which states what each
measures and what neither can see. Neither number here is compared against a byte
count that would drift: the free paths are graded at zero, and the declined path
against the cost of exactly one permitted opening.
:func:`~_lifecycle_cost_support.first_run` is read in a CHILD interpreter, one
seam per child, so no measured first run has been warmed by another and a lazily
built cache paid once is inside the window rather than before it.
"""

from __future__ import annotations

import subprocess
import sys
import tracemalloc
from collections.abc import Callable
from typing import Final
from uuid import uuid4

from _lifecycle_cost_support import (
    AFFECTED,
    REPEATS,
    STATEMENT,
    TARGET,
    Seam,
    allocation,
    first_run,
    rows,
    survivors,
)

from parallax.core.execution_lifecycle import ExecutionLifecycleHandler, RootExecution
from parallax.core.execution_lifecycle._activity import (
    INERT,
    DeliveryState,
    InstalledLifecycle,
    ReadActivity,
    WriteBatchActivity,
    open_read_root,
    open_transaction_root,
)

ROWS: Final = rows(1_000)


class _DecliningProvider:
    """A Provider that refuses every root, which is the second costed path."""

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return None

    def report_handler_error(self, error: object, /) -> None:
        return None


DECLINING: Final = _DecliningProvider()
DECLINED: Final = InstalledLifecycle(DECLINING, DeliveryState())
"""What a handle holds for a Provider that refuses everything.

Built at import, which is where a connected handle builds its own: the
per-thread re-entry slot is one allocation per handle per thread rather than one
per root, so materializing it here leaves every window below measuring what a
ROOT costs — the claim the specification actually makes.
"""


def _nothing(sample: Callable[[], None]) -> None:
    """The control for a path the specification costs at nothing."""
    sample()


def _unobserved_read(sample: Callable[[], None]) -> None:
    with (
        open_read_root(None, target=TARGET, interface="TYPED") as read,
        read.database_call(STATEMENT, "READ", TARGET) as call,
    ):
        call.read_completed(ROWS)
        sample()


def _declined_read(sample: Callable[[], None]) -> None:
    with (
        open_read_root(DECLINED, target=TARGET, interface="TYPED") as read,
        read.database_call(STATEMENT, "READ", TARGET) as call,
    ):
        call.read_completed(ROWS)
        sample()


def _one_declined_opening(sample: Callable[[], None]) -> None:
    """The control for the declined path: exactly the UUID, the descriptor, and
    the opening call the specification permits it, and nothing else."""
    execution = RootExecution(uuid4(), "READ")
    DECLINING.open(execution)
    sample()


def _unobserved_transaction(sample: Callable[[], None]) -> None:
    """The whole transaction seam, driven the way composition drives it.

    The scopes a transaction opens are the ones no read reaches — the invocation,
    the attempt whose start the port body announces, the batch a flush runs
    inside, and the enforcement bracket that follows each write — so the free
    path they take is graded here rather than inferred from the read's.
    """
    with (
        open_transaction_root(
            None,
            concurrency="optimistic",
            retries=10,
            retry_optimistic_conflicts=False,
            extra_retriable=None,
        ) as invocation,
        invocation.attempt() as attempt,
    ):
        attempt.begun()
        with attempt.write_batch("pre_commit") as batch:
            with batch.database_call(STATEMENT, "WRITE", TARGET) as call:
                call.write_completed(AFFECTED)
            with batch.enforcing(call):
                sample()
        attempt.committed()


def _flush_under(batch: WriteBatchActivity) -> Seam:
    """The other seam an unobserved operation drives: a flush's Database Call.

    The activity is closed over rather than named as a module global, which is
    how every call site receives it — and is not a detail: on CPython 3.12 an
    attribute call on a module global can leave the interpreter binding a method
    object, so the global spelling would measure that instead of the seam.
    """

    def run(sample: Callable[[], None]) -> None:
        with batch.database_call(STATEMENT, "WRITE", TARGET) as call:
            call.write_completed(AFFECTED)
            sample()

    return run


def _scopes_under(root: ReadActivity) -> Seam:
    def run(sample: Callable[[], None]) -> None:
        with root as read, read.database_call(STATEMENT, "READ", TARGET) as call:
            call.read_completed(ROWS)
            sample()

    return run


FIRST_RUN_SEAMS: Final[dict[str, Seam]] = {
    "control": _nothing,
    "read": _unobserved_read,
    "flush": _flush_under(INERT),
    "transaction": _unobserved_transaction,
    "declined": _declined_read,
    "opening": _one_declined_opening,
}
"""The seams a child interpreter can be asked to measure, by argument name.

One seam per child, because a first run exists once per process: two seams
measured in the same child would leave the later one warmed by whatever the
earlier built. The declined pair shows why that is not hypothetical — both run a
UUID and a descriptor, so measuring them together would grade the second against
a cost the first had already paid.
"""


def _first_run_in_a_child(seam: str) -> tuple[int, int]:
    """:func:`~_lifecycle_cost_support.first_run` for ``seam``, in a process that
    has run nothing else."""
    report = subprocess.run(
        [sys.executable, __file__, seam], capture_output=True, text=True, check=True
    )
    kept, transient = report.stdout.split()
    return int(kept), int(transient)


def test_an_unobserved_read_allocates_nothing_at_all() -> None:
    tracemalloc.start()
    try:
        control_kept, control_transient = allocation(_nothing)
        kept, transient = allocation(_unobserved_read)
    finally:
        tracemalloc.stop()
    assert control_transient == 0 and control_kept < REPEATS, "the harness measures its own noise"
    assert transient == 0
    assert kept < REPEATS


def test_a_declined_root_costs_only_its_uuid_descriptor_and_opening_call() -> None:
    # Equality is exact rather than an upper bound, and the declined path does
    # everything the control does: any further object would have to be born
    # while the descriptor holding the UUID is still alive, which raises the
    # high-water mark the control sets. What the opening returns is costed by
    # the scopes measurement below, so the two together leave an extra
    # allocation nowhere to sit.
    tracemalloc.start()
    try:
        permitted_kept, permitted_transient = allocation(_one_declined_opening)
        kept, transient = allocation(_declined_read)
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
    declined = open_read_root(DECLINED, target=TARGET, interface="TYPED")
    default = open_read_root(None, target=TARGET, interface="TYPED")
    tracemalloc.start()
    try:
        default_kept, default_transient = allocation(_scopes_under(default))
        kept, transient = allocation(_scopes_under(declined))
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
        kept, transient = allocation(_flush_under(INERT))
    finally:
        tracemalloc.stop()
    assert transient == 0
    assert kept < REPEATS


def test_an_unobserved_transaction_allocates_nothing_across_its_whole_seam() -> None:
    # The invocation, the attempt, the batch, and the enforcement bracket are
    # four more scopes an unobserved operation opens, and the specification costs
    # every one of them at nothing.
    tracemalloc.start()
    try:
        kept, transient = allocation(_unobserved_transaction)
    finally:
        tracemalloc.stop()
    assert transient == 0
    assert kept < REPEATS


def test_an_unobserved_read_leaves_no_tracked_object_alive_behind_it() -> None:
    # The claim the byte count cannot make. A list, a dict, or a method object
    # the free list serves moves no byte counter at all, and an activity that
    # built one to hold its own state would measure as free while every scope
    # entry created an object.
    assert survivors(_unobserved_read) == []


def test_a_declined_root_keeps_no_tracked_object_of_its_opening_alive() -> None:
    # The permitted UUID and descriptor are the opening's own transients: by the
    # time the scopes the decline hands back are running, neither is reachable,
    # which is what "the same path as the default one" means for a declined root.
    assert survivors(_declined_read) == []


def test_an_unobserved_write_batch_leaves_no_tracked_object_alive_either() -> None:
    assert survivors(_flush_under(INERT)) == []


def test_an_unobserved_transaction_leaves_no_tracked_object_alive_either() -> None:
    assert survivors(_unobserved_transaction) == []


def test_the_first_run_in_a_process_costs_what_a_warmed_one_does() -> None:
    # A warmed measurement pays every one-time cost outside its own window, so a
    # cache filled on first use — the shape the specification's "no allocation"
    # covers just as much as a per-call one — would be invisible to it. A child
    # interpreter is the only place a first run exists, so each free seam is
    # measured in one of its own, against a control that has already absorbed the
    # harness's own first-call cost.
    control = _first_run_in_a_child("control")
    assert _first_run_in_a_child("read") == control
    assert _first_run_in_a_child("flush") == control
    assert _first_run_in_a_child("transaction") == control


def test_a_declined_roots_first_run_costs_only_its_permitted_opening() -> None:
    # The warmed declined measurement grades a REPEATED opening, so a cost the
    # decline path pays once — a cache filled the first time a root is refused —
    # would sit outside its window as much as outside the free paths'. Each side
    # of the comparison therefore gets its own fresh interpreter, where the
    # declined read and the opening the specification permits it are both first
    # runs and neither has warmed the other.
    assert _first_run_in_a_child("declined") == _first_run_in_a_child("opening")


if __name__ == "__main__":
    tracemalloc.start()
    first_run(_nothing)
    print(*first_run(FIRST_RUN_SEAMS[sys.argv[1]]))
    tracemalloc.stop()
