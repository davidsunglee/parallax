"""What a run of code costs in memory, from four directions at once.

Four instruments, because an object can appear without any byte reaching the
allocator, a borrowed graph can be kept without either number moving, and a
structure built and dropped between two points of a longer sequence is gone from
every reading taken at the end of it:

**Bytes allocated.** :func:`allocation` grades retention over repeated runs, so a
byte kept per run cannot hide in the floor, beside the high-water rise after
:func:`tracemalloc.reset_peak`, which is what makes an object born and freed
inside the window visible. :func:`first_run` grades those two numbers for the
first run a process makes, because a lazily built cache is paid once and a warmed
measurement would never see it.

**Objects that survive.** :func:`survivors` grades the GC-tracked objects alive
at a sample point that were not alive before the sequence began. CPython serves
some construction from a free list, which reaches no allocator and moves no byte
counter — a warmed ``lambda: []`` measures as zero bytes — and a list, a
populated dict, or a bound method is a container the collector tracks, so the
survivor count sees what the byte count cannot.

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

Every reading is Python-level — bytes are what ``tracemalloc`` traces through
CPython's allocator and objects are what the collector tracks — so memory held
outside that allocator is in none of them.

**Warming: three warm themselves, one is warmed from outside, and one must not
be.** :func:`allocation` runs its seam :data:`WARMUP` times before opening either
of its windows, :func:`retained` warms both its seam and its sampler inside its
own call, and :func:`high_water` warms its span the same way. :func:`survivors`
opens its window before the first run, so a seam that fills a memo on first reach
is handed to it through :func:`warmed`, which puts those memos in the baseline
the sample is compared against rather than in the sample. The one that must not
be warmed is :func:`first_run`, whose subject is the first run a process makes:
repeating it would move what it grades to before the reading.

**Where a reading is taken.** Every instrument here reads the whole process and
not the seam alone — the survivor sample lists each tracked object, and every
collection walks all of them. What a reading costs, and the floor it is read
against, therefore belong to the interpreter rather than to what is being
measured. :func:`in_a_child_interpreter` is how a suite says so: the measurement
is taken in a process that has loaded only what it needs, which is what leaves
one reading comparable with the same reading taken beside anything else, and
whose hashing is pinned, which is what leaves it comparable with the same reading
taken again. Every reader refuses to run in a process that boundary did not
start, so a reading reached by any route but the boundary fails where it is taken
rather than passing against a shared heap.

The ``tests/unit`` cost suites read these, which is what puts them here beside
them; ``tools/snapshot_delivery_reading.py`` reads them too, and names this
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
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Final

__all__ = [
    "OWN_INTERPRETER_ATTRIBUTE",
    "OWN_INTERPRETER_VARIABLE",
    "REPEATS",
    "WARMUP",
    "Seam",
    "Span",
    "allocation",
    "first_run",
    "high_water",
    "in_a_child_interpreter",
    "require_own_interpreter",
    "retained",
    "serve_one_measurement",
    "survivors",
    "takes_its_own_interpreter",
    "untraced",
    "warmed",
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

Two marks rather than :data:`Seam`'s one, because what is being read is a
DIFFERENCE ACROSS the region rather than a state at one point in it — the
high-water one span reached above what was already alive where it opened. The
region is a middle of
the sequence rather than its innermost point, so the sequence keeps running after
``closed`` and whatever it has to unwind is outside the reading.
"""


def _unsampled() -> None:
    """The sampler a byte measurement passes: the sequence runs unobserved."""


OWN_INTERPRETER_VARIABLE: Final = "PARALLAX_OWN_INTERPRETER"
"""The environment variable that marks a process as an interpreter of its own,
set in the environment of every child a reading is taken in."""


def require_own_interpreter(reader: str) -> None:
    """Refuse ``reader`` in a process no child-interpreter boundary started.

    Every reader calls this on entry, before any window opens, so it moves no
    reading.
    """
    if OWN_INTERPRETER_VARIABLE not in os.environ:
        raise RuntimeError(
            f"{reader} reads the whole interpreter, so it needs an interpreter of its "
            f"own: take it inside a test decorated with @in_a_child_interpreter, whose "
            f"child sets {OWN_INTERPRETER_VARIABLE}"
        )


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
    require_own_interpreter("allocation")
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
    require_own_interpreter("first_run")
    gc.collect()
    gc.collect()
    before, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    work(_unsampled)
    current, peak = tracemalloc.get_traced_memory()
    return current - before, peak - current


