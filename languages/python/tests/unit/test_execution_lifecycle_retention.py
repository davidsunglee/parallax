"""What an OBSERVED operation leaves behind, and what a live one holds.

`core/spec/m-execution-lifecycle.md` bounds live lifecycle memory at
`O(N * (P + D))` over `N` concurrent accepted roots, `P` active Providers, and
maximum activity depth `D`, "independent of events already completed, retry
count, stream length, result cardinality, and materialized graph size". Nearly
all of that is a statement about REFERENCES rather than about bytes, and every
reference claim below is graded with a definite answer rather than against a
threshold: an object either survives its root or it does not, and a count either
equals its neighbour or it does not. Bytes are read where a reference cannot be
counted — an UNTRACKED value the collector never sees — and read against a bound
the claim itself sets rather than as an equality, because a byte reading of two
different shapes moves by tens where a free list served one construction and not
another.

All three terms are workload parameters, and none is reached the same way.

**`N` and `P` are workload parameters**, so they are read as a grid of counts and
each reading is graded twice. The line is a pin on THIS runtime: its live memory
is exactly affine in both, which implies the bound and is strictly stronger than
it — a conforming implementation whose per-root state were chunked or
capacity-doubled would sit on a staircase rather than a line and would fail here,
and would need this gate re-taken rather than the runtime changed. The bound
itself is the second reading, that the average cost of a root at the largest
count never exceeds what the first root cost, which every shape the
specification admits satisfies and no cost growing with what is already open
does. Neither says anything past the largest count measured: five counts refuse
a term that is already visible by thirty-two roots, and nothing refuses one that
turns on later.

**`D` is a workload parameter too**, and one construction reaches it: a joining
``db.transact`` opens its scope on the attempt already running, so a callback
that calls ``db.transact`` again nests a second joining scope inside the first,
and nothing bounds how often that repeats. Depth is therefore read as a grid the
same way `N` and `P` are, over that construction driven through the public
``Database.transact`` — the only door it has — and graded by the same two
readings. Read across the Provider counts as well, because `P + D` is an
addition: what one more level costs must not depend on how many Providers are
active, nor one more Provider on how deep the root is, and a cost in `P * D`
would agree with this at one column and disagree at the others. Crossing depth
with `N` is the one thing that door cannot be asked for — a joining call joins
the transaction active on the THREAD, so no second root is ever open beside the
one it joined — and the same scopes held open on a live attempt at the seam are
what the crossing below reads instead.

**The crossing, and which reading covers which part of it.** The bound is one
expression over all three parameters, so a grid that varies one of them while
pinning the others settles only that no parameter is wrong ALONE: a per-root
state sized per Provider and per level is affine down every axis at every column
of it and quadratic in the plane the two make. What is graded beside those grids
is therefore the whole crossing — every combination of the three counts — against
the shape the expression itself names, which is a base plus a per-root cost
affine in `P` and in `D` with no term in their product.

Two instruments read that, at two grains. The four counts come off ONE sample, so
no workload is covered in one of them and not in another: wherever a reading is
taken, all four are taken. Bytes are the second instrument and are read at the
crossing's corners rather than at every point of it, because a byte reading costs
a warmed repetition of the whole workload where a count costs a single sample of
it.

| Workload varied | The four counts | Bytes |
| --- | --- | --- |
| `N` | crossing, roots grid | crossing, roots grid |
| `P` | crossing, roots grid, depth grid | crossing, depth grid |
| `D` | crossing, depth grid | crossing, depth grid |
| `N` and `P` | crossing, roots grid | crossing |
| `N` and `D` | crossing | crossing |
| `P` and `D` | crossing, depth grid | crossing, depth grid |
| all three | crossing | crossing |

The **crossing** is
:func:`test_live_lifecycle_memory_is_affine_in_the_roots_providers_and_levels_at_once`
for the counts and
:func:`test_the_bytes_live_roots_keep_stay_within_the_bound_at_every_crossing_of_it`
for the bytes, over :data:`_GRID` and its corners. The **roots grid** is
:func:`test_live_lifecycle_memory_is_linear_in_the_roots_open_at_once`, which
crosses `N` and `P` over two different root SHAPES rather than one. The **depth
grid** is
:func:`test_live_lifecycle_memory_is_linear_in_the_joining_calls_nested_at_once`,
which crosses `D` and `P` at the public door.

Three things no cell of that table claims. Nothing past the largest count in each
tuple: thirty-two refuses a term already visible by thirty-two, and nothing here
refuses one that turns on later. Nothing about bytes as a LINE — every byte cell
is the bound and only the bound, so a hold small against what the smallest
workload already weighs passes all of them, and what refuses a TRACKED hold of
any size is the reference count beside it. And the crossings with `N` are read at
the seam rather than at the public door, for the reason above;
:func:`test_the_scopes_a_seam_nests_are_what_the_joining_recursion_opens` is what
holds those two constructions to the same per-level cost.

Two structural readings stand beside that grid, because a line fitted over
repetitions of ONE level says nothing about the levels that occur once. Every
live activity holds its own parent and nothing else of the tree, and the kinds
that open at more than one depth hold exactly the same wherever they sit. Both
are read as TOTALS of what one activity holds, never as the difference between
two arms — a difference cancels whatever the two arms share, which is precisely
the ancestor-derived state a depth claim is about. They are taken over the
CORRELATION chains, enumerated from the activity Protocols rather than listed by
hand, so an algebra that grows a level — the Snapshot Stream and Stream Batch
kinds the specification names and this runtime does not yet implement would make
it five — fails that enumeration and forces those readings to be taken again.
What the enumeration cannot see is the joining recursion above, which reaches
its parent through the active attempt rather than through the scope enclosing
it: every one of those scopes is a child of the same attempt, so correlation
depth stays fixed while live depth grows, and the grid rather than the
enumeration is what answers for it.

Four questions, four instruments:

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

**What live roots hold.** Live memory is sampled at the innermost point of what
is open at once — the roots for the `N` and `P` grid, the joining scopes nested
inside one another for the `D` one, and both at once for the crossing of all
three — which is the only point at which they exist
together, and one sample is read four ways because each way sees what the others
cannot. The
lifecycle-typed survivor count answers what the runtime's own structure costs per
root, per active Provider, and per level of nesting. The whole survivor count
answers the same question about state of ANY type, so a per-root buffer belonging
to no lifecycle class lands in it. The reference count answers what neither can:
one container is one object however many things it points at, so a scope that
kept its ancestors, or the roots open beside it, shows up there and nowhere else.
The inbound count answers what all three miss — a registry the installed
composition owned before the roots opened is no survivor however many of them it
accumulates, and every reference it took into the window is counted from the
holder's side. A fifth reading stands beside those four at the points the table
above names: the bytes still reachable at the same sample point, which is the
only one of the five that moves at all when a holder grew by values the collector
never tracked.

**What a live root holds of a value it was HANDED** needs the same sample and one
arrangement. A result is one borrowed object whatever its cardinality, so the
seam asking that question builds the rows inside the window and drops its own
reference before sampling: what is still reachable then is reachable through the
root, and it is read both as survivors and as bytes — the second because a hold
the collector does not track moves no count at all.

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
from collections.abc import Callable, Mapping
from contextlib import ExitStack, suppress
from itertools import product
from typing import Final, NamedTuple, get_type_hints

import pytest
from _lifecycle_cost_support import (
    REPEATS,
    STATEMENT,
    TARGET,
    Closure,
    Seam,
    allocation,
    closure,
    live_graph,
    retained,
    rows,
)
from _transact_support import ACCOUNT, FIXED, NEW_ROW, RecordingPort, deadlock, new_account

from _support import mirrored_models as mm
from parallax.core.db_error import DatabaseError
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleProvider,
    FanoutLifecycleProvider,
    JoinedInvocation,
    JoinedInvocationRaised,
    JoinedInvocationReturned,
    TransactionInvocationFinished,
    TransactionInvocationStarted,
)
from parallax.core.execution_lifecycle._activity import (
    DatabaseCallActivity,
    DeliveryState,
    InstalledLifecycle,
    JoinedInvocationActivity,
    ReadActivity,
    TransactionAttemptActivity,
    TransactionInvocationActivity,
    WriteBatchActivity,
    open_read_root,
    open_transaction_root,
)
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

SMALL_ROWS: Final = 500
LARGE_ROWS: Final = 5_000
"""Two result sizes an order of magnitude apart, neither below the small-integer
cache: ``len`` of a short list answers a cached integer while either of these
allocates one, so the two costs have the same shape and their equality is exact
rather than approximate."""

SMALL: Final = rows(SMALL_ROWS)
LARGE: Final = rows(LARGE_ROWS)

LIFECYCLE_PACKAGE: Final = "parallax.core.execution_lifecycle"
_TESTING: Final = f"{LIFECYCLE_PACKAGE}.testing"

_ROOTS: Final = (1, 2, 4, 8, 32)
"""The roots held open at once. The first two are one root apart, which is what
makes the difference between them a per-root cost rather than a ratio, and the
largest is far from them deliberately: a cost quadratic in the roots already
open sits within one root's own weight of the line at sixteen roots and whole
roots away from it at thirty-two."""

_PROVIDERS: Final = (1, 2, 3)
"""Providers active on every root. Three points, so the slope taken from the
first two has somewhere to be wrong: a per-root cost quadratic in the Providers
agrees with a linear one at two counts and disagrees at the third."""

_DEPTHS: Final = (1, 2, 4, 8, 32)
"""Joining calls nested inside one another, for the same reason and over the same
spread as :data:`_ROOTS`: the first two are one level apart, so their difference
is what one more level costs rather than a ratio, and the largest is far enough
from them that a cost quadratic in the levels already open is whole levels off
the line instead of within one level's weight of it."""


