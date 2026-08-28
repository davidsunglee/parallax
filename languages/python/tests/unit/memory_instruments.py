"""What a run of code costs in memory, from six directions at once.

Six instruments, because an object can appear without any byte reaching the
allocator, a borrowed graph can be kept without either number moving, a container
that existed before the window can grow inside it without becoming a survivor at
all, a structure built and dropped between two points of a longer sequence is
gone from every reading taken at the end of it, and a holder OLDER than the
window is outside every reading a window can take:

**Bytes allocated.** :func:`allocation` grades retention over repeated runs, so a
byte kept per run cannot hide in the floor, beside the high-water rise after
:func:`tracemalloc.reset_peak`, which is what makes an object born and freed
inside the window visible. :func:`first_run` grades those two numbers for the
first run a process makes, because a lazily built cache is paid once and a warmed
measurement would never see it.

**Objects and the references that reach them.** :func:`live_graph` grades the
GC-tracked objects alive at a sample point that were not alive before the
sequence began, and every reference in the heap that points at one. CPython
serves some construction from a free list, which reaches no allocator and moves
no byte counter — a warmed ``lambda: []`` measures as zero bytes — and a list, a
populated dict, or a bound method is a container the collector tracks, so the
survivor count sees what the byte count cannot. The INBOUND count sees what the
survivors cannot: a holder that existed before the window is no survivor however
many of the window's objects it accumulates, so a registry a long-lived
composition owns moves no survivor count and moves this by one for every
reference it took. :func:`survivors` is the survivor half alone, for a caller
whose whole claim is that there are none.

**Bytes still reachable.** :func:`retained` grades the bytes alive at a sample
point that were not alive before the sequence began. It is the only one that sees
a whole graph a live scope kept: a survivor count classified by type cannot see a
borrowed list of rows, and an allocation count cannot see a value the window
never allocated. What it costs is that the value has to be built inside the
window, which is what the caller arranges.

**The high-water mark of one region.** :func:`high_water` grades how far above
the level a marked region opened at the process ever rose inside it. Every
reading above answers what is still there at a sample point, so a structure a
sequence builds and releases before reaching one is invisible to all of them;
this is the reading that prices it. It is a NET rise rather than a region's own
total, and what that excludes is stated at the function.

**What the whole process holds.** :func:`whole_heap` grades every object the
collector tracks, every reference they hold, and what they and everything
untracked they reach report through :func:`sys.getsizeof` — as totals, with no
baseline and no survivor sample. Every reading above is a window's own
difference, so a holder that existed before the window is outside all of them
however much it took inside one. This is the reading that has no window to be
outside of, and it has two prices: a total is meaningful only between two runs of
one process that differ in one thing, and it prices PYTHON OBJECTS rather than a
process, so storage an object owns outside its own allocation is not in it.

**What one object holds.** :func:`closure` grades the objects and references one
object reaches without passing through any of a caller-named BOUNDARY. Where the
counts above answer what a whole window kept, this answers what one participant
in it kept, so a caller comparing one structure against the same structure
somewhere else compares two totals rather than the difference of two sums that
share most of their terms.

**Warming: four warm themselves, one is warmed from outside, and one must not
be.** :func:`allocation` runs its seam :data:`WARMUP` times before opening either
of its windows, :func:`retained` warms both its seam and its sampler inside its
own call, :func:`high_water` warms its span the same way, and :func:`whole_heap`
warms each seam and then takes a whole discarded set of readings before the set
it answers. :func:`live_graph` opens its window before the first run, so a seam
that fills a memo on first reach is handed to it through :func:`warmed`, which
puts those memos in the baseline the sample is compared against rather than in
the sample. :func:`first_run` is the one that must not be warmed at all: its
subject IS the first run a process makes, so warming it would erase what it
grades. :func:`closure` walks an object the caller already holds and runs no
seam, so warming does not arise for it.

Outside all of them, stated rather than implied. An object born and dropped
inside a single call that the free list also serves: no sample point holds it and
no counter moves. An UNTRACKED object counted as an OBJECT:
:func:`gc.get_objects` answers only what the collector tracks, so a retained
empty dictionary, all-immutable tuple, or integer is no survivor and no heap
entry — it is reached and priced in bytes by the two walks that follow untracked
referents, and counted by neither census. And, the widest of the three, STORAGE
AN OBJECT OWNS OUTSIDE ITSELF: every byte figure here is either CPython's
allocator through ``tracemalloc`` or a type's own :func:`sys.getsizeof`, and
neither reaches memory a Python object merely points at. A fully touched
``mmap.mmap`` reports the same hundred-odd bytes whether it maps four kilobytes
or four megabytes, and replacing one with a larger mapping moves no object, no
reference, no reported size, and no allocator counter — an anonymous mapping
never reaches the allocator ``tracemalloc`` traces. Nothing in this module is an
instrument for that; a resident-set reading taken from outside the interpreter
is. The instruments are read together for what they DO cover: the byte counts
see a retained integer no count can, the survivor sample sees a free-list list
the byte counts cannot, and the whole-heap totals see what a holder older than
the window took, which none of the rest can.

**Where a reading is taken.** Every instrument here reads the whole process and
not the seam alone — the survivor sample lists each tracked object and counts the
references among them, and every collection walks all of them. What a reading
costs, and the floor it is read against, therefore belong to the interpreter
rather than to what is being measured. :func:`in_a_child_interpreter` is how a
suite says so: the measurement is taken in a process that has loaded only what it
needs, which is what leaves one reading comparable with the same reading taken
beside anything else.

Three ``tests/unit`` cost suites read these, which is what puts them here beside
them; ``tools/snapshot_graph_overhead.py`` reads them too, and names this
directory to do it. Nothing here imports anything but the standard library, so
the subject of a measurement stays the caller's to supply. Never imported by
production code.

A name another module imports carries no leading underscore, because importing
an underscored name across modules is a `reportPrivateUsage` error under pyright
strict; :func:`_unsampled` has no caller outside this module.
"""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import threading
import tracemalloc
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from functools import wraps
from typing import Final, NamedTuple

