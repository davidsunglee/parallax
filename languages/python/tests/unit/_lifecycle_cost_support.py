"""The instruments the lifecycle cost suites measure with, and the seam values
they drive.

`core/spec/m-execution-lifecycle.md` states cost as a contract twice over: what
an operation nobody observes may allocate, and what an observed one may still
hold once it has finished. The first is graded in
``test_execution_lifecycle_allocation_shape.py`` and the second in
``test_execution_lifecycle_retention.py``, both through the seam a real
operation drives rather than through a whole query — the read AROUND the seam
allocates the driver SQL, the binds, the rows, and the graph, which end to end
swamps the seam's own cost by three orders of magnitude.

Three instruments, because an object can appear without any byte reaching the
allocator, and a borrowed graph can be kept without either number moving:

**Bytes allocated.** :func:`allocation` grades retention over repeated runs, so a
byte kept per run cannot hide in the floor, beside the high-water rise after
:func:`tracemalloc.reset_peak`, which is what makes an object born and freed
inside the window visible. :func:`first_run` grades those two numbers for the
first run a process makes, because a lazily built cache is paid once and a warmed
measurement would never see it.

**Objects.** :func:`survivors` grades the GC-tracked objects alive at a sample
point that were not alive before the sequence began. CPython serves some
construction from a free list, which reaches no allocator and moves no byte
counter — a warmed ``lambda: []`` measures as zero bytes — and a list, a
populated dict, or a bound method is a container the collector tracks, so this
instrument sees what the byte count cannot.

**Bytes still reachable.** :func:`retained` grades the bytes alive at a sample
point that were not alive before the sequence began. It is the only one of the
three that sees a whole graph a live scope kept: a survivor count classified by
type cannot see a borrowed list of rows, and an allocation count cannot see a
value the window never allocated. What it costs is that the value has to be
built inside the window, which is what the caller arranges.

Outside all three, stated rather than implied. An object born and dropped inside
a single call that the free list also serves: no sample point holds it and no
counter moves. And an UNTRACKED survivor: :func:`gc.get_objects` answers only
what the collector tracks, so a retained empty dictionary, all-immutable tuple,
or integer is invisible to the survivor sample. The instruments are read
together for that reason — the byte counts see a retained integer the survivor
sample cannot, and the survivor sample sees a free-list list the byte counts
cannot.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore — the same convention the private
`parallax.snapshot.handle` modules follow. Never imported by production code.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Final

from parallax.core.metamodel import EntityIdentity
from parallax.core.sql_gen import LoweredStatement

__all__ = [
    "AFFECTED",
    "REPEATS",
    "STATEMENT",
    "TARGET",
    "WARMUP",
    "Seam",
    "allocation",
    "first_run",
    "retained",
    "rows",
    "survivors",
]

TARGET: Final = EntityIdentity("parallax.compatibility", "Account")
"""A namespaced Entity whose canonical spelling has to be BUILT, which is what
makes a seam that spells its target measure as an allocation."""

STATEMENT: Final = LoweredStatement("select id from account where id = $1", (7,))

AFFECTED: Final = 5_000
"""A driver's affected-row count, past the interpreter's small-integer cache."""

WARMUP: Final = 200
"""Runs before every window, so import, cache-fill, and first-call costs are outside it."""

REPEATS: Final = 200
"""Runs inside the retention window. The floor is the harness's own handful of
bytes, so anything kept per run — the smallest object is tens of bytes — clears
it by two orders of magnitude, and "under one byte per run" needs no threshold
anyone has to justify."""

type Seam = Callable[[Callable[[], None]], None]
"""One sequence through the seam, calling its argument at its innermost point.

Sampling is a parameter rather than a second copy of the sequence, so the bytes
and the survivors are graded over the same code.
"""


def rows(count: int) -> list[dict[str, object]]:
    """``count`` rows shaped as a driver hands them back."""
    return [{"id": index} for index in range(count)]


def _unsampled() -> None:
    """The sampler a byte measurement passes: the sequence runs unobserved."""


@contextmanager
def _untraced() -> Generator[None]:
    """A window with the line tracer uninstalled.

    Under branch coverage the tracer allocates per executed line and keeps what
    it records, which would be the only thing a measurement inside the window
    saw. Every line inside a window is covered by the suites grading its
    behavior.
    """
    tracer = sys.gettrace()
    sys.settrace(None)
    try:
        yield
    finally:
        sys.settrace(tracer)


def allocation(work: Seam) -> tuple[int, int]:
    """Bytes ``work`` keeps over :data:`REPEATS` runs, and bytes one run
    allocates and frees again.

    The two are measured in separate windows because they need opposite things:
    retention needs repetition, so a byte kept per run cannot hide in the floor,
    while a transient allocation is a high-water mark that repetition does not
    accumulate.
    """
    with _untraced():
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


def survivors(seam: Seam) -> list[object]:
    """GC-TRACKED objects alive at ``seam``'s innermost point that were not alive
    before it began.

    Both snapshots and the sampler itself are built before the first one is
    taken, so the only objects the comparison has to discount are the two it
    cannot avoid: the identity set and the sampled list. What remains is every
    survivor rather than the ones of any chosen type, so a caller reading the
    whole count sees a live scope's own state whatever built it, and a caller
    classifying by type asks a narrower question of the same sample.
    """
    sampled: list[list[object]] = []

    def sample() -> None:
        sampled.append(gc.get_objects())

    with _untraced():
        gc.collect()
        before = {id(obj) for obj in gc.get_objects()}
        seam(sample)
    live = sampled[0]
    return [obj for obj in live if id(obj) not in before and obj is not live and obj is not before]


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

    with _untraced():
        for _ in range(WARMUP):
            seam(_unsampled)
        seam(sample)
        gc.collect()
        before, _ = tracemalloc.get_traced_memory()
        seam(sample)
    return sampled[1] - before