class _Point(NamedTuple):
    """One workload the bound is stated over: ``roots`` accepted roots open at
    once, ``providers`` Providers active on each of them, and ``depth`` joining
    calls nested inside each.

    ``depth`` counts the levels a workload VARIES rather than the whole activity
    depth. Every root has the levels its own shape gives it whichever workload
    opens it, so those are part of what one root costs rather than part of this
    term, and the bound is asymptotic in `D` either way.
    """

    roots: int
    providers: int
    depth: int


_LEAST: Final = _Point(min(_ROOTS), min(_PROVIDERS), min(_DEPTHS))
_MOST: Final = _Point(max(_ROOTS), max(_PROVIDERS), max(_DEPTHS))

_GRID: Final = tuple(
    _Point(roots, providers, depth)
    for roots in _ROOTS
    for providers in _PROVIDERS
    for depth in _DEPTHS
)
"""Every combination of the three counts.

What one axis at a time cannot reach: a per-root state sized per Provider AND
per level is affine down each axis on its own and quadratic in the plane the two
make, so a grid that varies one parameter while pinning the others admits it at
every column it reads.
"""

_CROSSINGS: Final = tuple(
    _Point(
        *(
            most if varies else least
            for varies, most, least in zip(raised, _MOST, _LEAST, strict=True)
        )
    )
    for raised in product((False, True), repeat=3)
)
"""The smallest workload, and the one that raises each nonempty set of the three
parameters to its largest count.

The crossing at the grain a byte reading can afford: eight workloads rather than
:data:`_GRID`'s seventy-five, because a byte reading costs a warmed repetition of
the whole workload where a count costs one sample of it. Every set of parameters
appears exactly once, so a term in any of them — one, two, or all three — is at
its largest against the bound somewhere in here.
"""


def _bound(point: _Point) -> int:
    """`N * (P + D)` at ``point``.

    The specification's own expression, and the size every average is taken
    over: a reading divided by this is what the bound holds constant, so one
    number grades a workload however many parameters it varied at once.
    """
    return point.roots * (point.providers + point.depth)


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


class _Live(NamedTuple):
    """What live roots hold, read four ways from one sample, because each answers
    what the other three cannot.

    ``lifecycle`` is what the runtime's own structure costs, and ``tracked`` is
    every survivor whatever defined its type, so state a root keeps in a list, a
    dict, or an application's own class is in the second and not the first.
    ``references`` is what neither count can see: one container is one object
    however many things it points at, so a scope that kept a graph — its
    ancestors, the roots open beside it — moves no count at all and moves this by
    one for every reference it kept. ``inbound`` is the same reading from the
    other end, and the only one that sees a holder OLDER than the window: a
    registry an installed composition already owned is no survivor, so what it
    took is counted where it points rather than where it is held. All four are
    counts of structure rather than readings of an allocator, so all four are
    exact, and none of them sees a value the collector never tracked — which is
    what :func:`retained` is read beside them for.
    """

    lifecycle: int
    tracked: int
    references: int
    inbound: int


_NOTHING: Final = _Live(0, 0, 0, 0)


