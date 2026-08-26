"""What a published Entity retains and costs under both backings, over the six
canonical scenarios and on every supported CPython minor.

Two arms — the legacy publication fixture and the shipping publication path —
measured side by side in the same fresh child interpreter, one child per complete
scenario, so no arm pays a process of its own and no ordering contaminates the
allocator. Six canonical scenarios (shallow, wide, nested, nullable, partial,
polymorphic) carry the aggregate; a seventh, deliberately warmed with a
``PrivateAttr`` and a ``cached_property``, is reported beside them and excluded
from it, because that state is the author's rather than the representation's.

It is a `report`: no number it computes can change its exit code, because a total
in bytes is machine- and interpreter-relative. What it does compute is the two
verdicts the measurement contract names — the aggregate reduction against its
target, and any representative operation regressing past its limit — and prints
them as an escalation block, so a missed target is detected here rather than
noticed by whoever reads the table. The one thing it exits non-zero on is
COMPLETENESS: a matrix cell that has no reading is named and refused, since that
is a statement about whether the measurement ran rather than about how large a
number is.

**Both arms are read over one object layout**, which is what makes their ratio
the representation's. Every framework slot a declared class carries is carried by
both — an ordinary value holds the compact and auxiliary pointers exactly as a
published one does, and an Entity of either backing holds the lifecycle slot — so
these two sums may be divided, where the frozen sums in
``docs/instance-state-baseline.md`` were taken over a tree that had none and may
not be the comparand for a reading taken here.

**The legacy arm is a FIXTURE** —
``_instance_state_support.legacy_publication``, which builds one node the way
Entity Graph Construction built one before publication became compact: a
zero-argument ``model_construct`` filled one member at a time. It reproduced the
real path exactly while that path existed, and every scenario's fixture was
compared against it before any reading was taken. The compact arm needs no
fixture: it is ``EntityGraphConstruction.construct`` itself.

**What is measured, per scenario and per arm.** Bytes reachable at the seam's
innermost point while one node of that arm is held that were not reachable before
the window opened — read twice, once with the node's lifecycle state attached and
once without, so the aggregate that includes unchanged lifecycle state and the
one that isolates publication state are both available. Beside them: what
constructing one node costs, what an ordinary declared-field read costs, what
``model_dump()`` costs, and what one construction allocates and frees again.

**How decoded payload leaves are excluded — structurally, not by filtering.**
Every scenario's input row and every leaf in it is allocated at import time,
outside every window, so a node that merely references one of them costs the
reading the position and not the leaf. Shared class and model metadata is excluded
the same way: every reading warms its seam before opening its window, so a layout,
a class index, or a construction's per-Entity facts is already in the baseline the
sample is compared against.

**What it is measured with.** ``memory_instruments``, the one definition the gated
suites read the same claims through: a collection before every sample so a reading
answers what is still REACHABLE, warm-up passes before every window, and the line
tracer uninstalled for the window.

Run it through `just python-report-instance-state`.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import tomllib
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any, Final, NamedTuple, cast

WORKSPACE: Final = Path(__file__).resolve().parents[1]
"""The Python workspace root — where a child interpreter of another minor is
resolved from, and where the supported-minor range is declared."""

INSTRUMENTS: Final = WORKSPACE / "tests" / "unit"
"""The one directory this report names, so it can read the instruments and the
scenario fixture the gated suite reads.

They are support code for `tests/unit/`, whose own suites are their other
readers, and `core/spec/language-testing.md` §4 keeps single-surface support code
inside its surface — a report is no surface of its own, so picking them up here
does not move them. The reach stays deliberate and one-way: the path is spelled
once, here, and nothing under `tests/` knows this file exists.
"""

INSTRUMENT_MODULE: Final = INSTRUMENTS / "memory_instruments.py"
SUPPORT_MODULE: Final = INSTRUMENTS / "_instance_state_support.py"
"""The exact files the reading is taken through and over.

