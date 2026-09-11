"""One storage layout's reading of the production materialization path, taken in
a child interpreter.

The half of `tools/snapshot_materialization_overhead.py` that measures. It is a
script rather than a function that report calls: every instrument here reads the
whole process, so a reading is only a property of its own subject when it is taken
in an interpreter that has loaded nothing else, and the report starts one child
per (minor, layout) naming this file. Every figure of one layout is measured in
that one child — a byte reading is read against a floor the interpreter decides,
so two arms compared across two processes would be compared across two floors.

Keeping it out of the report's own module is structural. The `dbfree` suite that
imports tools whole would reach any instrument imported there, and
`core/spec/language-testing.md` §5 requires a whole-interpreter reading to be
reachable only through an entry point that acquires an interpreter of its own. So
the report imports no instrument at all — the reading lives here, this file is
imported by nothing, and the only thing that runs it is a child.

This file therefore also owns the module-identity refusal for the instruments.
``memory_instruments`` is a generic name on a path this process does not own, and
a module of that name already in ``sys.modules`` wins before any path entry is
consulted, so a different sampling recipe would still produce numbers and they
would not be the numbers the recorded baseline is stated over.

The answer crosses back as one line of JSON on stdout, encoded by the report's own
:func:`~snapshot_materialization_overhead.payload` so the encoder and the decoder
stay in one place.
"""

from __future__ import annotations

import cProfile
import gc
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter
from typing import Final, cast

from parallax.core.entity._layout import CatalogedModel
from parallax.snapshot import prepare_model
from parallax.snapshot.handle._publication import read_projection

WORKSPACE: Final = Path(__file__).resolve().parents[1]
SUPPORT: Final = WORKSPACE / "tests" / "unit"
INSTRUMENT_MODULE: Final = SUPPORT / "memory_instruments.py"

sys.path.insert(0, str(SUPPORT))

import memory_instruments  # noqa: E402 - after the sys.path setup above

if Path(memory_instruments.__file__ or "").resolve() != INSTRUMENT_MODULE:
    raise ImportError(
        f"this reading is taken through {INSTRUMENT_MODULE}, but "
        f"'memory_instruments' resolved to {memory_instruments.__file__}"
    )

from _snapshot_materialization_support import (  # noqa: E402 - after the sys.path setup above
    LAYOUTS,
    PROJECTIONS_PER_BATCH,
    ROWS_PER_BATCH,
    Layout,
    batch,
    compiled_levels,
    fetch_plan,
    metamodel,
    prepared_levels,
    query,
    rows_per_level,
    verify,
    workload,
)
from memory_instruments import (  # noqa: E402 - after the sys.path setup above
    WARMUP,
    Seam,
    closure,
    retained,
    untraced,
)

import snapshot_graph_overhead  # noqa: E402 - after the sys.path setup above
from snapshot_materialization_overhead import (  # noqa: E402 - after the sys.path setup above
    CONTRIBUTORS,
    REPETITIONS,
    Reading,
    payload,
)

PREPARATION_REPETITIONS: Final = 20
"""Timed repetitions of model preparation and of compilation. Fewer than a
per-row operation needs, because each one derives a whole catalog or a whole
statement and the two are reported in milliseconds."""

EDITION: Final = "snapshot-materialization-report"


def _nothing() -> None:
    """The sampler an unobserved run passes."""


def _elapsed_ns(work: Callable[[], None], *, repetitions: int, warmup: int) -> float:
    """Mean nanoseconds one ``work`` takes."""
    with untraced():
        for _ in range(warmup):
            work()
        start = perf_counter()
        for _ in range(repetitions):
            work()
        elapsed = perf_counter() - start
    return elapsed * 1e9 / repetitions


def peak(seam: Seam) -> int:
    """Bytes the high-water mark of one run of ``seam`` stands above the floor it
    started from.

    ``memory_instruments.allocation``'s transient half cannot answer this for
    this seam, and its own contract says why: it reads the current total as soon
    as the run RETURNS, which is the floor again only for a seam that leaves
    nothing behind. A batch leaves a sealed graph, so the total still holds it and
    whatever else is waiting for the collector — and subtracting that from the
    high-water mark answers neither what the run reached nor what it freed again.
    The floor is therefore taken and collected for BEFORE the run, and what the
    graph keeps is subtracted from the answer rather than from the sample
    (:attr:`~snapshot_materialization_overhead.Reading.transient_bytes`).
    """
    with untraced():
        for _ in range(WARMUP):
            seam(_nothing)
        gc.collect()
        gc.collect()
        floor, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        seam(_nothing)
        _, high_water = tracemalloc.get_traced_memory()
    return high_water - floor


class _Prepared:
    """One layout's prepared model, compiled reads and the levels bound from
    them, plus the fixture rows every batch converts.

    Built once, outside every window: the rows in particular, so a reading counts
    the position a converted row takes and never the leaf it references."""

    __slots__ = ("bound", "meta", "model", "plan", "reads", "rows")

    def __init__(self, layout: Layout) -> None:
        self.meta = metamodel(layout)
        self.model = read_projection(prepare_model(workload(layout), edition=EDITION)).model
        self.plan = fetch_plan(query(self.meta), self.meta)
        self.reads = compiled_levels(self.plan, self.meta)
        self.bound = prepared_levels(self.model, self.reads)
        self.rows = rows_per_level(self.model, self.plan, self.reads)

    def run(self) -> None:
        batch(self.model, self.plan, self.bound, self.rows)

    def seam(self) -> Seam:
        def run(sample: Callable[[], None]) -> None:
            graph = batch(self.model, self.plan, self.bound, self.rows)
            sample()
            assert graph is not None

        return run