def _live(seam: Seam) -> _Live:
    """What is alive at ``seam``'s innermost point that was not alive before it.

    Run once unsampled first, so a cost paid the first time anything opens a
    root lands outside every window rather than inside whichever measurement
    happened to run first. That is what leaves the counts comparable with each
    other: a one-time structure is what the bound admits and what the allocation
    suite's first-run measurement grades, and a series that charged it to one
    member would read it as a difference between them.
    """
    seam(lambda: None)
    graph = live_graph(seam)
    return _Live(
        sum(1 for obj in graph.survivors if _lifecycle_object(obj)),
        len(graph.survivors),
        sum(len(gc.get_referents(obj)) for obj in graph.survivors),
        graph.inbound,
    )


def _difference_of(larger: _Live, smaller: _Live) -> _Live:
    """What ``larger`` holds and ``smaller`` does not, reading by reading."""
    return _Live(*(more - less for more, less in zip(larger, smaller, strict=True)))


def _line(base: _Live, added: _Live, steps: int) -> _Live:
    """``base`` plus ``steps`` of ``added``, reading by reading."""
    return _Live(*(start + steps * more for start, more in zip(base, added, strict=True)))


def _affine(measured: dict[int, _Live], over: tuple[int, ...]) -> _Live:
    """What one more of ``over`` costs, given readings that sit on a line.

    AFFINE rather than proportional, because a structure built once, when the
    first root opens, is what `O(N * (P + D))` admits, and a test demanding a
    reading through the origin would fail an implementation for being cheaper
    than this one.

    Stricter than the bound, deliberately and only here: this is a pin on the
    shape THIS runtime has, where every reading really does sit on the line the
    two smallest set, so any departure from it is a change worth reading rather
    than noise. An implementation that chunked its per-root state, or doubled a
    capacity, would satisfy the specification and fail this, and the answer then
    is to re-take the reading rather than to change the runtime.
    :func:`_at_most_proportional` is the reading that stands for the bound
    itself.
    """
    fewest, next_fewest = over[0], over[1]
    step = _difference_of(measured[next_fewest], measured[fewest])
    base = _difference_of(measured[fewest], _line(_NOTHING, step, fewest))
    assert measured == {key: _line(base, step, key) for key in measured}, measured
    return step


def _at_most_proportional(measured: dict[int, _Live], over: tuple[int, ...]) -> None:
    """That the average cost of one of ``over`` never rises as more are added.

    The bound as the specification states it, in the one form every shape it
    admits satisfies: an affine cost with a non-negative base has an average that
    falls, chunked storage charges a whole chunk to the first count that needs
    one and averages it away over the rest, and only a cost that grows with what
    is already open has an average that rises. Read against the SMALLEST count
    rather than as a slope, so no reading of any particular shape is required —
    only that thirty-two roots cost no more than thirty-two of the first one did.

    What it gives up for admitting every conforming shape is resolution: what it
    refuses is a term large enough to lift the average, so a quadratic one small
    against whatever one-time base the first count charged passes.
    :func:`_affine` is what refuses one of any size, at the price of admitting
    only the shape measured here.
    """
    fewest, most = over[0], over[-1]
    assert all(
        largest * fewest <= smallest * most
        for largest, smallest in zip(measured[most], measured[fewest], strict=True)
    ), (measured[fewest], measured[most])


class _Fit(NamedTuple):
    """Live memory as one function of the whole workload: ``origin``, plus each
    of `N` roots costing ``root`` plus ``provider`` for every active Provider
    plus ``level`` for every joining call nested inside it.

    The shape `N * (P + D)` names, written as arithmetic the readings are checked
    against. Its per-root cost is affine in `P` and affine in `D` and has no term
    in their PRODUCT, which is the whole of what a crossed grid adds to axes read
    one at a time: a state sized per Provider per level satisfies every
    single-axis line and has nowhere to sit in this.
    """

    origin: _Live
    root: _Live
    provider: _Live
    level: _Live


def _fitted(measured: Mapping[_Point, _Live]) -> _Fit:
    """The one function of that shape the four smallest workloads determine.

    Read off unit steps rather than solved for: the two smallest counts on every
    axis are one apart, so each difference is what one more of that parameter
    costs. Nothing here grades anything — :func:`_predicts` against the whole
    grid is what does, and a cost of any other shape disagrees with the fit
    somewhere in it.
    """
    least = measured[_LEAST]
    provider = _difference_of(measured[_LEAST._replace(providers=_PROVIDERS[1])], least)
    level = _difference_of(measured[_LEAST._replace(depth=_DEPTHS[1])], least)
    per_root = _difference_of(measured[_LEAST._replace(roots=_ROOTS[1])], least)
    return _Fit(
        _difference_of(least, per_root),
        _difference_of(_difference_of(per_root, provider), level),
        provider,
        level,
    )


def _predicts(fit: _Fit, point: _Point) -> _Live:
    """What ``fit`` says the workload at ``point`` costs, reading by reading."""
    return _Live(
        *(
            start + point.roots * (each + point.providers * per_provider + point.depth * per_level)
            for start, each, per_provider, per_level in zip(*fit, strict=True)
        )
    )


def _within_the_bound(measured: Mapping[_Point, _Live]) -> None:
    """That no workload's cost per unit of `N * (P + D)` exceeds the smallest
    workload's.

    :func:`_at_most_proportional` read over a whole crossing rather than down one
    axis, and against the expression the specification states rather than against
    one count. The argument for it is the same — an affine cost with a
    non-negative base has an average that falls — while the size divided by is
    the one the bound names, so a per-root term in `P * D` raises this average
    where each axis read alone leaves it flat.
    """
    smallest = min(measured, key=_bound)
    least, unit = measured[smallest], _bound(smallest)
    for point, reading in measured.items():
        assert all(
            more * unit <= less * _bound(point) for more, less in zip(reading, least, strict=True)
        ), (smallest, least, point, reading)


def _bytes_within_the_bound(measured: Mapping[_Point, int]) -> None:
    """The same reading in bytes, which is the only one an UNTRACKED hold moves.

    Bytes are graded against the bound and never against a line: two workloads of
    the same shape do not allocate proportionally, so what this refuses is an
    average per unit of `N * (P + D)` that rises rather than any particular
    arithmetic. Coarse by design, then — a hold small against whatever the
    smallest workload already weighs passes — and the only reading of any of them
    that sees a value the collector never tracked.
    """
    smallest = min(measured, key=_bound)
    least, unit = measured[smallest], _bound(smallest)
    for point, kept in measured.items():
        assert kept * unit <= least * _bound(point), (smallest, least, point, kept)


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


