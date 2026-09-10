"""What a production Snapshot read spends turning returned rows into a sealed
graph, under both storage layouts and on every supported CPython minor.

The representative workload — a table-per-hierarchy family with an abstract
middle, nested One and Many Value Objects at two depths, every declarable Neutral
Type as an Attribute and again as a document leaf, duplicate logical nodes
through a narrowed view, three view slots and a back-reference — driven through
the shipped loop from ``CompiledRead.materialize_row`` to ``GraphBuilder.seal``.
The workload itself is ``tests/unit/_snapshot_materialization_support.py``, which
the gated scaling regression drives through the same functions, so the report and
its grader measure one workload rather than two.

It is a `report`: it passes no verdict and joins no aggregate, because elapsed
time is a property of the machine that ran it and a total in bytes moves with the
interpreter. The SHAPE of the claim is gated instead, in
``tests/unit/test_snapshot_materialization_scaling.py``, which proves prepared
state is fixed by the model's exact layouts and the compiled reads rather than by
rows or graphs. What has been read off this, and under what conditions, is
``docs/snapshot-materialization-baseline.md``.

**What is inside the clock and what is not.** Model preparation and compilation
are timed once each and reported separately. The repeated batch holds exactly what
a read pays per statement of rows: row materialization, per-row level context,
conversion, the observation every hydrating row takes, view fan-back, and sealing.
Fixture construction, SQL execution, merge, classification, and Typed or Wire
publication are outside it — the fixture rows are built before any window opens,
so a reading counts the position a row takes and not the leaf it references.

**Compilation cannot be inside the batch.** A child level's ``compile_read`` runs
between gathering its parents' keys and converting its rows, so timing
``build_graph`` as one unit would recompile four statements per repetition and
call the result throughput. The batch therefore compiles once, against the
fixture's own keys, and still gathers those keys per repetition because production
does.

**Where a reading is taken, and where it is not.** This module IMPORTS no
instrument. Every reading is taken in a child, by
``tools/snapshot_materialization_reading.py``, which is the script a child runs
and the one place ``memory_instruments`` is reached from; this module spawns the
children, decodes what they answer, and judges only whether the matrix is
complete. `core/spec/language-testing.md` §5 asks that structurally rather than by
inspection: an import that is not here is a route no guard has to answer for.

**The secondary workload** is ``tools/snapshot_graph_overhead.py``'s own plan —
the direct-converter shape the 64-graph cost item is built over — timed in the
same child so its per-projection rate is comparable with the production one. The
cost ITEM is never re-run from a tool: its duration is read from
``tests/_support/cost_durations.json`` and printed as what it last cost.

Run it through `just python-report-snapshot-materialization`.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NamedTuple, cast

WORKSPACE: Final = Path(__file__).resolve().parents[1]
"""The Python workspace root — where a child interpreter of another minor is
resolved from, and where the supported-minor range is declared."""

SUPPORT: Final = WORKSPACE / "tests" / "unit"
"""The one directory this report names, so it can read the workload the gated
suite reads.

It is support code for `tests/unit/`, whose own suites are its other readers, and
`core/spec/language-testing.md` §4 keeps single-surface support code inside its
surface — a report is no surface of its own, so picking it up here does not move
it. The reach stays deliberate and one-way: the path is spelled once, here, and
nothing under `tests/` knows this file exists.
"""

READING_SCRIPT: Final = Path(__file__).resolve().parent / "snapshot_materialization_reading.py"
"""The script one child runs: the half of this report that takes a reading."""

SUPPORT_MODULE: Final = SUPPORT / "_snapshot_materialization_support.py"
"""The exact file the workload is read off.

A generic name on a path this process does not own, so prepending the directory
is only half of what makes the import deterministic: a module of that name
already in :data:`sys.modules` wins before any path entry is consulted. The report
therefore states which file it means and refuses to run against any other, because
the alternative failure is silent — a different workload would still produce
numbers, and they would not be the numbers the recorded baseline is stated over.
"""

DURATIONS: Final = WORKSPACE / "tests" / "_support" / "cost_durations.json"
COST_ITEM: Final = (
    "tests/unit/test_snapshot_graph_retention.py::"
    "test_a_models_layout_catalog_is_the_same_size_after_one_graph_and_after_sixty_four"
)
"""The 64-graph cost item, and the file recording what it last cost. Read rather
than re-run: the item owns its own instruments and its duration is a fact about
the class's balance, not a measurement this report may retake."""