__all__ = [
    "OWN_INTERPRETER_ATTRIBUTE",
    "REPEATS",
    "WARMUP",
    "Closure",
    "Heap",
    "LiveGraph",
    "Seam",
    "Span",
    "allocation",
    "closure",
    "first_run",
    "high_water",
    "in_a_child_interpreter",
    "live_graph",
    "retained",
    "serve_one_measurement",
    "survivors",
    "takes_its_own_interpreter",
    "untraced",
    "warmed",
    "whole_heap",
]

WARMUP: Final = 200
"""Runs before every window, so import, cache-fill, and first-call costs are outside it."""

REPEATS: Final = 200
"""Runs inside the retention window. The floor is the instrument's own handful of
bytes, so anything kept per run — the smallest object is tens of bytes — clears
it by two orders of magnitude, and "under one byte per run" needs no threshold
anyone has to justify."""

type Seam = Callable[[Callable[[], None]], None]
"""One sequence through the seam, calling its argument at its innermost point.

Sampling is a parameter rather than a second copy of the sequence, so the bytes
and the survivors are graded over the same code.
"""

type Span = Callable[[Callable[[], None], Callable[[], None]], None]
"""One sequence through the seam, calling ``opened`` where the region being
measured begins and ``closed`` where it ends.

Two marks rather than :data:`Seam`'s one, because a peak needs a floor and a
roof: what was already alive where the region opened, and the high-water it
reached before anything it built was released. The region is a middle of the
sequence rather than its innermost point, so the sequence keeps running after
``closed`` and whatever it has to unwind is outside the reading.
"""


def _unsampled() -> None:
    """The sampler a byte measurement passes: the sequence runs unobserved."""


@contextmanager
def untraced() -> Generator[None]:
    """A window with the line tracer uninstalled, on this thread and on any the
    window starts.

    Under branch coverage the tracer allocates per executed line and keeps what
    it records, which would be the only thing a measurement inside the window
    saw. Every line inside a window is covered by the suites grading its
    behavior.

    A thread carries the trace function installed when it STARTS rather than the
    one its parent holds, so uninstalling only this thread's would leave a
    threaded seam measuring the tracer on every worker it opens — the one place
    the window is widest and the reading is least able to show it.
    """
    tracer = sys.gettrace()
    spawned = threading.gettrace()
    sys.settrace(None)
    threading.settrace(None)
    try:
        yield
    finally:
        sys.settrace(tracer)
        threading.settrace(spawned)