def _observed_read_owning(count: int) -> Seam:
    """One observed Read root over a result the SEAM builds and then drops.

    :func:`_observed_read_over` hands the seam a list built before the window,
    where an activity that kept it would allocate nothing the window could see —
    which is exactly the shape a byte reading has to be arranged to catch. Here
    the rows are built inside the window and the caller's own reference is
    dropped before the sample, so every byte still reachable at that point is
    reachable through the root.
    """

    def run(sample: Callable[[], None]) -> None:
        result = rows(count)
        with (
            open_read_root(INSTALLED, target=TARGET, interface="TYPED") as read,
            read.database_call(STATEMENT, "READ", TARGET) as call,
        ):
            call.read_completed(result)
            del result
            sample()

    return run


def _fanout(providers: int) -> FanoutLifecycleProvider:
    """``providers`` Providers active on every root.

    Composed for one Provider as much as for four, so the shape a count is read
    over does not change between the counts being compared: a fan-out opens a
    composite Handler of its own, and a single Provider installed directly does
    not, which would put a step in the middle of a claim about a slope.
    """
    return FanoutLifecycleProvider([_AcceptingProvider() for _ in range(providers)])


def _installed(providers: int) -> InstalledLifecycle:
    """What a handle holds for ``providers`` Providers active on every root."""
    return InstalledLifecycle(_fanout(providers), DeliveryState())


type _Chain = Callable[[ExitStack, InstalledLifecycle], tuple[object, ...]]
"""One root opened to the full depth of its shape, holding every level open on
``stack`` and answering the activities it opened, outermost first.

One definition serves both questions the shape is asked. Held on a stack it is a
root among the roots open at once, and the count of them is what varies; entered
alone it is one live chain, and every level of it is measured where it stands.
"""


def _read_chain(stack: ExitStack, installed: InstalledLifecycle) -> tuple[object, ...]:
    """A Read root and its Database Call: the shallowest shape a root has."""
    read = stack.enter_context(open_read_root(installed, target=TARGET, interface="TYPED"))
    call = stack.enter_context(read.database_call(STATEMENT, "READ", TARGET))
    call.read_completed(SMALL)
    return (read, call)


def _begun_attempt(
    stack: ExitStack, installed: InstalledLifecycle
) -> tuple[TransactionInvocationActivity, TransactionAttemptActivity]:
    """The two levels every transaction shape starts with, held open on ``stack``.

    The attempt's outcome is registered as a callback rather than reported here,
    so it is taken after everything opened beneath the attempt has left and
    before the attempt itself does — the order a real transaction reports in, and
    the only one that leaves the attempt finishing committed.
    """
    invocation = stack.enter_context(
        open_transaction_root(
            installed,
            concurrency="optimistic",
            retries=1,
            retry_optimistic_conflicts=False,
            extra_retriable=None,
        )
    )
    attempt = stack.enter_context(invocation.attempt())
    attempt.begun()
    stack.callback(attempt.committed)
    return invocation, attempt


def _write_batch_chain(stack: ExitStack, installed: InstalledLifecycle) -> tuple[object, ...]:
    """An invocation, its attempt, a Write Batch, and the call the batch issued.

    The deepest shape the algebra admits, and the one the concurrency grid is
    read over beside the shallowest: a per-root cost that grew with the roots
    already open has more places to hide in a root that holds four activities
    than in one that holds two.
    """
    invocation, attempt = _begun_attempt(stack, installed)
    batch = stack.enter_context(attempt.write_batch("pre_commit"))
    call = stack.enter_context(batch.database_call(STATEMENT, "WRITE", TARGET))
    # The count is measured off the same list the shallow call reports the length
    # of, rather than named as a constant: an integer a module already holds is a
    # reference and an integer a call computes is an allocation, and a call has to
    # weigh what it weighs for its DEPTH rather than for where its number came
    # from.
    call.write_completed(len(SMALL))
    return (invocation, attempt, batch, call)


def _participating_read_chain(
    stack: ExitStack, installed: InstalledLifecycle
) -> tuple[object, ...]:
    """An invocation, its attempt, a participating Read, and that read's call.

    The other four-level shape, and the one that puts a Read at a depth other
    than a root's: the same activity kind opens directly under a Handle here and
    two levels down under an attempt.
    """
    invocation, attempt = _begun_attempt(stack, installed)
    read = stack.enter_context(attempt.read(TARGET, "TYPED"))
    call = stack.enter_context(read.database_call(STATEMENT, "READ", TARGET))
    call.read_completed(SMALL)
    return (invocation, attempt, read, call)


def _nested_chain(depth: int) -> _Chain:
    """An invocation, its attempt, and ``depth`` joining scopes nested inside one
    another, every one of them held open.

    The live structure :func:`_joined_depth` reaches through ``Database.transact``,
    built instead on the attempt each of those scopes opens against — which is
    what makes depth a parameter of a shape `N` of can be held open at once. The
    public door cannot be asked for that: a joining call joins the transaction
    active on the THREAD, so no second root is open beside the one it joined, and
    the crossing of `D` with `N` exists only here.
    :func:`test_the_scopes_a_seam_nests_are_what_the_joining_recursion_opens` is
    what ties the two constructions together.
    """

    def chain(stack: ExitStack, installed: InstalledLifecycle) -> tuple[object, ...]:
        invocation, attempt = _begun_attempt(stack, installed)
        nested = tuple(stack.enter_context(attempt.joined_invocation()) for _ in range(depth))
        return (invocation, attempt, *nested)

    return chain


def _joined_invocation_chain(stack: ExitStack, installed: InstalledLifecycle) -> tuple[object, ...]:
    """An invocation, its attempt, and a joining call nested inside it.

    Three CORRELATION levels rather than four: everything a joining call's
    callback drives — a read, a batch, another joining call — is a child of the
    same attempt this one is a child of, so nothing it opens is named beneath it.
    How deeply those scopes nest inside one another is a different question, and
    :func:`_nested_chain` is the shape that varies it.
    """
    return _nested_chain(1)(stack, installed)


_SHAPES: Final = (
    (_read_chain, (ReadActivity, DatabaseCallActivity)),
    (
        _write_batch_chain,
        (
            TransactionInvocationActivity,
            TransactionAttemptActivity,
            WriteBatchActivity,
            DatabaseCallActivity,
        ),
    ),
    (
        _participating_read_chain,
        (
            TransactionInvocationActivity,
            TransactionAttemptActivity,
            ReadActivity,
            DatabaseCallActivity,
        ),
    ),
    (
        _joined_invocation_chain,
        (TransactionInvocationActivity, TransactionAttemptActivity, JoinedInvocationActivity),
    ),
)
"""Every CORRELATION chain the algebra admits, and the kinds each level is.

A chain here is the parent relation an event's ``parent_activity_id`` follows,
which is what the two structural readings are taken over. Checked against the
Protocols rather than trusted:
:func:`test_the_correlation_chains_nest_four_levels_and_no_more` derives the same
set from the activity kinds themselves, so a shape missing here is a failure
rather than an omission. It is not a bound on how deep live scopes nest, which
:func:`_joined_depth` reaches past any of these.
"""