def survivors(seam: Seam) -> list[object]:
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

    The instrument discounts itself: the two heap listings, the identity set, and
    the list they were collected in are the only objects the comparison cannot
    avoid creating.
    """
    require_own_interpreter("survivors")
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
    return [obj for obj in heap if id(obj) not in before and id(obj) not in instruments]


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
    require_own_interpreter("retained")
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
    require_own_interpreter("high_water")
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


def warmed(seam: Seam) -> Seam:
    """``seam`` with its first-reach costs already paid, for :func:`survivors`.

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


_HASH_SEED: Final = "0"
"""What the child's string and bytes hashing is pinned to.

Every byte figure here is read over containers the interpreter sizes by hash. A
set's fill and a dictionary's probe sequence follow the hashes of the keys put
into them, and those hashes are salted per process unless this is set, so the
same structure occupies a different number of bytes in one child than in the
next and a difference between two arms carries that variance rather than
cancelling it. The seam is held fixed by the caller and the interpreter is the
child's own; this is what holds the last thing that varies, and it is what lets
a reading be an exact equality rather than a tolerance."""


_SERVED_RECORD_VARIABLE: Final = "PARALLAX_SERVED_RECORD"
"""The environment variable naming the file a child records the measurement it
served in, which the parent reads once the child has exited."""


def _child_environment(record: str) -> dict[str, str]:
    """The parent's environment, less what would trace the child, with its
    hashing pinned, marked as an interpreter of its own, and naming the file
    ``record`` it reports what it served in.

    The paths are carried over because the runner rather than the interpreter is
    what puts this test tree on the path, and a child started from a module file
    sees only that module's own directory.

    The seed is pinned for the reason :data:`_HASH_SEED` gives, and pinned HERE
    rather than by each measurement because every reading any child takes is a
    reading of a heap that hash order sized.

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
    return inherited | {
        "PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry),
        "PYTHONHASHSEED": _HASH_SEED,
        OWN_INTERPRETER_VARIABLE: "1",
        _SERVED_RECORD_VARIABLE: record,
    }


def in_a_child_interpreter(measurement: Callable[[], None]) -> Callable[[], None]:
    """``measurement``, taken in an interpreter that has loaded only what it needs.

    What the module docstring states as a contract, applied to one measurement:
    the reading becomes a property of the seam rather than of whatever else the
    runner happened to load beside it, or of the hash seed the process taking it
    started with.

    The child re-runs the defining module as a script, naming the measurement,
    and asserts for itself; the parent reports the child's whole output when it
    exits nonzero, and fails a child that exits cleanly without recording that it
    served the measurement it was asked for. A module holding one of these MUST
    therefore answer :func:`serve_one_measurement` from its ``__main__``, and
    MUST leave nothing but definitions to run at import — the child pays for its
    import before every reading it takes.
    """
    _MEASUREMENTS[measurement.__name__] = measurement
    script = measurement.__globals__["__file__"]

    @wraps(measurement)
    def taken_in_a_child() -> None:
        # Imported here, in the parent, because an import at module level would
        # load it into every child before the first reading it takes.
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            record = os.path.join(scratch, "served")
            report = subprocess.run(
                [sys.executable, script, measurement.__name__],
                capture_output=True,
                text=True,
                check=False,
                env=_child_environment(record),
            )
            served = _served(record)
        if report.returncode != 0:
            raise AssertionError(
                f"{measurement.__name__} failed in its child interpreter "
                f"(exit {report.returncode})\n{report.stdout}{report.stderr}"
            )
        if served != measurement.__name__:
            raise AssertionError(
                f"{measurement.__name__}'s child interpreter exited without serving "
                f"it, so {script} likely has no `__main__` entry point calling "
                f"serve_one_measurement(sys.argv[1])\n{report.stdout}{report.stderr}"
            )

    setattr(taken_in_a_child, OWN_INTERPRETER_ATTRIBUTE, True)
    return taken_in_a_child


def _served(record: str) -> str | None:
    """The measurement a child recorded serving in ``record``, if it served one."""
    try:
        with open(record) as written:
            return written.read()
    except FileNotFoundError:
        return None


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
    own. What it served is recorded only once the measurement has returned, so
    the record is outside every window the measurement reads.
    """
    _MEASUREMENTS[name]()
    with open(os.environ[_SERVED_RECORD_VARIABLE], "w") as record:
        record.write(name)