def _compiled_seam(prepared: _Prepared) -> Seam:
    """The compiled reads and the levels bound from them, derived INSIDE the
    window and held at the sample, with the plan they were derived from already
    unreachable.

    Binding is inside it because what a bind derives is state one compiled read
    owns for as long as it lives, which is exactly what this figure reports."""

    def run(sample: Callable[[], None]) -> None:
        reads = compiled_levels(fetch_plan(query(prepared.meta), prepared.meta), prepared.meta)
        bound = prepared_levels(prepared.model, reads)
        sample()
        assert bound is not None

    return run


def _catalog_seam(prepared: _Prepared) -> Seam:
    """The layout catalog derived inside the window over a Metamodel formed
    outside it."""

    def run(sample: Callable[[], None]) -> None:
        cataloged = CatalogedModel(prepared.meta)
        sample()
        assert cataloged is not None

    return run


def _counts(prepared: _Prepared) -> dict[str, int]:
    """Calls each named contributor took over ONE batch, outside every timed
    repetition.

    Attributed by defining file and function rather than by name alone, because
    one of the sites is a ``__post_init__`` and only its file says whose."""
    profile = cProfile.Profile()
    profile.enable()
    prepared.run()
    profile.disable()
    profile.create_stats()
    stats = cast(
        "dict[tuple[str, int, str], tuple[int, int, float, float, object]]",
        profile.stats,
    )
    counted = {contributor.label: 0 for contributor in CONTRIBUTORS}
    for (filename, _line, function), (_calls, primitive, *_rest) in stats.items():
        for contributor in CONTRIBUTORS:
            if function == contributor.function and filename.endswith(contributor.module):
                counted[contributor.label] += primitive
    return counted


def _catalog_census(prepared: _Prepared) -> tuple[int, int, int]:
    """What one exact Entity layout holds without crossing into another, and how
    many layouts the catalog carries.

    A closure rather than a difference: two totals over one catalog share almost
    every term and cancel whatever they share, where a claim about per-layout
    state needs one participant's own total. The other layouts are the boundary,
    so what comes back is what this one holds and not what it reaches through
    them."""
    cataloged = CatalogedModel(prepared.meta)
    layouts = [cataloged.layouts.entity(entity.identity) for entity in prepared.meta.entities]
    census = closure(layouts[0], layouts)
    return len(layouts), census.tracked, census.references


def measure(layout: Layout) -> Reading:
    """``layout``'s whole reading, taken in this interpreter."""
    prepared = _Prepared(layout)
    verify(
        prepared.model,
        prepared.plan,
        batch(prepared.model, prepared.plan, prepared.bound, prepared.rows),
    )

    model = workload(layout)

    def prepare() -> None:
        prepare_model(model, edition=EDITION)

    def compile_levels() -> None:
        reads = compiled_levels(fetch_plan(query(prepared.meta), prepared.meta), prepared.meta)
        prepared_levels(prepared.model, reads)

    def bind_levels() -> None:
        prepared_levels(prepared.model, prepared.reads)

    selection_ns = _elapsed_ns(prepare, repetitions=PREPARATION_REPETITIONS, warmup=5)
    compile_ns = _elapsed_ns(compile_levels, repetitions=PREPARATION_REPETITIONS, warmup=5)
    bind_ns = _elapsed_ns(bind_levels, repetitions=PREPARATION_REPETITIONS, warmup=5)
    batch_ns = _elapsed_ns(prepared.run, repetitions=REPETITIONS, warmup=5)

    tracemalloc.start()
    try:
        retained_graph = retained(prepared.seam())
        peak_bytes = peak(prepared.seam())
        prepared_bytes = retained(_compiled_seam(prepared))
        catalog_bytes = retained(_catalog_seam(prepared))
    finally:
        tracemalloc.stop()
    catalog_layouts, tracked, references = _catalog_census(prepared)
    secondary_build, secondary_merge = snapshot_graph_overhead.timings(
        snapshot_graph_overhead.cells(snapshot_graph_overhead.REPRESENTATIVE)
    )
    return Reading(
        layout=layout,
        warmup=WARMUP,
        rows=ROWS_PER_BATCH,
        projections=PROJECTIONS_PER_BATCH,
        selection_ns=selection_ns,
        selection_decode_ns=0.0,
        compile_ns=compile_ns,
        compile_decode_ns=bind_ns,
        batch_ns=batch_ns,
        retained_graph_bytes=retained_graph,
        peak_bytes=peak_bytes,
        prepared_bytes=prepared_bytes,
        prepared_reads=sum(1 for read in prepared.reads if read is not None),
        layout_decode_bytes=0,
        catalog_bytes=catalog_bytes,
        catalog_layouts=catalog_layouts,
        catalog_tracked=tracked,
        catalog_references=references,
        counts=_counts(prepared),
        secondary_build_s=secondary_build,
        secondary_merge_s=secondary_merge,
        secondary_projections=(
            snapshot_graph_overhead.REPRESENTATIVE * snapshot_graph_overhead.PROJECTIONS_PER_CELL
        ),
    )


def _layout_named(name: str) -> Layout | None:
    return next((layout for layout in LAYOUTS if layout == name), None)


def main(argv: Sequence[str]) -> int:
    """Take the one layout ``argv`` names and answer with its reading."""
    layout = _layout_named(argv[0]) if len(argv) == 1 else None
    if layout is None:
        print(
            f"usage: python tools/snapshot_materialization_reading.py <{'|'.join(LAYOUTS)}>",
            file=sys.stderr,
        )
        return 2
    print(payload(measure(layout)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