_ACTIVITY_KINDS: Final = (
    DatabaseCallActivity,
    JoinedInvocationActivity,
    ReadActivity,
    TransactionAttemptActivity,
    TransactionInvocationActivity,
    WriteBatchActivity,
)
"""The activity Protocols this runtime implements.

Five of the seven kinds `m-execution-lifecycle` names, plus the joining call an
invocation nests. Snapshot Stream and Stream Batch have events and no activity
here yet, and their arrival is what would take the longest correlation chain
from four levels to five.
"""


def _opens(kind: type) -> tuple[type, ...]:
    """The activity kinds ``kind`` names as its children, read off its Protocol.

    The return annotation is the whole of the evidence, which is what makes this
    an enumeration of the correlation relation rather than a second copy of it: a
    method that answers an activity parents one, and ``__enter__`` answers the
    kind it is already.

    What it cannot see is a scope opened through something other than the
    activity it nests inside — a joining ``transact`` reaches the ACTIVE ATTEMPT
    for its parent, so its scope sits inside another joining scope while naming
    none of it. That is why the depth term is measured rather than read off here.
    """
    returns = (
        get_type_hints(member).get("return")
        for name, member in vars(kind).items()
        if not name.startswith("__") and callable(member)
    )
    return tuple(nested for nested in returns if isinstance(nested, type))


def _chains_below(kind: type, above: tuple[type, ...] = ()) -> tuple[tuple[type, ...], ...]:
    """Every chain of kinds from ``kind`` down to one that parents nothing.

    A kind found above itself is refused rather than followed, because a cycle in
    the correlation relation has no finite enumeration and the two structural
    readings are taken per chain. It bounds the CORRELATION depth alone: live
    scopes nest as deeply as a workload asks, which
    :func:`test_live_lifecycle_memory_is_linear_in_the_joining_calls_nested_at_once`
    is what grades.
    """
    assert kind not in above, (kind, above)
    nested = tuple(child for child in _opens(kind) if child in _ACTIVITY_KINDS)
    if not nested:
        return ((kind,),)
    return tuple(
        (kind, *below) for child in nested for below in _chains_below(child, (*above, kind))
    )


def _admitted_chains() -> frozenset[tuple[type, ...]]:
    """Every correlation chain a root can parent, from the two root openers."""
    roots = tuple(
        opened
        for opener in (open_read_root, open_transaction_root)
        for opened in (get_type_hints(opener).get("return"),)
        if isinstance(opened, type)
    )
    return frozenset(chain for root in roots for chain in _chains_below(root))


def _concurrent_roots(count: int, providers: int, shape: _Chain) -> Seam:
    """``count`` roots of ``shape`` open at once, through one composition.

    Every root is opened through the same installed composition, which is what
    makes the sample the shape the bound is stated over: `P` Providers active
    across `N` roots, each root holding its own publisher, its own composite
    Handler, and its own chain of live activities.
    """
    installed = _installed(providers)

    def run(sample: Callable[[], None]) -> None:
        with ExitStack() as stack:
            for _ in range(count):
                shape(stack, installed)
            sample()

    return run


def _workload(point: _Point) -> Seam:
    """The workload ``point`` describes: its roots open at once, each nested to
    its depth, through one composition of its Providers."""
    return _concurrent_roots(point.roots, point.providers, _nested_chain(point.depth))


def _held_by_each_level(shape: _Chain) -> tuple[Closure, ...]:
    """What every activity of one live chain of ``shape`` holds of its own.

    Read at the innermost point, where every level is open, and read as a total
    per level rather than as the difference between two arms: what two arms share
    cancels, and an activity's ancestors are exactly what two arms of a depth
    comparison share.
    """
    with ExitStack() as stack:
        activities = shape(stack, INSTALLED)
        return tuple(closure(activity, activities) for activity in activities)


class _RegisteringProvider:
    """A Provider that notes, for every root it opens, the roots it opened beside.

    A per-root cost that grows with `N`, in the shape that hides from every
    reading but one. Both lists were built before any root opened, so neither is
    a survivor; nothing is allocated per pair, so no survivor count moves; and
    what a root's own structure holds is unchanged, so no count of ITS referents
    moves either. What grows is the number of references a holder older than the
    window took into it, which is the inbound reading and nothing else.
    """

    def __init__(self) -> None:
        self.open_roots: list[object] = []
        self.opened_beside: list[object] = []

    def open(self, execution: object, /) -> ExecutionLifecycleHandler:
        self.opened_beside.extend(self.open_roots)
        self.open_roots.append(execution)
        return _DiscardingHandler()

    def report_handler_error(self, error: object, /) -> None:
        return None


def _registering_roots(count: int) -> Seam:
    """``count`` Read roots open at once through a Provider that notes them all.

    The registry is emptied at the start of each run and owned by a Provider
    built before the window, so what the sample sees is a holder OLDER than every
    root it holds.
    """
    provider = _RegisteringProvider()
    installed = InstalledLifecycle(provider, DeliveryState())

    def run(sample: Callable[[], None]) -> None:
        provider.open_roots.clear()
        provider.opened_beside.clear()
        with ExitStack() as stack:
            for _ in range(count):
                _read_chain(stack, installed)
            sample()

    return run


_HOARD: Final = 512
"""Bytes a hoarding Handler keeps for each level it is already inside.

Untracked, so no count of objects or references can see it, and large enough that
the quadratic total thirty-two levels of it make clears what a level of the
workload itself legitimately weighs.
"""


class _HoardingHandler:
    """A Handler that keeps an untracked value sized by the nesting it is inside.

    A cost quadratic in `D`, in the shape that hides from every reading but one:
    a ``bytes`` object is untracked, so it is neither a survivor nor a referent
    of one nor a reference into one, and the list holding them belongs to a
    Handler built before any root opened, so that is no survivor either. All four
    counts stay exactly on the line a linear cost sets while live bytes grow as
    the square of the depth.

    The hoard is dropped when the root Invocation FINISHES rather than when the
    next one starts: a byte reading is the difference between what is reachable
    at the innermost point of one root and what was reachable once the root
    before it had left, and a hoard still held at the second of those cancels out
    of the first.
    """

    def __init__(self) -> None:
        self._kept: list[bytes] = []
        self._nested = 0

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, TransactionInvocationStarted) and isinstance(
            event.invocation, JoinedInvocation
        ):
            self._nested += 1
            self._kept.append(bytes(_HOARD * self._nested))
        elif isinstance(event, TransactionInvocationFinished) and not isinstance(
            event.outcome, JoinedInvocationReturned | JoinedInvocationRaised
        ):
            self._kept.clear()
            self._nested = 0