def allocation(work: Seam) -> tuple[int, int]:
    """Bytes ``work`` keeps over :data:`REPEATS` runs, and bytes one run
    allocates and frees again.

    The two are measured in separate windows because they need opposite things:
    retention needs repetition, so a byte kept per run cannot hide in the floor,
    while a transient allocation is a high-water mark that repetition does not
    accumulate.
    """
    with untraced():
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
    return after - before, peak - current


def first_run(work: Seam) -> tuple[int, int]:
    """The same two numbers for ONE run, with nothing warmed but the measurement.

    Retention is read before the peak is reset, so the reading's own objects land
    in the retained figure rather than in the transient one and the caller's
    control carries the identical harness cost. Meaningful only in a process that
    has never run ``work``, which is why the allocation suite measures it in a
    child interpreter.
    """
    gc.collect()
    gc.collect()
    before, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    work(_unsampled)
    current, peak = tracemalloc.get_traced_memory()
    return current - before, peak - current


class LiveGraph(NamedTuple):
    """What a window left reachable at its innermost point, from both ends of a
    reference: the objects it created that are still alive, and how many
    references anywhere in the heap point at one of them."""

    survivors: list[object]
    inbound: int


def live_graph(seam: Seam) -> LiveGraph:
    """What is alive at ``seam``'s innermost point that was not alive before it.

    The baseline BINDS the objects it found rather than only their addresses, and
    the binding outlives the sample: an object it holds cannot be freed inside
    the window, so no address it recorded can be reused by an object born there
    and read back as already known.

    The sample is taken after a collection, so what it answers is what is still
    REACHABLE at that point rather than what has merely not been swept yet. That
    is also what makes the reading independent of when the collector last ran: a
    collection untracks a tuple holding only untracked items, so a sample taken
    without one counts a tuple or not according to whether an automatic
    collection happened to land inside the window. An untracked survivor is
    invisible to this instrument either way, and is what :func:`retained` is read
    beside it for.

    The INBOUND count is taken over the whole heap rather than over the survivors
    alone, because the two see opposite pathologies: what a new object holds is
    visible in its own referents, while what a PRE-EXISTING holder accumulated is
    visible only from the holder's side, and a holder that existed before the
    window is no survivor however much it grew inside it.

    The instruments discount themselves: the two heap listings, the identity set,
    and the list they were collected in are the only objects the comparison
    cannot avoid creating.
    """
    sampled: list[list[object]] = []

    def sample() -> None:
        gc.collect()
        sampled.append(gc.get_objects())

    with untraced():
        gc.collect()
        known = gc.get_objects()
        before = {id(obj) for obj in known}
        seam(sample)
    heap = sampled[0]
    instruments = {id(heap), id(known), id(before), id(sampled)}
    born = [obj for obj in heap if id(obj) not in before and id(obj) not in instruments]
    identities = {id(obj) for obj in born}
    inbound = sum(
        1
        for holder in heap
        if id(holder) not in instruments
        for referent in gc.get_referents(holder)
        if id(referent) in identities
    )
    return LiveGraph(born, inbound)


def survivors(seam: Seam) -> list[object]:
    """The survivor half of :func:`live_graph`, for a caller whose claim is that
    there are none."""
    return live_graph(seam).survivors


class Closure(NamedTuple):
    """What one object holds, and which of the boundary it holds it through."""

    reached: tuple[int, ...]
    tracked: int
    references: int