Both are generic names on a path this process does not own, so prepending the
directory is only half of what makes the import deterministic: a module of either
name already in :data:`sys.modules` wins before any path entry is consulted. The
report therefore states which files it means and refuses to measure through any
other, because the alternative failure is silent — a different sampling recipe or
a different scenario mix would still produce numbers, and they would not be the
numbers the recorded baseline is stated over.
"""

sys.path.insert(0, str(INSTRUMENTS))

import _instance_state_support  # noqa: E402
import memory_instruments  # noqa: E402

for _module, _expected in (
    (memory_instruments, INSTRUMENT_MODULE),
    (_instance_state_support, SUPPORT_MODULE),
):
    if Path(_module.__file__ or "").resolve() != _expected:
        raise ImportError(
            f"this report measures through {_expected}, but "
            f"{_module.__name__!r} resolved to {_module.__file__}"
        )

from _instance_state_support import (  # noqa: E402
    REPORTED,
    SCENARIOS,
    WARMED_AUXILIARY,
    Scenario,
    compact_publication,
    legacy_publication,
    scenario_named,
    state_cells,
)
from memory_instruments import (  # noqa: E402
    WARMUP,
    Seam,
    allocation,
    retained,
    untraced,
)

REPETITIONS: Final = 2_000
"""Timed repetitions of each operation. Wall clock is recorded for visibility
alone, so this buys a stable mean rather than a distribution."""

AGGREGATE_TARGET: Final = 0.33
"""The reduction in summed retained bytes the measurement contract accepts, below
which the measured result is returned to the user for a decision."""

REGRESSION_LIMIT: Final = 1.20
"""How far a representative operation may move before it is surfaced for human
review. There is no timing gate — this decides what the escalation block SAYS,
never what the report exits with."""

CURRENT_MINOR: Final = f"{sys.version_info.major}.{sys.version_info.minor}"


class ArmReading(NamedTuple):
    """One arm's whole reading of one scenario."""

    cells: int
    retained_bytes: int
    bare_bytes: int
    transient_bytes: int
    construct_ns: float
    read_ns: float
    dump_ns: float

    @property
    def lifecycle_bytes(self) -> int:
        """What the unchanged lifecycle state costs — the difference between the
        two readings rather than a measurement of the state object alone, so
        whatever attaching it makes reachable is counted where a reader would."""
        return self.retained_bytes - self.bare_bytes

    @property
    def peak_bytes(self) -> int:
        """The high-water mark one construction reaches: the state the node keeps
        plus what the construction allocated and freed on the way to it."""
        return self.retained_bytes + self.transient_bytes


class Reading(NamedTuple):
    """One scenario's reading under both arms, as a child interpreter answers it."""

    scenario: str
    summary: str
    fields: int
    legacy: ArmReading
    compact: ArmReading

    @property
    def reduction(self) -> float:
        """This scenario's own percentage, lifecycle state included. Diagnostic:
        an aggregate is never the mean of these."""
        return 1 - self.compact.retained_bytes / self.legacy.retained_bytes

    @property
    def bare_reduction(self) -> float:
        """The same, over the readings that carry no lifecycle state."""
        return 1 - self.compact.bare_bytes / self.legacy.bare_bytes


type Cell = Reading | str
"""One matrix position: a reading, or why there is none."""

type Matrix = dict[str, dict[str, Cell]]
"""Every reading, by runtime and then by scenario."""


class Operation(NamedTuple):
    """One representative operation the regression rule grades."""

    name: str
    nanoseconds: Callable[[ArmReading], float]


# Three named readers rather than three lambdas, so each one carries the parameter
# type its Operation declares and the timings stay statically checked.


def _construction_ns(arm: ArmReading) -> float:
    return arm.construct_ns


def _read_ns(arm: ArmReading) -> float:
    return arm.read_ns


def _dump_ns(arm: ArmReading) -> float:
    return arm.dump_ns


OPERATIONS: Final = (
    Operation("construction", _construction_ns),
    Operation("attribute read", _read_ns),
    Operation("serialization", _dump_ns),
)


# --------------------------------------------------------------------------- #
# The seams, and one scenario's reading. Taken in a child interpreter.          #
# --------------------------------------------------------------------------- #