class _HoardingProvider:
    """A Provider handing every root the same hoarding Handler."""

    def __init__(self) -> None:
        self._handler = _HoardingHandler()

    def open(self, execution: object, /) -> ExecutionLifecycleHandler:
        return self._handler

    def report_handler_error(self, error: object, /) -> None:
        return None


def _joined_depth(depth: int, provider: ExecutionLifecycleProvider) -> Seam:
    """One transaction whose callback joins itself ``depth`` times, sampled at the
    innermost of them.

    The construction that makes activity depth a workload parameter, driven
    through the only door that reaches it: a joining ``db.transact`` opens its
    scope on the attempt already running, so the scope opened by a callback's own
    ``db.transact`` sits inside the scope that callback is running in, and
    neither has closed when the next one opens.

    Driven end to end rather than at the seam, unlike every other shape here,
    because the nesting is a property of what ``transact`` does when a
    transaction is already active on the thread. The reading therefore carries
    the unit of work each level runs as well as the activity each level opens,
    and every reading still has to sit on a line. What it cannot be asked for is
    a second root open beside this one — the thread has exactly one active
    transaction — which is why :func:`_nested_chain` holds the same scopes open
    at the seam for the crossings with `N`.
    """
    port = RecordingPort(rows=[NEW_ROW])
    db = connect(port, ACCOUNT, clock=FixedClock(FIXED), lifecycle_provider=provider)

    def joining(remaining: int, sample: Callable[[], None]) -> Callable[[Transaction], None]:
        def body(_tx: Transaction) -> None:
            if remaining == 0:
                sample()
                return
            db.transact(joining(remaining - 1, sample))

        return body

    def run(sample: Callable[[], None]) -> None:
        db.transact(joining(depth, sample))

    return run


class _JoiningTransitions:
    """Every joining call's Started and Finished, as correlation and nothing else.

    Keeps integers rather than events, so a Handler that would fail the retention
    claims this suite makes elsewhere is not what any of them measure.
    """

    def __init__(self) -> None:
        self.order: list[tuple[str, int]] = []
        self.parents: set[int | None] = set()

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, TransactionInvocationStarted) and isinstance(
            event.invocation, JoinedInvocation
        ):
            self.order.append(("started", event.activity_id))
            self.parents.add(event.parent_activity_id)
        elif isinstance(event, TransactionInvocationFinished) and isinstance(
            event.outcome, JoinedInvocationReturned | JoinedInvocationRaised
        ):
            self.order.append(("finished", event.activity_id))


class _RecordingJoins:
    """A Provider handing every root the same joining-transition recorder."""

    def __init__(self, transitions: _JoiningTransitions) -> None:
        self._transitions = transitions

    def open(self, execution: object, /) -> ExecutionLifecycleHandler:
        return self._transitions

    def report_handler_error(self, error: object, /) -> None:
        return None


def test_a_completed_read_leaves_no_lifecycle_object_alive() -> None:
    # The published result is where a retained trace would hang: a caller holds
    # that value for as long as it likes and long after the root has finished,
    # so a result that could still reach its root's events would keep every one
    # of them alive for exactly that long.
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
        # What a borrowed result weighs, which is the reading an allocation
        # count cannot make: rows the window never allocated cost it nothing to
        # keep. These are built inside the window and let go of before the
        # sample, so what is still reachable is what the ROOT is holding — and
        # an untracked hold, which no count of objects can see, is bytes here.
        small_bytes = retained(_observed_read_owning(SMALL_ROWS))
        large_bytes = retained(_observed_read_owning(LARGE_ROWS))
    finally:
        tracemalloc.stop()
    assert small_transient == large_transient
    assert small_kept < REPEATS
    assert large_kept < REPEATS
    # Fewer bytes between the two than there are extra rows, so anything kept
    # per row is out: the cheapest way to keep one is a reference, and one
    # reference apiece for 4,500 more rows is thirty-six thousand bytes. The
    # bound is read rather than an equality because the two seams allocate
    # different amounts on their way to the sample, and a free list serving one
    # construction and not another moves a byte reading by tens.
    assert abs(small_bytes - large_bytes) < LARGE_ROWS - SMALL_ROWS
    # The same claim about what is REACHABLE, which is exact where the weight is
    # not: a kept result is 4,500 more tracked survivors and 4,500 more
    # references, whatever the allocator did on the way.
    assert _live(_observed_read_owning(SMALL_ROWS)) == _live(_observed_read_owning(LARGE_ROWS))


def test_live_lifecycle_memory_is_linear_in_the_roots_open_at_once() -> None:
    # The `N` and `P` of `O(N * (P + D))`, over the roots open at once and the
    # Providers active on each of them, and over both the shallowest per-root
    # shape and the deepest — a cost that grew with the roots already open has
    # more places to hide in a root holding four activities than in one holding
    # two. A per-root cost that grew with `N`, a registry each publisher joined,
    # or a per-Provider structure quadratic in the composition would all break a
    # line that has to hold at every count: in objects if it allocated one per
    # root, in references if it only pointed at the roots that were already
    # there, and in the inbound count if the pointing were done by something the
    # composition owned before any root opened.
    for shape in (_read_chain, _write_batch_chain):
        measured = {
            (roots, providers): _live(_concurrent_roots(roots, providers, shape))
            for providers in _PROVIDERS
            for roots in _ROOTS
        }
        per_root = {
            providers: _affine({roots: measured[(roots, providers)] for roots in _ROOTS}, _ROOTS)
            for providers in _PROVIDERS
        }
        assert min(min(added) for added in per_root.values()) > 0, (
            "a live root holds nothing, or nothing is being sampled"
        )
        assert min(_affine(per_root, _PROVIDERS)) > 0, (
            "a Provider active on a root costs it nothing, or all three are one Provider"
        )
        # The same readings against the bound rather than against this runtime's
        # shape, which is the claim the specification actually makes and the one
        # a differently shaped implementation would also have to pass.
        for providers in _PROVIDERS:
            _at_most_proportional({roots: measured[(roots, providers)] for roots in _ROOTS}, _ROOTS)
        _at_most_proportional(per_root, _PROVIDERS)
    # Bytes down the same grid's `N` axis, on the deeper of the two shapes: what
    # none of the four counts can answer is an UNTRACKED value — no object to
    # `gc.get_objects` and no referent of one — so a holder accumulating strings
    # or integers per root, the roots' own correlation text say, moves every
    # count not at all and moves this.
    tracemalloc.start()
    try:
        kept = {
            _Point(roots, max(_PROVIDERS), 0): retained(
                _concurrent_roots(roots, max(_PROVIDERS), _write_batch_chain)
            )
            for roots in (min(_ROOTS), max(_ROOTS))
        }
    finally:
        tracemalloc.stop()
    assert kept[_Point(min(_ROOTS), max(_PROVIDERS), 0)] > 0, (
        "a live root weighs nothing, or nothing is being sampled"
    )
    _bytes_within_the_bound(kept)