def closure(start: object, boundary: Sequence[object]) -> Closure:
    """What ``start`` reaches without passing through any other member of
    ``boundary``, and which members it reaches.

    A TOTAL reading of one participant's own state, which is what a claim about
    one structure repeated in several places needs: two sums that share most of
    their terms cancel whatever they share when subtracted, and two closures do
    not.

    ``reached`` is the boundary members found, as their positions, so a caller
    states which of them one member may hold rather than how many. The walk stops
    at each of them, so a member reached through another member is not reported:
    what comes back is the boundary this one holds DIRECTLY.

    Classes end the walk. Every instance of a kind reaches its own class and
    everything the module defining it does, which is shared structure no single
    instance can grow; what a class itself accumulated is a reference into the
    window's objects and is what :func:`live_graph` reads.

    Objects the collector does not track are followed but not counted, for the
    reason the survivor sample cannot count them at all: whether an equal integer
    or an interned string is one object or two is the interpreter's business
    rather than the measured structure's.
    """
    others = {id(obj): index for index, obj in enumerate(boundary) if obj is not start}
    seen = {id(start)}
    reached: set[int] = set()
    tracked = 0
    pending = gc.get_referents(start)
    references = len(pending)
    while pending:
        obj = pending.pop()
        identity = id(obj)
        if identity in seen:
            continue
        seen.add(identity)
        if identity in others:
            reached.add(others[identity])
            continue
        if isinstance(obj, type):
            continue
        if gc.is_tracked(obj):
            tracked += 1
        referents = gc.get_referents(obj)
        references += len(referents)
        pending.extend(referents)
    return Closure(tuple(sorted(reached)), tracked, references)


def retained(seam: Seam) -> int:
    """Bytes reachable at ``seam``'s innermost point that were not reachable
    before it began.

    What a live scope KEPT, rather than what it allocated: the sample is taken
    after a collection, so an object the window allocated and dropped is gone
    from it and only what something still holds is counted. Nothing is filtered
    by type, which is the whole point of reading it — a borrowed graph a live
    activity kept is bytes here and is invisible to a survivor count classified
    by where its type is defined.

    Only bytes the window itself allocated are visible, so a caller asking what
    a scope kept of a VALUE builds that value inside the seam and drops its own
    reference before sampling: whatever is still reachable then is reachable
    through the scope.

    The seam is warmed for the same reason :func:`allocation` warms its own, and
    the SAMPLER is warmed as well — a sampled run collects and reads the tracer
    where an unsampled one does not, and the first of those in a process leaves
    tens of bytes behind under coverage that every later one does not. Warming
    the two separately is what leaves this measuring the seam rather than the
    first measurement of it.
    """
    sampled: list[int] = []

    def sample() -> None:
        gc.collect()
        sampled.append(tracemalloc.get_traced_memory()[0])

    with untraced():
        for _ in range(WARMUP):
            seam(_unsampled)
        seam(sample)
        gc.collect()
        before, _ = tracemalloc.get_traced_memory()
        seam(sample)
    return sampled[1] - before


def high_water(span: Span) -> int:
    """How far above the level it opened at the process ever rose inside ``span``'s
    marked region.

    The reading the others cannot take. Every instrument above answers what is
    still there at a sample point, so a structure a longer sequence builds and
    releases before reaching one leaves no trace in any of them; this answers how
    far the process rose while it existed. What a region left BEHIND is inside the
    figure too — the roof is measured against the floor rather than against the
    level the region settled at — so one number covers both what a step rose to
    and what it kept.

    **A NET rise over one floor, which is exactly two blind spots and not one.**
    The floor is the process's level where the region opened, read after a
    collection; the roof is the process's peak since. So an allocation that never
    takes the process above an earlier moment of the same region is invisible
    however large it is — a peak is a maximum — and, for the same arithmetic,
    memory the region RELEASES after the floor was read is headroom the rest of
    the region allocates into for free: a region that frees a megabyte and then
    allocates and frees a hundred kilobytes reads near zero rather than a hundred
    kilobytes. Neither is a threshold that could be tightened. A caller wanting
    what a region allocated in its own right must mark a region that releases
    nothing it did not first allocate, and read the figure as an upper bound on
    the region's peak rather than as its size.

    The floor is read after a collection, so a region that only reuses structure
    its caller already built reads near zero rather than reporting the caller's
    own level. The span is warmed for the reason :func:`retained` warms its seam,
    and ``tracemalloc`` must already be tracing, as it must be there.
    """
    marks: list[int] = []

    def opened() -> None:
        gc.collect()
        marks.append(tracemalloc.get_traced_memory()[0])
        tracemalloc.reset_peak()

    def closed() -> None:
        marks.append(tracemalloc.get_traced_memory()[1])

    with untraced():
        for _ in range(WARMUP):
            span(_unsampled, _unsampled)
        span(opened, closed)
    return marks[1] - marks[0]