sys.path.insert(0, str(SUPPORT))

import _snapshot_materialization_support  # noqa: E402

if Path(_snapshot_materialization_support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(
        f"this report measures over {SUPPORT_MODULE}, but "
        f"'_snapshot_materialization_support' resolved to "
        f"{_snapshot_materialization_support.__file__}"
    )

from _snapshot_materialization_support import (  # noqa: E402
    LAYOUTS,
    PROJECTIONS_PER_BATCH,
    ROWS_PER_BATCH,
)

REPETITIONS: Final = 20
"""Timed batches behind the steady-state figure. Wall clock is recorded for
visibility alone, so this buys a stable mean rather than a distribution."""

SUPPORTED_MINORS: Final = 2
"""How many CPython minors are supported at once — `spec/python.md` §10's policy
is "the latest minor + one prior minor", which makes the declared
``requires-python`` floor the prior one and fixes the range's width above it."""

CURRENT_MINOR: Final = f"{sys.version_info.major}.{sys.version_info.minor}"


class Contributor(NamedTuple):
    """One call the profiled batch counts, and where it is defined.

    Counted by defining site rather than by name alone: one of the sites below is
    a ``__post_init__``, which only its file identifies, and a count attributed to
    the wrong module would be read as a per-row cadence that is not there.
    """

    label: str
    module: str
    function: str
    per_row: bool
    """Whether this site rebuilds, once per row, something the compiled read
    already fixed. The sum over these is what the decision gate reads."""


CONTRIBUTORS: Final = (
    Contributor("decode_canonical_wire", "_codec.py", "decode_canonical_wire", False),
    Contributor("encode_wire", "_codec.py", "encode_wire", False),
    Contributor("matches_neutral_type", "_neutral.py", "matches_neutral_type", False),
    Contributor("admits_stored_scalar", "__init__.py", "admits_stored_scalar", False),
    Contributor(
        "reduce_declared_members_classified",
        "_document.py",
        "reduce_declared_members_classified",
        False,
    ),
    Contributor(
        "decode_occurrence_classified", "_document.py", "decode_occurrence_classified", False
    ),
    Contributor("occurrence_shape", "_shape.py", "occurrence_shape", False),
    Contributor("materialize_row", "_compile.py", "materialize_row", False),
    Contributor("convert_row (result_keys dict)", "_convert.py", "convert_row", True),
    Contributor("LevelContext (fresh per row)", "_convert.py", "__post_init__", True),
    Contributor("attribute_reads (contract dict)", "_compile.py", "attribute_reads", True),
    Contributor(
        "_document_columns (projected frozenset)", "_convert.py", "_document_columns", True
    ),
    Contributor("observable_columns", "_convert.py", "observable_columns", False),
)
"""Every contributor the baseline names.

The last five are the containers whose inputs one compiled read already fixed and
which are rebuilt anyway. They are counted at the function that BUILDS each one
rather than as ``dict`` calls: ``dict(...)`` is a type call, which ``cProfile``
does not record at all, so counting the site is the only reading there is.
"""


class Reading(NamedTuple):
    """One storage layout's whole reading, as a child interpreter answers it."""

    layout: str
    warmup: int
    rows: int
    projections: int
    selection_ns: float
    """Total one-time selected-model preparation."""
    selection_decode_ns: float
    """Decode preparation WITHIN that total. Zero while no model-derived decode
    preparation exists, which is a statement about the code rather than a
    measurement that was skipped."""
    compile_ns: float
    """Total compiled-read preparation: the fetch plan and one ``compile_read``
    per level."""
    compile_decode_ns: float
    """Decode preparation the compiled read owns, within that total. Zero for the
    same reason."""
    batch_ns: float
    retained_graph_bytes: int
    peak_bytes: int
    prepared_bytes: int
    prepared_reads: int
    layout_decode_bytes: int
    """Immutable prepared decode state per exact Entity layout. Zero: no such
    state exists yet."""
    catalog_bytes: int
    catalog_layouts: int
    catalog_tracked: int
    catalog_references: int
    counts: Mapping[str, int]
    secondary_build_s: float
    secondary_merge_s: float
    secondary_projections: int

    @property
    def rows_per_second(self) -> float:
        return self.rows * 1e9 / self.batch_ns

    @property
    def microseconds_per_row(self) -> float:
        return self.batch_ns / 1e3 / self.rows

    @property
    def transient_bytes(self) -> int:
        """What one batch allocated and freed again on the way to the graph it
        kept: the high-water mark less the state that survives it.

        Derived rather than measured, because the two are one reading taken from
        both ends — measuring each against its own floor would let a batch be
        charged for its own product twice, or for none of it."""
        return self.peak_bytes - self.retained_graph_bytes

    @property
    def transient_bytes_per_row(self) -> float:
        return self.transient_bytes / self.rows

    @property
    def retained_bytes_per_projection(self) -> float:
        return self.retained_graph_bytes / self.projections

    @property
    def prepared_bytes_per_read(self) -> float:
        return self.prepared_bytes / self.prepared_reads

    @property
    def catalog_bytes_per_layout(self) -> float:
        return self.catalog_bytes / self.catalog_layouts

    @property
    def preparation_rows(self) -> float:
        """How many rows of steady-state work one whole preparation — model plus
        compiled reads — costs.

        The amortization figure a single reading can state. A repayment row count
        needs two readings and is computed in the baseline document by dividing
        the preparation this half added by the per-row time the other half saved;
        within one run there is no earlier half to divide by."""
        return (self.selection_ns + self.compile_ns) / (self.batch_ns / self.rows)

    @property
    def compile_rows(self) -> float:
        """The same for compiled-read preparation alone, which is what an
        execution pays rather than a process."""
        return self.compile_ns / (self.batch_ns / self.rows)

    @property
    def secondary_microseconds_per_projection(self) -> float:
        return self.secondary_build_s * 1e6 / self.secondary_projections

    @property
    def secondary_projections_per_second(self) -> float:
        return self.secondary_projections / self.secondary_build_s

    def rebuilt_per_row(self) -> float:
        """Containers the conforming batch rebuilt per row whose inputs one
        compiled read already fixed."""
        return sum(self.counts[c.label] for c in CONTRIBUTORS if c.per_row) / self.rows


type Cell = Reading | str
"""One matrix position: a reading, or why there is none."""

type Matrix = dict[str, dict[str, Cell]]
"""Every reading, by runtime and then by storage layout."""


# --------------------------------------------------------------------------- #
# The matrix: one child per (minor, layout), one runtime at a time.            #
# --------------------------------------------------------------------------- #


def supported_minors() -> tuple[str, ...]:
    """Every CPython minor the workspace declares support for, oldest first.

    Derived from ``requires-python`` and from the support policy
    (`spec/python.md` §10, "the latest minor + one prior minor"), and from
    nothing about the interpreter taking the reading. The declared floor is the
    prior minor, so :data:`SUPPORTED_MINORS` closes the range above it.

    Closing it at ``sys.version_info`` instead is the one thing this must not do:
    run on any minor but the latest, the range would silently lose its top row —
    and a matrix short by a whole runtime looks COMPLETE to a check that walks
    the runtimes the matrix has.
    """
    declared = cast(
        "str",
        tomllib.loads((WORKSPACE / "pyproject.toml").read_text())["project"]["requires-python"],
    )
    floor = declared.removeprefix(">=").strip()
    parts = floor.split(".")
    readable = declared.startswith(">=") and len(parts) == 2 and all(p.isdigit() for p in parts)
    if not readable:
        raise SystemExit(
            f"the workspace declares requires-python {declared!r}: this report reads the "
            "supported range off a bare '>=<major>.<minor>' floor, and any other legal "
            "specifier is a range it would have to guess at"
        )
    major, minor = (int(part) for part in parts)
    return tuple(f"{major}.{minor + above}" for above in range(SUPPORTED_MINORS))


def _child_environment(runtime: str) -> dict[str, str]:
    """The environment a ``runtime`` child measures in.

    A child of this interpreter's own minor inherits the import path that reached
    here. A child of another minor must not: this process's ``site-packages``
    holds extension modules built for the wrong ABI, and its virtual environment
    would be resolved in preference to the one uv builds. So the path is dropped
    and the throwaway environment is named explicitly, which is also what keeps
    uv from rebuilding the workspace's own ``.venv`` at the other minor.
    """
    if runtime == CURRENT_MINOR:
        return os.environ | {"PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry)}
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    return environment | {
        "UV_PROJECT_ENVIRONMENT": str(
            Path(tempfile.gettempdir()) / f"parallax-snapshot-materialization-{runtime}"
        )
    }


def _child_command(runtime: str, layout: str) -> list[str]:
    """What starts one layout's child on ``runtime``."""
    script = str(READING_SCRIPT)
    if runtime == CURRENT_MINOR:
        return [sys.executable, script, layout]
    return ["uv", "run", "--frozen", "--python", runtime, "python", script, layout]


def in_a_child(runtime: str, layout: str) -> Cell:
    """``layout``'s reading on ``runtime``, or why there is none.

    One child per complete layout rather than per instrument: the isolation a
    whole-interpreter reading needs is a property of the process, and paying one
    process per instrument would buy nothing while making every reading's floor a
    different one.

    A child that fails answers with its own output rather than ending the run, so
    one unavailable runtime names every cell it cost instead of hiding the cells
    that would have followed it.

    ``memory_instruments.in_a_child_interpreter`` is the same pattern for a test,
    and is deliberately not reused: it raises on a non-zero exit and discards the
    child's output, where a report has to read the numbers back.
    """
    try:
        report = subprocess.run(
            _child_command(runtime, layout),
            capture_output=True,
            text=True,
            check=False,
            cwd=WORKSPACE,
            env=_child_environment(runtime),
        )
    except OSError as error:
        return f"the child could not be started: {error}"
    if report.returncode != 0:
        return f"the child exited {report.returncode}\n{report.stdout}{report.stderr}"
    return _decoded(report.stdout)


def _decoded(output: str) -> Cell:
    """One child's last output line as a reading, or why it is not one."""
    lines = output.strip().splitlines()
    if not lines:
        return "the child printed nothing"
    try:
        decoded = cast("dict[str, Any]", json.loads(lines[-1]))
        reading = Reading(**decoded)
        missing = [c.label for c in CONTRIBUTORS if c.label not in reading.counts]
        return f"the child counted no {missing[0]!r}" if missing else reading
    except (ValueError, KeyError, TypeError) as error:
        return f"the child's reading did not decode: {error}"


def payload(reading: Reading) -> str:
    """One reading as the line a child answers with.

    The encoding half of the child protocol, spelled here beside its decoder so
    the two cannot drift, and imported by the script the child runs.
    """
    return json.dumps(reading._asdict())


def missing_cells(matrix: Matrix, runtimes: Sequence[str]) -> list[str]:
    """Every position of ``runtimes`` by :data:`LAYOUTS` that carries no reading,
    each with its reason.

    Walked over the runtimes the caller ASKED for rather than the ones the matrix
    holds: a layout whose child died leaves a cell behind to notice, and a runtime
    nothing was ever run for leaves nothing at all, so a check reading the matrix's
    own keys would call the second one complete.
    """
    absent: list[str] = []
    for runtime in runtimes:
        cells = matrix.get(runtime, {})
        for layout in LAYOUTS:
            cell = cells.get(layout, "no child was run")
            if isinstance(cell, str):
                absent.append(f"CPython {runtime}, {layout}: {cell}")
    return absent


def recorded_cost_item_seconds() -> float | None:
    """What the 64-graph cost item last cost, as its own class's balance data
    records it — or absence, which is a fact about the file rather than about the
    item."""
    try:
        durations = cast("dict[str, float]", json.loads(DURATIONS.read_text()))
    except (OSError, ValueError):
        return None
    return durations.get(COST_ITEM)


# --------------------------------------------------------------------------- #
# Output.                                                                      #
# --------------------------------------------------------------------------- #


def _conditions(runtimes: Sequence[str], warmups: Sequence[int]) -> list[tuple[str, str]]:
    stated = ", ".join(str(count) for count in sorted(set(warmups)))
    return [
        ("Runtimes", f"CPython {', '.join(runtimes)} (this one is {platform.python_version()})"),
        ("Platform", f"{sys.platform}/{platform.machine()}"),
        ("Warm-up", f"{stated} unsampled runs before every window"),
        ("Timings", f"mean of {REPETITIONS} batches, taken untraced"),
        ("Batch", f"{ROWS_PER_BATCH} rows over {PROJECTIONS_PER_BATCH} projections, 5 levels"),
        ("Isolation", "one fresh child interpreter per (minor, layout)"),
        ("Excluded", "fixture rows, SQL execution, merge, classification, publication"),
    ]


_TIMING_HEADER: Final = (
    f"{'layout':<10} {'model prep ms':>14} {'decode':>7} {'compile ms':>11} {'decode':>7} "
    f"{'batch ms':>9} {'rows/s':>10} {'us/row':>8} {'prep rows':>10} {'compile rows':>13}"
)

_MEMORY_HEADER: Final = (
    f"{'layout':<10} {'retained B':>11} {'B/proj':>9} {'peak B':>10} {'transient B':>12} "
    f"{'transient/row':>14} {'prepared B':>11} {'B/read':>9} {'layout decode':>14} "
    f"{'catalog B/layout':>17}"
)


def _timing_line(reading: Reading) -> str:
    return (
        f"{reading.layout:<10} {reading.selection_ns / 1e6:>14.3f} "
        f"{reading.selection_decode_ns / 1e6:>7.3f} {reading.compile_ns / 1e6:>11.3f} "
        f"{reading.compile_decode_ns / 1e6:>7.3f} {reading.batch_ns / 1e6:>9.3f} "
        f"{reading.rows_per_second:>10,.0f} {reading.microseconds_per_row:>8.1f} "
        f"{reading.preparation_rows:>10,.0f} {reading.compile_rows:>13,.0f}"
    )


def _memory_line(reading: Reading) -> str:
    return (
        f"{reading.layout:<10} {reading.retained_graph_bytes:>11,} "
        f"{reading.retained_bytes_per_projection:>9.1f} {reading.peak_bytes:>10,} "
        f"{reading.transient_bytes:>12,} {reading.transient_bytes_per_row:>14,.0f} "
        f"{reading.prepared_bytes:>11,} {reading.prepared_bytes_per_read:>9,.0f} "
        f"{reading.layout_decode_bytes:>14,} {reading.catalog_bytes_per_layout:>17,.0f}"
    )


def _count_lines(readings: Sequence[Reading]) -> list[str]:
    header = f"{'contributor':<40} " + " ".join(
        f"{reading.layout + ' calls':>16} {'per row':>8}" for reading in readings
    )
    lines = ["call counts from one profiled batch", "", header]
    for contributor in CONTRIBUTORS:
        marker = "*" if contributor.per_row else " "
        cells = " ".join(
            f"{reading.counts[contributor.label]:>16,} "
            f"{reading.counts[contributor.label] / reading.rows:>8.2f}"
            for reading in readings
        )
        lines.append(f"{marker}{contributor.label:<39} {cells}")
    rebuilt = " ".join(f"{'':>16} {reading.rebuilt_per_row():>8.2f}" for reading in readings)
    lines.append(f" {'* rebuilt per row, summed':<39} {rebuilt}")
    return lines


def _secondary_lines(readings: Sequence[Reading], recorded: float | None) -> list[str]:
    build = sum(r.secondary_build_s for r in readings) / len(readings)
    merge = sum(r.secondary_merge_s for r in readings) / len(readings)
    projections = readings[0].secondary_projections
    duration = "not recorded" if recorded is None else f"{recorded:.1f} s"
    return [
        "secondary workload — the direct-converter 64-graph shape",
        f"  build (convert, write, seal)  = {build * 1e3:.2f} ms "
        f"({build / projections * 1e6:.2f} us/projection, "
        f"{projections / build:,.0f} projections/s)",
        f"  merge                         = {merge * 1e3:.2f} ms "
        f"({merge / projections * 1e6:.2f} us/projection)",
        f"  the 64-graph cost item        = {duration} "
        "(read from cost_durations.json, never re-run)",
        "  the two cells of one runtime measure one layout-independent workload, so the",
        "  spread between them is this reading's own repeatability.",
    ]


def _runtime_section(runtime: str, cells: Mapping[str, Cell], recorded: float | None) -> list[str]:
    readings = [cast("Reading", cells[layout]) for layout in LAYOUTS]
    lines = [
        f"CPython {runtime}",
        "",
        "steady state and what one preparation costs",
        "",
        _TIMING_HEADER,
    ]
    lines += [_timing_line(reading) for reading in readings]
    lines += ["", "memory", "", _MEMORY_HEADER]
    lines += [_memory_line(reading) for reading in readings]
    lines += [
        "",
        *(
            f"  one exact Entity layout of the {reading.layout} model holds "
            f"{reading.catalog_tracked:,} tracked objects through "
            f"{reading.catalog_references:,} references, and no prepared decode state"
            for reading in readings
        ),
    ]
    lines += ["", *_count_lines(readings)]
    lines += ["", *_secondary_lines(readings, recorded)]
    return lines


def _scope() -> list[str]:
    """What each column means, and which of them is a measurement of what.

    Stated beside the figures rather than in a document, because it is what a
    reader deciding on one of them needs at the moment of reading it.
    """
    return [
        "what the columns are",
        "  model prep    prepare_model over the workload's Domain Model, once. `decode` is the",
        "                decode preparation inside it, and is zero because none exists.",
        "  compile       the fetch plan plus one compile_read per level, once per execution.",
        "                `decode` is the decode preparation the compiled read owns: also zero.",
        "  batch         one steady-state batch from an already prepared model and compiled",
        "                reads: row materialization, level context, conversion, the observation",
        "                every hydrating row takes, view fan-back, and sealing.",
        "  prep rows     rows of steady-state work one whole preparation costs, and `compile",
        "                rows` the same for compiled-read preparation alone. A REPAYMENT row",
        "                count needs two halves and is computed in the baseline document.",
        "  retained B    bytes the sealed graph keeps, reachable at the sample point.",
        "  peak B        the high-water mark one batch reached above its collected floor.",
        "  transient B   peak less retained: what a batch allocated and freed again.",
        "  prepared B    bytes the compiled reads keep, derived inside the window; `B/read` is",
        "                that over the statements this plan compiles.",
        "  layout decode immutable prepared decode state per exact Entity layout: zero.",
        "  catalog B     what one model's whole layout catalog keeps, over its Entity layouts —",
        "                context for the line above, and unchanged by this work.",
        "",
        "  Every figure is a measurement of ONE machine and ONE interpreter. Nothing here",
        "  gates. The gated claim is the scaling regression's: prepared state is fixed by the",
        "  model's exact Entity layouts and by the compiled reads, asserted as an exact",
        "  equality over what each prepared structure reaches and what its window leaves",
        "  alive, where references and positions answer definitely and a byte total does not.",
    ]


def render(matrix: Matrix, recorded: float | None) -> list[str]:
    """The whole report, given a complete matrix."""
    lines = ["parallax snapshot materialization — production row-to-graph path", ""]
    warmups = [
        cell.warmup
        for cells in matrix.values()
        for cell in cells.values()
        if isinstance(cell, Reading)
    ]
    lines += [f"  {name:<10}{value}" for name, value in _conditions(tuple(matrix), warmups)]
    for runtime, cells in matrix.items():
        lines += ["", *_runtime_section(runtime, cells, recorded)]
    return [*lines, "", *_scope()]


# --------------------------------------------------------------------------- #
# Entry points.                                                               #
# --------------------------------------------------------------------------- #


def main(argv: list[str]) -> int:
    """Spawn the children, print what they answer; judge only whether the
    measurement is complete.

    Exit codes: 0 — the measurement ran; 2 — usage error; 3 — a matrix cell has
    no reading. Every one of them is a statement about whether there is output to
    read, never about what the output says, which is what
    `core/spec/language-testing.md` §2 leaves a non-blocking operation.

    Takes no arguments, which is what leaves the reading itself outside this
    module: one layout's reading is `tools/snapshot_materialization_reading.py`,
    run as a script by :func:`in_a_child`.
    """
    if argv:
        print("usage: python tools/snapshot_materialization_overhead.py", file=sys.stderr)
        return 2

    runtimes = supported_minors()
    matrix: Matrix = {
        runtime: {layout: in_a_child(runtime, layout) for layout in LAYOUTS} for runtime in runtimes
    }
    absent = missing_cells(matrix, runtimes)
    if absent:
        print(
            "\n".join(["the matrix is incomplete, so nothing is reported:", *absent]),
            file=sys.stderr,
        )
        return 3
    print("\n".join(render(matrix, recorded_cost_item_seconds())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