def test_live_lifecycle_memory_is_linear_in_the_joining_calls_nested_at_once() -> None:
    # The `D` of `O(N * (P + D))`, over the one construction that grows it: a
    # callback calling `db.transact` again nests a joining scope inside the one
    # it is running in, and nothing bounds how often that repeats. Read as a grid
    # rather than argued from the algebra — the correlation tree makes these
    # scopes siblings under one attempt, and being siblings does not close the
    # ones already open.
    #
    # Read twice over, once down each axis, because `P + D` is an addition: a
    # per-level cost that depended on the Providers active, or a per-Provider
    # cost that depended on the depth, is a `P * D` term that agrees with this at
    # one column and disagrees at the others.
    measured = {
        (depth, providers): _live(_joined_depth(depth, _fanout(providers)))
        for providers in _PROVIDERS
        for depth in _DEPTHS
    }
    per_level = {
        providers: _affine({depth: measured[(depth, providers)] for depth in _DEPTHS}, _DEPTHS)
        for providers in _PROVIDERS
    }
    per_provider = {
        depth: _affine(
            {providers: measured[(depth, providers)] for providers in _PROVIDERS}, _PROVIDERS
        )
        for depth in _DEPTHS
    }
    assert min(min(added) for added in per_level.values()) > 0, (
        "a nested joining call holds nothing, or nothing is being sampled"
    )
    assert len(set(per_level.values())) == 1, per_level
    assert len(set(per_provider.values())) == 1, per_provider
    # The same readings against the bound rather than against this runtime's
    # shape, which is the claim the specification makes and the one a differently
    # shaped implementation would also have to pass.
    for providers in _PROVIDERS:
        _at_most_proportional({depth: measured[(depth, providers)] for depth in _DEPTHS}, _DEPTHS)
    # Bytes over the same grid, every point of it, because a level that grew by
    # untracked values moves none of the four counts: a retained integer or
    # `bytes` value is no survivor, no referent of one, and no reference into
    # one. This is what refuses a per-level hold sized by the level's own
    # depth — one lifecycle object and one referent per level however large the
    # value it points at, and a total quadratic in `D`.
    tracemalloc.start()
    try:
        kept = {
            _Point(1, providers, depth): retained(_joined_depth(depth, _fanout(providers)))
            for providers in _PROVIDERS
            for depth in _DEPTHS
        }
    finally:
        tracemalloc.stop()
    assert kept[_Point(1, min(_PROVIDERS), min(_DEPTHS))] > 0, (
        "a live joining scope weighs nothing, or nothing is being sampled"
    )
    _bytes_within_the_bound(kept)


def test_live_lifecycle_memory_is_affine_in_the_roots_providers_and_levels_at_once() -> None:
    # `N * (P + D)` as one claim rather than three, over every combination of the
    # three counts. A grid that varies one parameter while pinning the others
    # settles only that no parameter is wrong ALONE: a per-root state sized per
    # Provider and per level is affine down each axis at every column and
    # violates the bound in the plane, and no reading down an axis sees it. The
    # fit is the shape the specification's expression names — a base, plus a
    # per-root cost affine in `P` and in `D` with no term in their product — and
    # it is taken from four workloads and answered for at all seventy-five.
    measured = {point: _live(_workload(point)) for point in _GRID}
    fit = _fitted(measured)
    assert measured == {point: _predicts(fit, point) for point in _GRID}, (fit, measured)
    assert min(fit.root) > 0 and min(fit.provider) > 0 and min(fit.level) > 0, fit
    assert min(fit.origin) >= 0, fit
    # The same readings against the bound rather than against this runtime's
    # shape, and against the specification's own expression rather than one
    # count at a time.
    _within_the_bound(measured)


def test_the_bytes_live_roots_keep_stay_within_the_bound_at_every_crossing_of_it() -> None:
    # The fifth reading over the same crossing, at its corners. What none of the
    # four counts can answer is an UNTRACKED value — no object to
    # `gc.get_objects`, no referent of one, and no reference into one — so a hold
    # sized per root, per Provider, per level, or per any product of them moves
    # every count not at all and moves this. Read as a bound rather than as a
    # line because two workloads of the same shape do not allocate
    # proportionally: a deque block and a list's over-allocation move a byte
    # reading by hundreds where the counts do not move at all. Coarse by design,
    # then, and the only reading that sees the untracked hold at all.
    tracemalloc.start()
    try:
        kept = {point: retained(_workload(point)) for point in _CROSSINGS}
    finally:
        tracemalloc.stop()
    assert kept[_LEAST] > 0, "a live root weighs nothing, or nothing is being sampled"
    _bytes_within_the_bound(kept)


def test_the_scopes_a_seam_nests_are_what_the_joining_recursion_opens() -> None:
    # What licenses reading the crossings with `N` at the seam. One more joining
    # scope held open on a live attempt costs the same lifecycle structure as one
    # more level of the recursion a real `db.transact` drives, which is the only
    # construction that reaches depth through the public door and the one that
    # cannot be asked for a second root beside it. The two differ in everything
    # around that structure — a real level runs a unit of work of its own and the
    # seam runs none — so what is compared is the lifecycle objects a level adds
    # rather than the whole reading, and the rest is asserted to be the door's
    # surplus rather than a disagreement.
    seam = {depth: _live(_workload(_Point(1, 1, depth))) for depth in _DEPTHS}
    door = {depth: _live(_joined_depth(depth, _fanout(1))) for depth in _DEPTHS}
    at_the_seam, at_the_door = _affine(seam, _DEPTHS), _affine(door, _DEPTHS)
    assert at_the_door.lifecycle == at_the_seam.lifecycle > 0, (at_the_seam, at_the_door)
    assert at_the_door.tracked > at_the_seam.tracked, (at_the_seam, at_the_door)