def held(
    scenario: Scenario,
    arm: Callable[[Scenario, object | None], object],
    *,
    lifecycle: bool,
) -> Seam:
    """One node of ``arm``, built inside the window and held at the sample.

    The lifecycle state is built inside the window too, so the reading that
    carries it counts it: an object allocated before the window would be borrowed
    rather than retained, and the difference between the two readings would be
    zero for the wrong reason.
    """

    def run(sample: Callable[[], None]) -> None:
        state = scenario.state() if lifecycle else None
        node = arm(scenario, state)
        sample()
        assert node is not None

    return run


def _elapsed_ns(work: Callable[[], None], *, per: int = 1) -> float:
    """Mean nanoseconds one ``work`` takes, over :data:`REPETITIONS` runs."""
    with untraced():
        for _ in range(WARMUP):
            work()
        start = perf_counter()
        for _ in range(REPETITIONS):
            work()
        elapsed = perf_counter() - start
    return elapsed * 1e9 / (REPETITIONS * per)


def measure_arm(
    scenario: Scenario,
    arm: Callable[[Scenario, object | None], object],
    field_names: tuple[str, ...],
) -> ArmReading:
    """``arm``'s reading of ``scenario``, taken in this interpreter."""
    node = arm(scenario, scenario.state())

    def construct() -> None:
        arm(scenario, scenario.state())

    def read_fields() -> None:
        for name in field_names:
            getattr(node, name)

    def dump() -> None:
        cast("Any", node).model_dump()

    tracemalloc.start()
    try:
        retained_bytes = retained(held(scenario, arm, lifecycle=True))
        bare_bytes = retained(held(scenario, arm, lifecycle=False))
        _, transient_bytes = allocation(held(scenario, arm, lifecycle=True))
    finally:
        tracemalloc.stop()
    return ArmReading(
        cells=state_cells(node),
        retained_bytes=retained_bytes,
        bare_bytes=bare_bytes,
        transient_bytes=transient_bytes,
        construct_ns=_elapsed_ns(construct),
        read_ns=_elapsed_ns(read_fields, per=len(field_names)),
        dump_ns=_elapsed_ns(dump),
    )


def measure(scenario: Scenario) -> Reading:
    """``scenario``'s reading under both arms, taken in this interpreter.

    Both arms in one process, which is what the child is for: a byte reading is
    read against a floor the interpreter decides, so two arms compared across two
    processes would be compared across two floors.
    """
    field_names = tuple(cast("Any", scenario.cls).__pydantic_fields__)
    return Reading(
        scenario=scenario.name,
        summary=scenario.summary,
        fields=len(field_names),
        legacy=measure_arm(scenario, legacy_publication, field_names),
        compact=measure_arm(scenario, compact_publication, field_names),
    )


# --------------------------------------------------------------------------- #
# The matrix: one child per complete scenario, one runtime at a time.           #
# --------------------------------------------------------------------------- #


def supported_minors() -> tuple[str, ...]:
    """Every CPython minor the workspace declares support for, oldest first.

    Derived from ``requires-python`` rather than authored here, so the matrix is
    the supported range by construction: the floor is the range's own lower bound
    and the ceiling is the interpreter taking the reading, which the support
    policy makes the latest supported minor.
    """
    declared = cast(
        "str",
        tomllib.loads((WORKSPACE / "pyproject.toml").read_text())["project"]["requires-python"],
    )
    floor = declared.removeprefix(">=").strip()
    major, minor = (int(part) for part in floor.split(".")[:2])
    if major != sys.version_info.major or minor > sys.version_info.minor:
        raise SystemExit(
            f"the declared floor is CPython {floor} and this interpreter is {CURRENT_MINOR}: "
            "the matrix runs from the floor up to the interpreter taking the reading, which has "
            "to be the later of the two and in the same major series"
        )
    return tuple(f"{major}.{each}" for each in range(minor, sys.version_info.minor + 1))


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
            Path(tempfile.gettempdir()) / f"parallax-instance-state-{runtime}"
        )
    }