class Heap(NamedTuple):
    """The whole process's PYTHON-LEVEL size at one point.

    ``objects`` and ``references`` are over what the collector tracks; ``held``
    adds every untracked object those reach, priced by :func:`sys.getsizeof` once
    per PATH the walk arrives by, for the reason :func:`closure` does not count
    them at all — whether two equal integers are one object is the interpreter's
    business, while how many ways the heap arrives at a value of that size is the
    heap's own shape. Per path and not per reference: the walk carries no
    identity set, so a value under a shared untracked subgraph is charged once
    for every path into it however few references point at it directly.

    ``held`` is what each type reports about itself, so storage an object owns
    outside its own allocation is in none of the three numbers: a fully touched
    ``mmap.mmap`` weighs the same whatever it maps.
    """

    objects: int
    references: int
    held: int


def whole_heap(*seams: Seam) -> tuple[Heap, ...]:
    """What the WHOLE PROCESS holds at each of ``seams``' innermost points.

    No baseline and no survivor sample, which is the whole of why it exists.
    Every reading above is a window's own difference, so a holder that EXISTED
    BEFORE the window is outside all of them: it is no survivor, a reference it
    took points at an object that may itself predate the window, and bytes it
    banked into an untracked buffer are reachable from nothing a survivor sample
    can start walking at. A total has no window to be outside of, so any PYTHON
    STRUCTURE anywhere that grew is in one of these three numbers.

    **Where a total still stops.** The three are :func:`gc.get_objects` and
    :func:`sys.getsizeof`, which price Python objects and the references among
    them rather than the process's memory. Storage an object owns outside its own
    allocation — an ``mmap.mmap``, a buffer a C extension holds — is a
    constant-size shell in every one of them however large its backing grows, so
    growing one in place moves nothing here at all. What sees that is a
    resident-set reading taken from outside the interpreter, which no instrument
    in this module takes.

    **Every seam at once, because a total is not a difference.** Two totals are
    comparable only when they are taken in ONE process against everything else
    about it held still — including what the reader itself is holding, since a
    caller that bound the first reading before taking the second would be
    counted holding it. Handing the whole comparison over is what lets the
    instrument discount its own: each sample excludes the heap listing and every
    reading already taken, so the process looks identical at all of them.

    The caller owes the same discipline over its fixtures: a seam that varies one
    thing must hold the WIDTH of every value it produces fixed, because a longer
    string or a wider integer at a later position moves ``held`` for a reason
    that is not retention. Read that way the readings are exact and no tolerance
    is needed; read any other way they are not readings at all.

    Warmed twice over, because a total shows every first-reach cost a difference
    would cancel: each seam runs :data:`WARMUP` times unsampled before it is
    sampled, and the whole set is then run and sampled a second time, with the
    first set's readings answered to nobody.
    """
    readings: list[Heap] = []

    def sample() -> None:
        gc.collect()
        heap = gc.get_objects()
        readings.append(_heap_census(heap, frozenset({id(heap), id(readings), *map(id, readings)})))

    with untraced():
        for _ in range(2):
            readings.clear()
            for seam in seams:
                for _ in range(WARMUP):
                    seam(_unsampled)
                seam(sample)
    return tuple(readings)


def _heap_census(heap: Sequence[object], instruments: frozenset[int]) -> Heap:
    """``heap``'s own totals, less the containers the listing needed.

    The untracked walk carries no identity set and REVISITS deliberately: a value
    reached by several paths is priced once for each of them, which is what keeps
    ``held`` a function of the heap's shape rather than of how the interpreter
    happened to share a value.

    It terminates all the same. An untracked object holds only untracked objects
    — inserting a tracked value into a dictionary re-tracks it, and a tuple is
    immutable — so no untracked graph closes a cycle, and none of them can reach
    back into anything tracked and re-count an entry of ``heap``.
    """
    objects = 0
    references = 0
    held = 0
    pending: list[object] = []
    for obj in heap:
        if id(obj) in instruments:
            continue
        objects += 1
        held += sys.getsizeof(obj)
        referents = gc.get_referents(obj)
        references += len(referents)
        pending.extend(each for each in referents if not gc.is_tracked(each))
    while pending:
        obj = pending.pop()
        held += sys.getsizeof(obj)
        pending.extend(each for each in gc.get_referents(obj) if not gc.is_tracked(each))
    return Heap(objects, references, held)