def test_the_byte_reading_refuses_an_untracked_hold_sized_by_the_nesting() -> None:
    # What the byte reading is worth, demonstrated rather than asserted, and the
    # shape the four counts are blind to: a composition that keeps one untracked
    # value for every level it is already inside holds bytes quadratic in `D`
    # while each level still contributes exactly one lifecycle object and one
    # referent. The counts are read first to establish that they stay on their
    # line under it, and the bytes second to establish that this is what refuses
    # it — which is the whole reason both are read over every grid.
    provider = _HoardingProvider()
    measured = {depth: _live(_joined_depth(depth, provider)) for depth in _DEPTHS}
    _affine(measured, _DEPTHS)
    _at_most_proportional(measured, _DEPTHS)
    tracemalloc.start()
    try:
        kept = {_Point(1, 1, depth): retained(_joined_depth(depth, provider)) for depth in _DEPTHS}
    finally:
        tracemalloc.stop()
    with pytest.raises(AssertionError):
        _bytes_within_the_bound(kept)


def test_the_concurrency_readings_refuse_a_composition_that_keeps_what_is_open() -> None:
    # What the readings above are worth, demonstrated rather than asserted, and
    # what each one reaches: the same grid over a composition that notes, per
    # root, the roots it opened beside. Every count of what the WINDOW created
    # stays on its line under it — the pairs are references a pre-existing list
    # took, not objects anything allocated — and the count taken from the holders'
    # side does not. That is the whole reason one sample is read from both ends,
    # and it is why the pin and the bound are both read: the line refuses the
    # growth at any size, and the bound refuses it because a per-pair hold at
    # thirty-two roots is fifteen times a per-root one.
    measured = {roots: _live(_registering_roots(roots)) for roots in _ROOTS}
    _affine(
        {
            roots: _Live(reading.lifecycle, reading.tracked, reading.references, 0)
            for roots, reading in measured.items()
        },
        _ROOTS,
    )
    with pytest.raises(AssertionError):
        _affine(measured, _ROOTS)
    with pytest.raises(AssertionError):
        _at_most_proportional(measured, _ROOTS)


def test_a_joining_call_nests_a_live_scope_the_correlation_tree_does_not_show() -> None:
    # Why `D` is measured over a workload instead of read off the Protocols. A
    # joining `transact` takes its parent from the ACTIVE ATTEMPT, so every one
    # of these scopes is a child of the same attempt and the correlation tree is
    # three levels deep however many are open — while the scopes themselves nest
    # one inside the next, which the transitions say exactly: a scope is open
    # between its Started and its Finished, every Started here arrives before any
    # Finished, and they close in the reverse of the order they opened.
    transitions = _JoiningTransitions()
    port = RecordingPort(rows=[NEW_ROW])
    db = connect(
        port, ACCOUNT, clock=FixedClock(FIXED), lifecycle_provider=_RecordingJoins(transitions)
    )
    depth = 5

    def joining(remaining: int) -> Callable[[Transaction], None]:
        def body(_tx: Transaction) -> None:
            if remaining > 0:
                db.transact(joining(remaining - 1))

        return body

    db.transact(joining(depth))

    assert [phase for phase, _ in transitions.order] == ["started"] * depth + ["finished"] * depth
    opened = [activity for phase, activity in transitions.order if phase == "started"]
    closed = [activity for phase, activity in transitions.order if phase == "finished"]
    assert closed == list(reversed(opened))
    assert len(transitions.parents) == 1 and None not in transitions.parents, transitions.parents


def test_the_correlation_chains_nest_four_levels_and_no_more() -> None:
    # What an event's `parent_activity_id` can chain through, which is what the
    # two structural readings below are taken over — deliberately not a bound on
    # `D`, which the joining recursion grows past any of these. Enumerated from
    # the Protocols and compared against the shapes this suite measures, so a
    # kind that grew a parent level — the stream activities
    # `m-execution-lifecycle` names and this runtime has yet to open — fails here
    # first and forces those readings to be taken again.
    admitted = _admitted_chains()
    assert admitted == frozenset(kinds for _, kinds in _SHAPES)
    assert max(len(chain) for chain in admitted) == 4


def test_no_live_activity_holds_any_of_its_tree_but_its_own_parent() -> None:
    # What makes the sum over a chain linear in the length of it: one live
    # activity reaches its parent and no other activity, so no level's state is
    # derived from its ancestors. An activity that kept its ancestor chain — the
    # shape that makes live memory quadratic in depth — would reach the levels
    # above its parent and fail here, at whichever level it sat, including the
    # levels that open at exactly one depth and can therefore be compared against
    # nothing.
    for shape, kinds in _SHAPES:
        held = _held_by_each_level(shape)
        assert [holding.reached for holding in held] == [
            (),
            *((level,) for level in range(len(kinds) - 1)),
        ], kinds
        assert min(holding.references for holding in held) > 0, (
            "a live activity holds nothing, or nothing is being sampled"
        )


def test_an_activity_holds_the_same_at_every_depth_it_can_open_at() -> None:
    # The other half of the depth claim: a level costs what it costs wherever it
    # sits. Two of the kinds open at more than one depth — a Read directly under
    # a Handle and two levels down under an attempt, a Database Call under either
    # of those — and each is read as the total ITS OWN structure holds rather
    # than as a difference between two chains, so nothing an ancestor holds can
    # cancel out of the comparison. The Database Call readings cross a read call
    # and a write call as well, which weigh the same.
    depths: dict[type, set[int]] = {}
    holdings: dict[type, set[tuple[int, int]]] = {}
    for shape, kinds in _SHAPES:
        levels = zip(kinds, _held_by_each_level(shape), strict=True)
        for depth, (kind, held) in enumerate(levels, start=1):
            depths.setdefault(kind, set()).add(depth)
            holdings.setdefault(kind, set()).add((held.tracked, held.references))
    assert {kind for kind, at in depths.items() if len(at) > 1} == {
        ReadActivity,
        DatabaseCallActivity,
    }
    disagreeing = {
        kind.__name__: readings for kind, readings in holdings.items() if len(readings) > 1
    }
    assert disagreeing == {}


def test_nothing_of_a_closed_root_is_alive_once_the_sample_is_past() -> None:
    # Both grid samples are taken while every scope is still open, so neither
    # says anything about what happens when they close. Leaving them closes them
    # all, at sixteen roots open at once and at sixteen joining calls nested.
    deepest, _ = _SHAPES[1]
    nested = _joined_depth(16, _fanout(3))
    assert _left_behind(lambda: _concurrent_roots(16, 3, deepest)(lambda: None)) == []
    assert _left_behind(lambda: nested(lambda: None)) == []
