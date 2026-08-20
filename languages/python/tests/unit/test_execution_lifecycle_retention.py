"""What an OBSERVED operation leaves behind, and what a live one holds.

`core/spec/m-execution-lifecycle.md` bounds live lifecycle memory at
`O(N * (P + D))` over `N` concurrent accepted roots, `P` active Providers, and
maximum activity depth `D`, "independent of events already completed, retry
count, stream length, result cardinality, and materialized graph size". Every
clause of that is a statement about REFERENCES rather than about bytes, so each
one below is graded with a definite answer rather than against a threshold: an
object either survives its root or it does not, and a count either equals its
neighbour or it does not.

Three questions, three instruments:

**What a finished root left.** :func:`_left_behind` answers every live instance
of a type the lifecycle package defines that was not alive before the work began.
It is taken over a real ``find`` and a real ``transact``, because a completed
root is a claim about the whole composition rather than about the seam: the
handle, the unit of work, the result, and the port all outlive the root, and any
of them holding an event would fail here.

**What repetition kept.** Reference liveness cannot see an UNTRACKED survivor —
a retained integer, an empty tuple, an all-immutable tuple — so the byte
instrument is read beside it over two hundred observed roots, where anything kept
per root clears the harness floor by two orders of magnitude.

**What a live root holds.** Live memory is sampled at the innermost point of `N`
simultaneously open roots, which is the only point at which `N` roots exist at
once.

What is graded elsewhere, and deliberately not restated here. The FREE paths —
no Provider installed, and a Provider that declined — are
``test_execution_lifecycle_allocation_shape.py``, which measures the same seam
with the same instruments. What a live ACTIVITY holds of the failures it has
already seen is ``test_execution_lifecycle_transaction.py``: an attempt keeps one
handled read failure however many it handles, and an invocation keeps one failed
attempt however many it retries. Both are properties of the attribution slot, so
they are stated where the attribution rule they follow from is stated.
"""

from __future__ import annotations

import gc
import tracemalloc
from collections.abc import Callable
from contextlib import ExitStack, suppress
from typing import Final

from _lifecycle_cost_support import (
    REPEATS,
    STATEMENT,
    TARGET,
    Seam,
    allocation,
    rows,
    survivors,
)
from _transact_support import ACCOUNT, FIXED, NEW_ROW, RecordingPort, deadlock, new_account

from _support import mirrored_models as mm
from parallax.core.db_error import DatabaseError
from parallax.core.execution_lifecycle import ExecutionEvent, ExecutionLifecycleHandler
from parallax.core.execution_lifecycle._activity import (
    DeliveryState,
    InstalledLifecycle,
    open_read_root,
)
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

SMALL: Final = rows(500)
LARGE: Final = rows(5_000)
"""Two result sizes an order of magnitude apart, neither below the small-integer
cache: ``len`` of a short list answers a cached integer while either of these
allocates one, so the two costs have the same shape and their equality is exact
rather than approximate."""

LIFECYCLE_PACKAGE: Final = "parallax.core.execution_lifecycle"
_TESTING: Final = f"{LIFECYCLE_PACKAGE}.testing"


class _DiscardingHandler:
    """A Handler that receives every event and keeps none of them.

    What a retention proof needs and what the recorder deliberately is not: the
    recorder holds every event it is handed, so a root observed through it would
    measure the recorder's own contract rather than the runtime's.
    """

    def handle(self, event: ExecutionEvent, /) -> None:
        return None


class _AcceptingProvider:
    """A Provider that accepts every root, so every event is really delivered."""

    def open(self, execution: object, /) -> ExecutionLifecycleHandler:
        return _DiscardingHandler()

    def report_handler_error(self, error: object, /) -> None:
        return None


PROVIDER: Final = _AcceptingProvider()
INSTALLED: Final = InstalledLifecycle(PROVIDER, DeliveryState())