def warmed(seam: Seam) -> Seam:
    """``seam`` with its first-reach costs already paid, for :func:`live_graph`.

    That instrument opens its window before the first run, so a memo filled on
    first reach anywhere under the seam would read as a survivor of the measured
    structure rather than as what it is. Warming outside the window puts every
    one of them in the baseline the sample is compared against, which is what
    :func:`retained` already does for itself.
    """
    for _ in range(WARMUP):
        seam(_unsampled)
    return seam


OWN_INTERPRETER_ATTRIBUTE: Final = "__parallax_own_interpreter__"
"""What marks a collected item as needing an interpreter of its own.

Named here and read by the runner's collection hook, which cannot import this
module: the hook loads before any surface directory reaches the path. The two
spellings are held together by `tools/check_instrument_access.py` rather than by
an import."""


_MEASUREMENTS: Final[dict[str, Callable[[], None]]] = {}
"""Every measurement a child can be asked for, filled by the decorator below as
the defining module is imported — in the parent, where the entry is never read,
and in the child, where it is the only one that matters."""


_COVERAGE_VARIABLES: Final = (
    "COV_CORE_SOURCE",
    "COV_CORE_CONFIG",
    "COV_CORE_DATAFILE",
    "COVERAGE_PROCESS_START",
)
"""What activates a coverage tracer inside a subprocess, by the names
``pytest-cov`` and ``coverage`` publish for it."""


def _child_environment() -> dict[str, str]:
    """The parent's environment, less what would trace the child.

    The paths are carried over because the runner rather than the interpreter is
    what puts this test tree on the path, and a child started from a module file
    sees only that module's own directory.

    The tracer is dropped because the child exists to measure without one: a
    traced child allocates per executed line inside every window, which is the
    cost and the distortion the parent already steps around, and the readings it
    would take are the parent's readings again rather than cheaper ones. Nothing
    is lost by it — the production lines a measurement drives are the same lines
    the suites grading their behavior already cover.
    """
    inherited = {
        name: value for name, value in os.environ.items() if name not in _COVERAGE_VARIABLES
    }
    return inherited | {"PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry)}


def in_a_child_interpreter(measurement: Callable[[], None]) -> Callable[[], None]:
    """``measurement``, taken in an interpreter that has loaded only what it needs.

    What the module docstring states as a contract, applied to one measurement:
    the reading becomes a property of the seam rather than of whatever else the
    runner happened to load beside it.

    The child re-runs the defining module as a script, naming the measurement,
    and asserts for itself; the parent reports the child's whole output when it
    exits nonzero. A module holding one of these MUST therefore answer
    :func:`serve_one_measurement` from its ``__main__``, and MUST leave nothing
    but definitions to run at import — the child pays for its import before every
    reading it takes.
    """
    _MEASUREMENTS[measurement.__name__] = measurement
    script = measurement.__globals__["__file__"]

    @wraps(measurement)
    def taken_in_a_child() -> None:
        report = subprocess.run(
            [sys.executable, script, measurement.__name__],
            capture_output=True,
            text=True,
            check=False,
            env=_child_environment(),
        )
        if report.returncode != 0:
            raise AssertionError(
                f"{measurement.__name__} failed in its child interpreter "
                f"(exit {report.returncode})\n{report.stdout}{report.stderr}"
            )

    setattr(taken_in_a_child, OWN_INTERPRETER_ATTRIBUTE, True)
    return taken_in_a_child


def takes_its_own_interpreter(test: object) -> bool:
    """Whether ``test`` is a measurement :func:`in_a_child_interpreter` wrapped.

    What the runner's collection hook reads to classify an item `cost`
    (`core/spec/language-testing.md` §5). The attribute rather than the registry
    is what answers it: the registry is keyed by name and holds the measurement,
    while what the runner collected is the wrapper standing in for it.
    """
    return getattr(test, OWN_INTERPRETER_ATTRIBUTE, False) is True


def serve_one_measurement(name: str) -> None:
    """Take the one measurement ``name`` names, for the child
    :func:`in_a_child_interpreter` starts.

    The registered function is the one the decorator wrapped rather than the
    wrapper, so the child takes the reading instead of starting a child of its
    own.
    """
    _MEASUREMENTS[name]()
