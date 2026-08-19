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

Two instruments, because an object can appear without any byte reaching the
allocator:

**Bytes.** :func:`_allocation` grades retention over repeated runs, so a byte
kept per run cannot hide in the floor, beside the high-water rise after
:func:`tracemalloc.reset_peak`, which is what makes an object born and freed
inside the window visible. Neither number is compared against a byte count that
would drift: the free paths are graded at zero, and the declined path against the
cost of exactly one permitted opening. :func:`_first_run` grades those two
numbers for the first run a process makes, in a child interpreter, because a
lazily built cache is paid once and a warmed measurement would never see it —
and one seam per child, so no measured first run has been warmed by another.

**Survivors.** :func:`_survivors` grades objects rather than bytes: the GC-tracked
ones alive at the innermost point of the sequence that were not alive before it
began. CPython serves some construction from a free list, which reaches no
allocator and moves no byte counter — a warmed ``lambda: []`` measures as zero
bytes — and a list, a populated dict, or a bound method is a container the
collector tracks, so this instrument sees what the byte count cannot.

Outside both, stated rather than implied. An object born and dropped inside a
single seam call that the free list also serves: no sample point holds it and no
counter moves. An UNTRACKED survivor: :func:`gc.get_objects` answers only what
the collector tracks, so a retained empty dictionary, all-immutable tuple, or
integer is as invisible to the survivor sample as it is to the byte count. And
the allocation of the read AROUND the seam — the driver SQL, the binds, the rows,
the graph — which is the query's own cost, is not zero, and end to end swamps the
seam's by three orders of magnitude. That is why the window holds the sequence a
read drives the seam through rather than a whole ``find``, and why what a real
call site hands the seam is graded where that call site runs.
"""

from __future__ import annotations

import gc
import subprocess
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

type _Seam = Callable[[Callable[[], None]], None]
"""One sequence through the seam, calling its argument at its innermost point.

Sampling is a parameter rather than a second copy of the sequence, so the bytes
and the survivors are graded over the same code.
"""


class _DecliningProvider:
    """A Provider that refuses every root, which is the second costed path."""

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return None

    def report_handler_error(self, error: object, /) -> None:
        return None


DECLINING: Final = _DecliningProvider()


def _unsampled() -> None:
    """The sampler a byte measurement passes: the sequence runs unobserved."""


def _allocation(work: _Seam) -> tuple[int, int]:
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
            work(_unsampled)
        gc.collect()
        gc.collect()
        before, _ = tracemalloc.get_traced_memory()
        for _ in range(REPEATS):
            work(_unsampled)
        gc.collect()
        gc.collect()
        after, _ = tracemalloc.get_traced_memory()

        gc.collect()
        tracemalloc.reset_peak()
        work(_unsampled)
        current, peak = tracemalloc.get_traced_memory()
    finally:
        sys.settrace(tracer)
    return after - before, peak - current


def _first_run(work: _Seam) -> tuple[int, int]:
    """The same two numbers for ONE run, with nothing warmed but the measurement.

    Retention is read before the peak is reset, so the reading's own objects land
    in the retained figure rather than in the transient one and the caller's
    control carries the identical harness cost. Meaningful only in a process that
    has never run ``work``, which is why :func:`_first_run_in_a_child` exists.
    """
    gc.collect()
    gc.collect()
    before, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    work(_unsampled)
    current, peak = tracemalloc.get_traced_memory()
    return current - before, peak - current


def _survivors(seam: _Seam) -> list[object]:
    """GC-TRACKED objects alive at ``seam``'s innermost point that were not alive
    before it began.

    :func:`gc.get_objects` answers the collector's own containers, so an
    untracked survivor — an empty dictionary, an all-immutable tuple, an integer
    — is outside this instrument exactly as it is outside the byte count.

    Both snapshots and the sampler itself are built before the first one is
    taken, so the only objects the comparison has to discount are the two it
    cannot avoid: the identity set and the sampled list.
    """
    sampled: list[list[object]] = []

    def sample() -> None:
        sampled.append(gc.get_objects())

    gc.collect()
    before = {id(obj) for obj in gc.get_objects()}
    seam(sample)
    live = sampled[0]
    return [obj for obj in live if id(obj) not in before and obj is not live and obj is not before]


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
        open_read_root(DECLINING, target=TARGET, interface="TYPED") as read,
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


def _flush_under(batch: WriteBatchActivity) -> _Seam:
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


def _scopes_under(root: ReadActivity) -> _Seam:
    def run(sample: Callable[[], None]) -> None:
        with root as read, read.database_call(STATEMENT, "READ", TARGET) as call:
            call.read_completed(ROWS)
            sample()

    return run


FIRST_RUN_SEAMS: Final[dict[str, _Seam]] = {
    "control": _nothing,
    "read": _unobserved_read,
    "flush": _flush_under(INERT),
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
    """:func:`_first_run` for ``seam``, in a process that has run nothing else."""
    report = subprocess.run(
        [sys.executable, __file__, seam], capture_output=True, text=True, check=True
    )
    kept, transient = report.stdout.split()
    return int(kept), int(transient)


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
    # Equality is exact rather than an upper bound, and the declined path does
    # everything the control does: any further object would have to be born
    # while the descriptor holding the UUID is still alive, which raises the
    # high-water mark the control sets. What the opening returns is costed by
    # the scopes measurement below, so the two together leave an extra
    # allocation nowhere to sit.
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


def test_an_unobserved_read_leaves_no_tracked_object_alive_behind_it() -> None:
    # The claim the byte count cannot make. A list, a dict, or a method object
    # the free list serves moves no byte counter at all, and an activity that
    # built one to hold its own state would measure as free while every scope
    # entry created an object.
    assert _survivors(_unobserved_read) == []


def test_a_declined_root_keeps_no_tracked_object_of_its_opening_alive() -> None:
    # The permitted UUID and descriptor are the opening's own transients: by the
    # time the scopes the decline hands back are running, neither is reachable,
    # which is what "the same path as the default one" means for a declined root.
    assert _survivors(_declined_read) == []


def test_an_unobserved_write_batch_leaves_no_tracked_object_alive_either() -> None:
    assert _survivors(_flush_under(INERT)) == []


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
    _first_run(_nothing)
    print(*_first_run(FIRST_RUN_SEAMS[sys.argv[1]]))
    tracemalloc.stop()