def _lifecycle_object(obj: object) -> bool:
    """Whether ``obj`` is an instance of a type the lifecycle package defines.

    Identified by where the type is defined, so an event, an outcome, a live
    activity, a publisher, and a diagnostic are all in, while an application's
    own Handler is out however closely it mirrors one. ``.testing`` is excluded
    because the recorder there retains every event by design.

    ``__module__`` is read defensively because ``gc.get_objects`` answers CLASSES
    too, and a class's type is its metaclass: ``type.__module__`` is a descriptor
    rather than a string, and an extension module's metaclass may answer anything
    at all. A class is never what this is looking for, so anything that does not
    answer a string is not one.
    """
    module = getattr(type(obj), "__module__", None)
    if not isinstance(module, str):
        return False
    return module.startswith(LIFECYCLE_PACKAGE) and not module.startswith(_TESTING)


def _left_behind(work: Callable[[], None]) -> list[object]:
    """Every lifecycle object alive after ``work`` that was not alive before it.

    The baseline binds the objects themselves and not merely their addresses,
    and the binding outlives the comparison: an object it holds cannot be
    collected, so no address it recorded can be reused by an object born inside
    ``work`` and read back as already known.

    The handle's own per-handle state is outside the window by construction —
    a caller builds its ``Database`` before the baseline is taken — which is what
    leaves this measuring what a ROOT costs rather than what a connection does.
    """
    gc.collect()
    known = [obj for obj in gc.get_objects() if _lifecycle_object(obj)]
    identities = {id(obj) for obj in known}
    work()
    gc.collect()
    survived = [
        obj for obj in gc.get_objects() if _lifecycle_object(obj) and id(obj) not in identities
    ]
    return survived


def _live_lifecycle_objects(seam: Seam) -> list[object]:
    """The lifecycle objects alive at ``seam``'s innermost point that were not
    alive before it began."""
    return [obj for obj in survivors(seam) if _lifecycle_object(obj)]


def _observed_db(port: RecordingPort) -> Database:
    return connect(port, ACCOUNT, clock=FixedClock(FIXED), lifecycle_provider=PROVIDER)


def _one_read(db: Database) -> Callable[[], None]:
    def run() -> None:
        db.find(mm.Account.where(mm.Account.id == 7)).result()

    return run


def _observed_read_over(result: list[dict[str, object]]) -> Seam:
    """One observed Read root driven at the seam, over a result of a given size.

    The seam rather than a whole ``find``, because the query's own allocation —
    the driver SQL, the binds, the rows, the graph — is not zero and swamps the
    lifecycle's by three orders of magnitude, so an end-to-end comparison would
    grade the materializer.
    """

    def run(sample: Callable[[], None]) -> None:
        with (
            open_read_root(INSTALLED, target=TARGET, interface="TYPED") as read,
            read.database_call(STATEMENT, "READ", TARGET) as call,
        ):
            call.read_completed(result)
            sample()

    return run


def _concurrent_roots(count: int) -> Seam:
    """``count`` Read roots open at once, each with a Database Call in flight.

    Every root is opened through the same installed Provider, which is what makes
    the sample the shape the bound is stated over: one Provider active across `N`
    roots, each holding its own publisher and its own chain of live activities.
    """

    def run(sample: Callable[[], None]) -> None:
        with ExitStack() as stack:
            for _ in range(count):
                read = stack.enter_context(
                    open_read_root(INSTALLED, target=TARGET, interface="TYPED")
                )
                call = stack.enter_context(read.database_call(STATEMENT, "READ", TARGET))
                call.read_completed(SMALL)
            sample()

    return run


def test_a_completed_read_leaves_no_lifecycle_object_alive() -> None:
    # The published result is where a retained trace would have hung: the
    # retired accessor answered one off the Snapshot, so a result that still
    # reached its root's events would keep every one of them alive for as long as
    # the caller held the value.
    port = RecordingPort(rows=[NEW_ROW])
    db = _observed_db(port)
    assert _left_behind(_one_read(db)) == []