def _child_command(runtime: str, scenario: Scenario) -> list[str]:
    """What starts one scenario's child on ``runtime``."""
    here = str(Path(__file__).resolve())
    if runtime == CURRENT_MINOR:
        return [sys.executable, here, scenario.name]
    return ["uv", "run", "--frozen", "--python", runtime, "python", here, scenario.name]


def in_a_child(runtime: str, scenario: Scenario) -> Cell:
    """``scenario``'s reading on ``runtime``, or why there is none.

    One child per COMPLETE scenario rather than per arm: the isolation a whole-
    interpreter reading needs is a property of the process, and paying one process
    per arm would buy nothing while making every arm's floor a different one.

    A child that fails answers with its own output rather than ending the run, so
    one unavailable runtime names every cell it cost instead of hiding the cells
    that would have followed it.

    ``memory_instruments.in_a_child_interpreter`` is the same pattern for a test,
    and is deliberately not reused: it raises on a non-zero exit and discards the
    child's output, where a report has to read the numbers back.
    """
    try:
        report = subprocess.run(
            _child_command(runtime, scenario),
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
        payload = cast("dict[str, Any]", json.loads(lines[-1]))
        return Reading(
            scenario=cast("str", payload["scenario"]),
            summary=cast("str", payload["summary"]),
            fields=cast("int", payload["fields"]),
            legacy=ArmReading(**cast("dict[str, Any]", payload["legacy"])),
            compact=ArmReading(**cast("dict[str, Any]", payload["compact"])),
        )
    except (ValueError, KeyError, TypeError) as error:
        return f"the child's reading did not decode: {error}"


def _payload(reading: Reading) -> str:
    """One reading as the line a child answers with."""
    return json.dumps(
        reading._asdict()
        | {"legacy": reading.legacy._asdict(), "compact": reading.compact._asdict()}
    )


def missing_cells(matrix: Matrix, scenarios: Sequence[Scenario]) -> list[str]:
    """Every matrix position that carries no reading, each with its reason.

    Named rather than skipped: a runtime whose interpreter is unavailable, or a
    scenario whose child died, would otherwise leave a matrix that looks complete
    to a reader who does not know which cells to expect.
    """
    absent: list[str] = []
    for runtime, cells in matrix.items():
        for scenario in scenarios:
            cell = cells.get(scenario.name, "no child was run")
            if isinstance(cell, str):
                absent.append(f"CPython {runtime}, {scenario.name}: {cell}")
    return absent


def canonical(cells: Mapping[str, Cell]) -> list[Reading]:
    """One runtime's readings over the canonical mix, in the mix's own order.

    The warmed-auxiliary scenario is not among them: it is measured and printed,
    and no aggregate sees it.
    """
    return [
        cell
        for cell in (cells.get(scenario.name) for scenario in SCENARIOS)
        if isinstance(cell, Reading)
    ]


# --------------------------------------------------------------------------- #
# The two aggregates, and the escalation block.                                #
# --------------------------------------------------------------------------- #


class Aggregate(NamedTuple):
    """One summed before-and-after, and the reduction between them."""

    label: str
    before: int
    after: int

    @property
    def reduction(self) -> float:
        """``1 - sum(after) / sum(before)``, over sums — never the mean of the
        per-scenario percentages, which weights a small node like a large one."""
        return 1 - self.after / self.before


def aggregates(readings: Sequence[Reading]) -> tuple[Aggregate, Aggregate]:
    """The primary and secondary aggregates over ``readings``.

    Primary includes the unchanged lifecycle state, because a caller retains it;
    secondary excludes it, which is what isolates the publication state this work
    changed.
    """
    return (
        Aggregate(
            label="primary (lifecycle included)",
            before=sum(reading.legacy.retained_bytes for reading in readings),
            after=sum(reading.compact.retained_bytes for reading in readings),
        ),
        Aggregate(
            label="secondary (lifecycle excluded)",
            before=sum(reading.legacy.bare_bytes for reading in readings),
            after=sum(reading.compact.bare_bytes for reading in readings),
        ),
    )


def mix_ratio(readings: Sequence[Reading], operation: Operation) -> float:
    """How far ``operation`` moved over the whole mix — summed, for the same
    reason an aggregate is."""
    before = sum(operation.nanoseconds(reading.legacy) for reading in readings)
    after = sum(operation.nanoseconds(reading.compact) for reading in readings)
    return after / before


def escalations(runtime: str, readings: Sequence[Reading]) -> list[str]:
    """Every line the escalation block owes for one runtime's canonical readings.

    Two rules, both the measurement contract's: an aggregate short of its target
    returns the measured result to the user for a decision, and a representative
    operation past its limit is surfaced for human review. Neither changes what
    this report exits with.
    """
    lines: list[str] = []
    primary, _ = aggregates(readings)
    if primary.reduction < AGGREGATE_TARGET:
        lines.append(
            f"CPython {runtime}: primary aggregate {primary.reduction:.1%} < "
            f"{AGGREGATE_TARGET:.0%} — return the measured result to the user for a decision"
        )
    for operation in OPERATIONS:
        ratio = mix_ratio(readings, operation)
        if ratio <= REGRESSION_LIMIT:
            continue
        worst = max(
            readings,
            key=lambda reading: (
                operation.nanoseconds(reading.compact) / operation.nanoseconds(reading.legacy)
            ),
        )
        worst_ratio = operation.nanoseconds(worst.compact) / operation.nanoseconds(worst.legacy)
        lines.append(
            f"CPython {runtime}: {operation.name} {ratio:.2f}x over the mix "
            f"(> {REGRESSION_LIMIT:.2f}x), worst {worst.scenario} at {worst_ratio:.2f}x "
            "— surfaced for human review"
        )
    return lines


def escalation_block(matrix: Matrix) -> list[str]:
    """The whole block, or the one line that says there is nothing in it."""
    raised = [
        line for runtime, cells in matrix.items() for line in escalations(runtime, canonical(cells))
    ]
    if not raised:
        return [
            "no escalation: every runtime's primary aggregate reaches "
            f"{AGGREGATE_TARGET:.0%} and no representative operation moved past "
            f"{REGRESSION_LIMIT:.2f}x"
        ]
    return ["REVIEW REQUIRED", *(f"  {line}" for line in raised)]


# --------------------------------------------------------------------------- #
# Output.                                                                      #
# --------------------------------------------------------------------------- #


def _conditions(runtimes: Sequence[str]) -> list[tuple[str, str]]:
    return [
        ("Runtimes", f"CPython {', '.join(runtimes)} (this one is {platform.python_version()})"),
        ("Platform", f"{sys.platform}/{platform.machine()}"),
        ("Warm-up", f"{WARMUP} unsampled runs before every window"),
        ("Timings", f"mean of {REPETITIONS} repetitions, taken untraced"),
        ("Isolation", "one fresh child interpreter per complete scenario"),
    ]


_HEADER: Final = (
    f"{'scenario':<12} {'fields':>6} {'arm':<8} {'cells':>5} {'retained B':>11} {'bare B':>9} "
    f"{'lifecycle B':>12} {'build us':>9} {'read ns':>8} {'dump us':>8} "
    f"{'transient B':>12} {'peak B':>9}"
)


def _arm_line(scenario: str, fields: str, arm: str, reading: ArmReading) -> str:
    return (
        f"{scenario:<12} {fields:>6} {arm:<8} {reading.cells:>5} "
        f"{reading.retained_bytes:>11,} {reading.bare_bytes:>9,} "
        f"{reading.lifecycle_bytes:>12,} {reading.construct_ns / 1e3:>9.2f} "
        f"{reading.read_ns:>8.1f} {reading.dump_ns / 1e3:>8.2f} "
        f"{reading.transient_bytes:>12,} {reading.peak_bytes:>9,}"
    )


def _reading_lines(reading: Reading) -> list[str]:
    return [
        _arm_line(reading.scenario, str(reading.fields), "legacy", reading.legacy),
        _arm_line("", "", "compact", reading.compact),
        f"{'':<12} {'':>6} {'reduction':<8} {'':>5} {reading.reduction:>10.1%} "
        f"{reading.bare_reduction:>9.1%}",
    ]


def _runtime_section(runtime: str, cells: Mapping[str, Cell]) -> list[str]:
    lines = [f"CPython {runtime}", "", _HEADER]
    for scenario in REPORTED:
        if scenario is WARMED_AUXILIARY:
            lines.append("-" * len(_HEADER))
        cell = cells[scenario.name]
        assert isinstance(cell, Reading)
        lines += _reading_lines(cell)
    readings = canonical(cells)
    lines.append("")
    for aggregate in aggregates(readings):
        lines.append(
            f"  {aggregate.label:<30} {aggregate.before:>7,} -> {aggregate.after:>7,} B "
            f"= {aggregate.reduction:>6.1%}"
        )
    for operation in OPERATIONS:
        lines.append(
            f"  {operation.name:<30} {mix_ratio(readings, operation):>21.2f}x over the mix"
        )
    return lines


def _scope() -> list[str]:
    """What the two arms include where they do not include the same thing.

    Stated beside the escalation block rather than in a document, because it is
    what a reader deciding on a surfaced regression needs at the moment of
    reading it.
    """
    return [
        "what the arms include, where they differ",
        "  Retained bytes and the read and dump timings are like for like: one node of one",
        "  backing, held or read the same way. CONSTRUCTION is not. The legacy arm is the",
        "  node-building the flip replaced, and the compact arm is the whole",
        "  EntityGraphConstruction.construct call — a scope, a writer, root validation and",
        "  factory buffering, measured at about 1 us per call, which the legacy path paid too",
        "  and the fixture standing for it does not. Read the construction ratio with that",
        "  microsecond subtracted from the compact arm before deciding what it says.",
    ]


def _detail() -> list[str]:
    return [
        "what each scenario is",
        *(f"  {scenario.name:<12} {scenario.summary}" for scenario in REPORTED),
        "",
        "The aggregate is 1 - sum(after) / sum(before) over the summed columns, never the",
        "mean of the per-scenario percentages, and both sums come from one object layout:",
        "both arms are measured on this tree, in one child, so every framework slot one",
        "carries the other carries too. The `warmed` scenario is reported and excluded from",
        "both aggregates — a PrivateAttr's value and a cached_property's result are the",
        "author's state under either backing.",
    ]


def render(matrix: Matrix) -> list[str]:
    """The whole report, given a complete matrix."""
    lines = ["parallax published instance state — legacy and compact arms", ""]
    lines += [f"  {name:<10}{value}" for name, value in _conditions(tuple(matrix))]
    for runtime, cells in matrix.items():
        lines += ["", *_runtime_section(runtime, cells)]
    return [*lines, "", *escalation_block(matrix), "", *_scope(), "", *_detail()]


# --------------------------------------------------------------------------- #
# Entry points.                                                                #
# --------------------------------------------------------------------------- #


def main(argv: list[str]) -> int:
    """Measure and print; judge only whether the measurement is complete.

    Exit codes: 0 — the measurement ran; 2 — usage error; 3 — a matrix cell has
    no reading. There is no exit code for a number that is too large,
    deliberately: the escalation block is what a number earns.
    """
    if len(argv) > 1:
        print("usage: python tools/instance_state_overhead.py [scenario]", file=sys.stderr)
        return 2
    if argv:
        print(_payload(measure(scenario_named(argv[0]))))
        return 0

    matrix: Matrix = {
        runtime: {scenario.name: in_a_child(runtime, scenario) for scenario in REPORTED}
        for runtime in supported_minors()
    }
    absent = missing_cells(matrix, REPORTED)
    if absent:
        print(
            "\n".join(["the matrix is incomplete, so no aggregate is reported:", *absent]),
            file=sys.stderr,
        )
        return 3
    print("\n".join(render(matrix)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