def test_a_completed_transaction_leaves_no_lifecycle_object_alive() -> None:
    # A transaction is the deep root: an invocation over an attempt over a write
    # batch over its Database Calls, with a participating read and its dependency
    # batch beside them. Nothing of that tree may outlive the callback.
    port = RecordingPort(rows=[NEW_ROW])
    db = _observed_db(port)

    def body(tx: Transaction) -> None:
        tx.insert(new_account())
        tx.find(mm.Account.where(mm.Account.id == 7)).result()

    assert _left_behind(lambda: db.transact(body)) == []


def test_a_retried_transaction_leaves_neither_its_events_nor_its_diagnostics_alive() -> None:
    # The failure path is where retention has something to hold: a rendered
    # diagnostic, an attribution pairing an exception with a child, and one
    # attempt's events per try. The trigger is dropped rather than caught into a
    # name, because a live traceback holds the frames of every scope it unwound
    # through and would keep their activities alive by itself.
    port = RecordingPort(rows=[NEW_ROW])
    port.txn_faults = [deadlock(), deadlock()]
    db = _observed_db(port)

    def run() -> None:
        with suppress(DatabaseError):
            db.transact(lambda tx: tx.insert(new_account()), retries=1)

    assert _left_behind(run) == []
    assert port.begins == 2


def test_a_hundred_sequential_roots_leave_exactly_what_one_leaves() -> None:
    # The slope claim, stated as an equality of two definite answers rather than
    # as a trend anyone has to read: if a completed root left one reference, a
    # hundred roots would leave a hundred.
    port = RecordingPort(rows=[NEW_ROW])
    db = _observed_db(port)
    one = _one_read(db)

    def many() -> None:
        for _ in range(100):
            one()

    assert _left_behind(one) == _left_behind(many) == []


def test_two_hundred_observed_roots_keep_no_bytes_between_them() -> None:
    # What reference liveness cannot answer. `gc.get_objects` reports only what
    # the collector tracks, so a retained integer, an empty tuple, or an
    # all-immutable tuple is invisible to every assertion above — and visible
    # here, where anything kept per root would clear the floor by two orders of
    # magnitude.
    tracemalloc.start()
    try:
        kept, transient = allocation(_observed_read_over(SMALL))
    finally:
        tracemalloc.stop()
    assert transient > 0, "an observed root is not free, or nothing is being observed"
    assert kept < REPEATS


def test_an_observed_root_costs_the_same_over_ten_times_the_result() -> None:
    # Independence from result cardinality, as an equality rather than a trend.
    # A seam that sized, copied, or held the rows would allocate ten times as
    # much for the larger result; what it does instead is read one length off a
    # borrowed sequence, and one length costs one integer either way.
    tracemalloc.start()
    try:
        small_kept, small_transient = allocation(_observed_read_over(SMALL))
        large_kept, large_transient = allocation(_observed_read_over(LARGE))
    finally:
        tracemalloc.stop()
    assert small_transient == large_transient
    assert small_kept < REPEATS
    assert large_kept < REPEATS
    assert len(_live_lifecycle_objects(_observed_read_over(SMALL))) == len(
        _live_lifecycle_objects(_observed_read_over(LARGE))
    )


def test_live_lifecycle_memory_is_linear_in_the_roots_open_at_once() -> None:
    # `O(N * (P + D))` over one Provider and a fixed depth is `N` times what one
    # root holds — linear through the origin rather than merely affine, because
    # nothing in the runtime is shared between two roots of one Provider. A
    # per-root cost that grew with the roots already open, or a registry the
    # publisher joined, would break the equality at the first count that is not
    # one.
    per_root = len(_live_lifecycle_objects(_concurrent_roots(1)))
    assert per_root > 0, "a live root holds nothing, or nothing is being sampled"
    counts = (1, 2, 4, 8, 16)
    measured = {count: len(_live_lifecycle_objects(_concurrent_roots(count))) for count in counts}
    assert measured == {count: count * per_root for count in counts}


def test_nothing_of_a_closed_root_is_alive_once_the_sample_is_past() -> None:
    # The concurrency sample is taken while every root is still open, so it says
    # nothing about what happens when they close. Leaving them closes them all.
    assert _left_behind(lambda: _concurrent_roots(16)(lambda: None)) == []
