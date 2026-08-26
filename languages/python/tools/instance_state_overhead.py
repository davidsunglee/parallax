"""What a published Entity retains and costs under each backing, over the six
canonical scenarios and on every supported CPython minor.

Three arms — the legacy publication fixture, the shipping publication path, and
ordinary validating construction — measured side by side in the same fresh child
interpreter, one child per complete scenario, so no arm pays a process of its own
and no ordering contaminates the allocator. Six canonical scenarios (shallow,
wide, nested, nullable, partial, polymorphic) carry the aggregate; a seventh,
deliberately warmed with a ``PrivateAttr`` and a ``cached_property``, is reported
beside them and excluded from it, because that state is the author's rather than
the representation's.

**Two different comparisons are printed, and each says which it is.** The
aggregates are legacy against compact: the representation change, which is the
before and after the measurement contract states its target over. The ordinary
arm enters neither, and answers the other question a caller asks — what a
published instance costs against one they built themselves — which is the
comparison ``spec/python.md`` §2 states every Interface figure over.

It is a `report`, so it DECIDES nothing about what it measures. It computes the
two comparisons the measurement contract names — the aggregate reduction beside
its target, and each representative operation beside its limit — and displays
them as an escalation block, so a missed target is read here rather than noticed
by whoever re-adds the table. `core/spec/language-testing.md` §2 is what makes
that display diagnostic rather than a verdict: a non-blocking command may say
which side of a stated limit a measurement fell on, and may not decide anything
on the answer. So no comparison here reaches an exit code, and the one thing this
exits non-zero on is COMPLETENESS — a matrix cell that has no reading is named
and refused, which says there is nothing here to read rather than that what is
here is wrong.

**Every arm is read over one object layout**, which is what makes a ratio between
two of them the representation's. Every framework slot a declared class carries
is carried by all three — an ordinary value holds the compact and auxiliary
pointers exactly as a published one does, and an Entity of any backing holds the
lifecycle slot — so these sums may be divided, where the frozen sums in
``docs/instance-state-baseline.md`` were taken over a tree that had none and may
not be the comparand for a reading taken here.

**The legacy arm is a FIXTURE** —
``_instance_state_support.legacy_publication``, which builds one node the way
Entity Graph Construction built one before publication became compact: a
zero-argument ``model_construct`` filled one member at a time. It reproduced the
real path exactly while that path existed, and every scenario's fixture was
compared against it before any reading was taken. The compact arm needs no
fixture: it is ``EntityGraphConstruction.construct`` itself. The ordinary arm is
the validating constructor, which needs none either.

**What is measured, per scenario and per arm.** Bytes reachable at the seam's
innermost point while one node of that arm is held that were not reachable before
the window opened — read twice, once with the node's lifecycle state attached
where its arm has one to attach and once without, so the aggregate that includes
unchanged lifecycle state and the one that isolates publication state are both
available. An ordinary node has none to attach (``spec/python.md`` §3), so its
two readings are the same reading rather than a pair. Beside them: what one
MORE node of that arm costs to construct, what one call costs besides its nodes,
how much of that per-node cost is left once the work the legacy fixture also does
is timed out of it, what an ordinary declared-field read costs, what
``model_dump()`` costs, and the
high-water mark one construction reaches, from which what it allocated and freed
again is the difference.

**Construction is timed per node, and its ratio is printed twice.** A compact
node arrives from an ``EntityGraphConstruction.construct`` call that also pays a
call scope, a writer, root validation and factory buffering, where the two
other arms build a node and nothing else — so a per-CALL construction figure compares
two different amounts of work. Each arm is therefore timed building one node and
building :data:`MARGINAL_NODES`, and :func:`marginal` splits the two into the cost
of one more node and the per-call remainder, printed beside it.

That split removes the FIXED per-call cost and not the per-NODE one. A
``construct`` call's populated check, root validation, resolution views and
buffered attachment all scale with node count, so they stay inside the compact
arm's ``node µs``; the pre-flip path paid the same per-node work through the same
call, and the legacy FIXTURE reproduces only the node building and its lifecycle
state. So the compact arm's call is measured a second time with each thing that
fixture also does timed from inside it — a closed list, because the fixture is
four statements — and the remainder, ``outside µs``, is the per-node work the
fixture does not reproduce.

**Both construction ratios are upper bounds, and the tighter one is graded.**
Dividing the two ``node µs`` columns gives ``arm against arm``, which charges the
compact arm for all of that remainder; adding ``outside µs`` to the legacy side
gives ``like for like``, which the regression rule is stated over. It is a bound
rather than a point estimate because ``outside µs`` is a remainder, and every span
subtracted to leave it prices its term high: the corrected figure is at least the
true one, so an operation under the limit is under it in truth. For a member read
and a ``model_dump()`` the correction is exactly zero and both figures are exact.
The ordinary ratio needs no
correction at all: a caller building an ordinary instance genuinely pays no
construction call, so both its sides are the same quantity — the marginal cost of
one additional node, with each arm's per-call cost printed beside it rather than
inside it.

**Where a reading is taken, and where it is not.** This module IMPORTS no
instrument, so there is no name in it that reaches one — not bare, not through a
module attribute, and not through an alias. Every reading is taken in a child, by
``tools/instance_state_reading.py``, which is the script a child runs and the one
place ``memory_instruments`` is reached from; this module spawns the children,
decodes what they answer, and judges only whether the matrix is complete. That is
what `core/spec/language-testing.md` §5 asks of it structurally rather than by
inspection: the `dbfree` suite that grades what this computes imports this module
whole, and a guard reading call spellings can only ever catch the routes it was
taught, where an import that does not exist has no route to teach.

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
tracer uninstalled for the window. Each reading carries the warm-up count its own
child ran, so the printed condition is the range's rather than this process's.

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
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
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

READING_SCRIPT: Final = Path(__file__).resolve().parent / "instance_state_reading.py"
"""The script one child runs: the half of this report that takes a reading."""

SUPPORT_MODULE: Final = INSTRUMENTS / "_instance_state_support.py"
"""The exact file the scenarios are read off.

A generic name on a path this process does not own, so prepending the directory
is only half of what makes the import deterministic: a module of that name
already in :data:`sys.modules` wins before any path entry is consulted. The
report therefore states which file it means and refuses to run against any other,
because the alternative failure is silent — a different scenario mix would still
produce numbers, and they would not be the numbers the recorded baseline is
stated over. The reading script states the same about ``memory_instruments``,
which is the module this one deliberately does not import.
"""

sys.path.insert(0, str(INSTRUMENTS))

import _instance_state_support  # noqa: E402

if Path(_instance_state_support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(
        f"this report measures over {SUPPORT_MODULE}, but "
        f"'_instance_state_support' resolved to {_instance_state_support.__file__}"
    )

from _instance_state_support import (  # noqa: E402
    REPORTED,
    SCENARIOS,
    WARMED_AUXILIARY,
    Scenario,
)

REPETITIONS: Final = 2_000
"""Timed repetitions of each operation. Wall clock is recorded for visibility
alone, so this buys a stable mean rather than a distribution."""

MARGINAL_NODES: Final = 11
"""How many nodes the larger of the two construction timings builds.

Ten more than the smaller, so the per-node cost is a tenth of the difference and
one call's fixed cost divides out of it. Large enough that the difference is far
above the timer's resolution on every arm, small enough that no scenario's graph
starts costing the allocator something a one-node build does not."""

AGGREGATE_TARGET: Final = 0.33
"""The reduction in summed retained bytes the measurement contract accepts, below
which the measured result is returned to the user for a decision."""

REGRESSION_LIMIT: Final = 1.20
"""How far a representative operation may move before it is surfaced for human
review. There is no timing gate — this decides what the escalation block SAYS,
never what the report exits with."""

CURRENT_MINOR: Final = f"{sys.version_info.major}.{sys.version_info.minor}"

SUPPORTED_MINORS: Final = 2
"""How many CPython minors are supported at once — `spec/python.md` §10's policy
is "the latest minor + one prior minor", which makes the declared
``requires-python`` floor the prior one and fixes the range's width above it."""


class ArmReading(NamedTuple):
    """One arm's whole reading of one scenario."""

    cells: int
    retained_bytes: int
    bare_bytes: int
    peak_bytes: int
    construct_ns: float
    """What one MORE node of this arm costs — the marginal per-node cost
    :func:`marginal` separates out, not what one call costs."""
    call_ns: float
    """What one call of this arm costs BESIDES the nodes it builds. Zero within
    noise for an arm that builds a node and nothing else."""
    scaffolding_ns: float
    """How much of :attr:`construct_ns` this arm's call spends BEYOND the work the
    legacy fixture also does — per-node work that fixture reproduces none of,
    although the path it stands for paid all of it through the same call.

    Exactly zero for an arm whose call is a loop over its own node builder, which
    is a fact about that arm rather than a measurement it declined to take. It is
    what turns the raw legacy construction ratio into the like-for-like one
    (:func:`like_for_like_ratio`).

    Derived by subtracting a measured figure rather than by measuring this one, so
    what it is worth follows from that subtrahend: every quantity the fixture DOES
    reproduce is timed out of :attr:`construct_ns` by a span that prices it high,
    which leaves this remainder at most the work the fixture never did. It cannot
    over-state what it adds to the legacy side, and may under-state it — far
    enough, on a scenario where the quantity is near the two timings' noise, to
    come out below zero. :attr:`unreproduced_ns` is this figure read as the
    duration it stands for, and is what every consumer uses."""
    read_ns: float
    dump_ns: float

    @property
    def unreproduced_ns(self) -> float:
        """:attr:`scaffolding_ns` read as the duration it stands for, which is
        never negative.

        The raw difference can be, because it is one marginal timing subtracted
        from another and the quantity it leaves is small enough for the two
        timings' noise to swamp it. A negative correction is not a measurement of
        work: subtracting it from the legacy side would make the pre-flip path
        cost LESS than the fixture that stands for it, which moves the ratio in
        the compact arm's favour on nothing but noise. Zero is the honest floor —
        the case where nothing could be separated out — and it keeps the
        corrected ratio at or under the arm-against-arm one, which is what makes
        the pair a bound and a tighter bound rather than two unrelated figures.
        """
        return max(self.scaffolding_ns, 0.0)

    @property
    def lifecycle_bytes(self) -> int:
        """What the unchanged lifecycle state costs — the difference between the
        two readings rather than a measurement of the state object alone, so
        whatever attaching it makes reachable is counted where a reader would."""
        return self.retained_bytes - self.bare_bytes

    @property
    def transient_bytes(self) -> int:
        """What one construction allocated and freed again on the way to the node
        it kept: the high-water mark less the state that survives it.

        Derived rather than measured, because the two are one reading taken from
        both ends — measuring each against its own floor would let a construction
        be charged for its own product twice, or for none of it."""
        return self.peak_bytes - self.retained_bytes


def marginal(one_node_ns: float, many_nodes_ns: float) -> tuple[float, float]:
    """What one more node costs, and what one call costs besides its nodes.

    ``many_nodes_ns`` times a build of :data:`MARGINAL_NODES` and
    ``one_node_ns`` a build of one, both under the same arm, so their difference
    holds no per-call cost at all: the per-node cost is that difference over the
    node count between them, and the remainder of the one-node timing is what the
    call cost regardless of how many nodes it built.

    Pure arithmetic over two timings, and here rather than beside the timer for
    the reason the module docstring gives: the suite that grades this report
    cannot import anything that measures, so the judgement lives where it can be
    fed numbers and the measurement lives in the child.
    """
    per_node = (many_nodes_ns - one_node_ns) / (MARGINAL_NODES - 1)
    return per_node, one_node_ns - per_node


class Reading(NamedTuple):
    """One scenario's reading under every arm, as a child interpreter answers it."""

    scenario: str
    summary: str
    fields: int
    warmup: int
    """Unsampled runs the child took before every window, as its own instruments
    declare — a condition of this reading rather than of the process printing
    it, since a child of another minor resolves its own."""
    ordinary: ArmReading
    legacy: ArmReading
    compact: ArmReading

    @property
    def reduction(self) -> float:
        """This scenario's own percentage against the LEGACY arm, lifecycle state
        included — the representation change the aggregates divide. Diagnostic:
        an aggregate is never the mean of these."""
        return 1 - self.compact.retained_bytes / self.legacy.retained_bytes

    @property
    def bare_reduction(self) -> float:
        """The same, over the readings that carry no lifecycle state."""
        return 1 - self.compact.bare_bytes / self.legacy.bare_bytes

    @property
    def ordinary_reduction(self) -> float:
        """This scenario's percentage against the ORDINARY arm — a different
        comparison from :attr:`reduction`, and the one §2's Interface statement
        is made over. It enters no aggregate.

        What each side holds rather than a matched pair: the published node
        carries its lifecycle state and the ordinary one has none to carry."""
        return 1 - self.compact.retained_bytes / self.ordinary.retained_bytes

    @property
    def ordinary_bare_reduction(self) -> float:
        """The same with the published node's lifecycle state removed too, which
        is publication state alone against ordinary storage."""
        return 1 - self.compact.bare_bytes / self.ordinary.bare_bytes


type Cell = Reading | str
"""One matrix position: a reading, or why there is none."""

type Matrix = dict[str, dict[str, Cell]]
"""Every reading, by runtime and then by scenario."""


class Operation(NamedTuple):
    """One representative operation the regression rule is stated over."""

    name: str
    nanoseconds: Callable[[ArmReading], float]
    unreproduced: Callable[[ArmReading], float]
    """Given the COMPACT arm's reading, AT MOST the per-node work inside its call
    that the legacy fixture does not reproduce and the pre-flip path paid through
    the same call.

    Zero for an operation whose two arms do the same work on the same object —
    a member read and a ``model_dump()`` are one call against one call — and the
    compact arm's measured scaffolding for construction, which is the one
    operation whose arms are timed at different scopes. Exact where it is zero,
    and a floor where it is measured, which is what makes the corrected ratio an
    upper bound (:func:`like_for_like_ratio`)."""


# Named readers rather than lambdas, so each one carries the parameter type its
# Operation declares and the timings stay statically checked.


def _construction_ns(arm: ArmReading) -> float:
    return arm.construct_ns


def _read_ns(arm: ArmReading) -> float:
    return arm.read_ns


def _dump_ns(arm: ArmReading) -> float:
    return arm.dump_ns


def _scaffolding_ns(arm: ArmReading) -> float:
    return arm.unreproduced_ns


def _same_scope(_arm: ArmReading) -> float:
    return 0.0


OPERATIONS: Final = (
    Operation("construction", _construction_ns, _scaffolding_ns),
    Operation("attribute read", _read_ns, _same_scope),
    Operation("serialization", _dump_ns, _same_scope),
)


# --------------------------------------------------------------------------- #
# The matrix: one child per complete scenario, one runtime at a time.           #
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
    the runtimes the matrix has. The range is therefore what the workspace
    declares, and which interpreter spawns the children decides nothing.
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
            Path(tempfile.gettempdir()) / f"parallax-instance-state-{runtime}"
        )
    }


def _child_command(runtime: str, scenario: Scenario) -> list[str]:
    """What starts one scenario's child on ``runtime``."""
    script = str(READING_SCRIPT)
    if runtime == CURRENT_MINOR:
        return [sys.executable, script, scenario.name]
    return ["uv", "run", "--frozen", "--python", runtime, "python", script, scenario.name]


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
        decoded = cast("dict[str, Any]", json.loads(lines[-1]))
        return Reading(
            scenario=cast("str", decoded["scenario"]),
            summary=cast("str", decoded["summary"]),
            fields=cast("int", decoded["fields"]),
            warmup=cast("int", decoded["warmup"]),
            ordinary=ArmReading(**cast("dict[str, Any]", decoded["ordinary"])),
            legacy=ArmReading(**cast("dict[str, Any]", decoded["legacy"])),
            compact=ArmReading(**cast("dict[str, Any]", decoded["compact"])),
        )
    except (ValueError, KeyError, TypeError) as error:
        return f"the child's reading did not decode: {error}"


def payload(reading: Reading) -> str:
    """One reading as the line a child answers with.

    The encoding half of the child protocol, spelled here beside its decoder so
    the two cannot drift, and imported by the script the child runs.
    """
    return json.dumps(
        reading._asdict()
        | {
            "ordinary": reading.ordinary._asdict(),
            "legacy": reading.legacy._asdict(),
            "compact": reading.compact._asdict(),
        }
    )


def missing_cells(
    matrix: Matrix, runtimes: Sequence[str], scenarios: Sequence[Scenario]
) -> list[str]:
    """Every position of ``runtimes`` by ``scenarios`` that carries no reading,
    each with its reason.

    Walked over the runtimes the caller ASKED for rather than the ones the matrix
    holds: a scenario whose child died leaves a cell behind to notice, and a
    runtime nothing was ever run for leaves nothing at all, so a check reading the
    matrix's own keys would call the second one complete.
    """
    absent: list[str] = []
    for runtime in runtimes:
        cells = matrix.get(runtime, {})
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

    @property
    def retention(self) -> float:
        """What is left, as a share of what there was — the same figure the other
        way up, which is how an Interface statement about what a value RETAINS
        reads."""
        return self.after / self.before


def aggregates(readings: Sequence[Reading]) -> tuple[Aggregate, Aggregate]:
    """The primary and secondary aggregates over ``readings``.

    Both divide the LEGACY arm into the compact one: the representation change,
    which is the before-and-after the measurement contract names. Primary
    includes the unchanged lifecycle state, because a caller retains it;
    secondary excludes it, which is what isolates the publication state this work
    changed. The ordinary arm is in neither — see :func:`against_ordinary`.
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


def against_ordinary(readings: Sequence[Reading]) -> Aggregate:
    """What a published node retains against one a caller built, summed over the
    mix, lifecycle state included.

    A DIFFERENT comparison from :func:`aggregates` and deliberately not one of
    them: the measurement contract's 33% target is stated over the representation
    change, so folding a third arm into that comparison would state the result
    over a pair the target was never set against. This is the figure
    ``spec/python.md`` §2 states instead, and it is reported beside the aggregates
    rather than inside them.

    Lifecycle state is included on the compact side and absent from the ordinary
    one because that is what each holds: a published node carries state under
    either backing and a plainly constructed instance has none to carry
    (``spec/python.md`` §3). :attr:`Reading.ordinary_bare_reduction` is the same
    comparison with the compact side's state removed as well.
    """
    return Aggregate(
        label="published vs ordinary (lifecycle where each holds it)",
        before=sum(reading.ordinary.retained_bytes for reading in readings),
        after=sum(reading.compact.retained_bytes for reading in readings),
    )


def mix_ratio(readings: Sequence[Reading], operation: Operation) -> float:
    """How far ``operation`` moved from the legacy ARM to the compact one over
    the whole mix — summed, for the same reason an aggregate is.

    Arm against arm, exactly as each was timed. For a member read and a
    ``model_dump()`` that is already the before and after; for construction it is
    a LOOSE upper bound, because the compact arm's timing carries per-node work
    the legacy fixture reproduces none of. :func:`like_for_like_ratio` is that
    same comparison with as much of the difference as can be measured taken out,
    which makes it the tighter upper bound and the one the regression rule is
    stated over. Both are printed.
    """
    before = sum(operation.nanoseconds(reading.legacy) for reading in readings)
    after = sum(operation.nanoseconds(reading.compact) for reading in readings)
    return after / before


def before_ns(reading: Reading, operation: Operation) -> float:
    """AT MOST what the pre-flip path paid for ``operation`` on one of
    ``reading``'s nodes: the legacy fixture's own timing plus the per-node work
    that fixture does not reproduce.

    The second term is measured on today's compact call and added to the BEFORE
    side rather than subtracted from the after, because it is work the pre-flip
    path paid and still pays — that half of ``EntityGraphConstruction`` is
    unchanged either side of the flip. Removing it from the compact side would
    price a node nobody constructs.

    At most, and not exactly, because that term is a remainder left by spans that
    price the common work high (:attr:`ArmReading.scaffolding_ns`). A before side
    that can only be small makes every ratio taken over it an upper bound, which
    is the direction a rule that surfaces regressions needs.
    """
    return operation.nanoseconds(reading.legacy) + operation.unreproduced(reading.compact)


def like_for_like_ratio(readings: Sequence[Reading], operation: Operation) -> float:
    """:func:`mix_ratio` with as much of the two arms' scope difference measured
    out as a measurement can take out — the figure the regression rule is stated
    over, and an UPPER BOUND on what the representation change cost rather than a
    point estimate of it.

    A bound rather than a point because the correction is a remainder: it is what
    is left of the compact arm's per-node cost once every quantity the legacy
    fixture also pays has been timed out of it, and each of those is timed by a
    span that prices it high (``_instance_state_support.compact_common_work_ns``).
    The remainder is therefore at most the work the fixture never reproduced, the
    before side it joins is at most what the pre-flip path paid, and this ratio is
    at least the true one. Stating the 20% rule over it can surface an operation
    that did not regress and cannot miss one that did.

    Identical to :func:`mix_ratio` for every operation whose arms already do the
    same work, where the correction is exactly zero and the figure is exact, so
    printing the two side by side is what shows WHICH comparison needed a
    correction rather than asserting it.
    """
    before = sum(before_ns(reading, operation) for reading in readings)
    after = sum(operation.nanoseconds(reading.compact) for reading in readings)
    return after / before


def scenario_ratio(reading: Reading, operation: Operation) -> float:
    """One scenario's own like-for-like ratio — how the escalation block picks
    the worst of a mix it is naming a summed figure for."""
    return operation.nanoseconds(reading.compact) / before_ns(reading, operation)


def ordinary_ratio(readings: Sequence[Reading], operation: Operation) -> float:
    """How far ``operation`` stands from an ordinary instance to a published one
    over the whole mix — summed, and in no escalation.

    A DIFFERENT comparison from :func:`mix_ratio` for the same reason
    :func:`against_ordinary` is a different one from :func:`aggregates`: this is
    what a caller pays against what they would have paid building the value
    themselves, which is the comparison ``spec/python.md`` §2 states every
    Interface cost over, and it is not a regression from anything.

    Over the same quantity on both sides, which for construction is the marginal
    cost of one additional node rather than a whole call: the compact side's
    ``call µs`` is real and is printed, and it is not in this ratio.
    """
    ordinary = sum(operation.nanoseconds(reading.ordinary) for reading in readings)
    compact = sum(operation.nanoseconds(reading.compact) for reading in readings)
    return compact / ordinary


def escalations(runtime: str, readings: Sequence[Reading]) -> list[str]:
    """Every line the escalation block owes for one runtime's canonical readings.

    Two rules, both the measurement contract's: an aggregate short of its target
    returns the measured result to the user for a decision, and a representative
    operation past its limit is surfaced for human review. Both decide what is
    DISPLAYED and neither reaches the exit code, which is what keeps a `report`
    one (`core/spec/language-testing.md` §2).

    The operation rule is applied to :func:`like_for_like_ratio` rather than
    :func:`mix_ratio`, because the limit is stated over what the representation
    change cost and only the like-for-like figure bounds that: the raw ratio would
    surface a difference in how two arms are timed as though it were a regression.
    Both are printed, so a reader sees the compared figure beside the
    arm-against-arm one. The figure the rule reads is an upper bound, so an
    operation it leaves out of the block is one whose true ratio is under the
    limit too.
    """
    lines: list[str] = []
    primary, _ = aggregates(readings)
    if primary.reduction < AGGREGATE_TARGET:
        lines.append(
            f"CPython {runtime}: primary aggregate {primary.reduction:.1%} < "
            f"{AGGREGATE_TARGET:.0%} — return the measured result to the user for a decision"
        )
    for operation in OPERATIONS:
        ratio = like_for_like_ratio(readings, operation)
        if ratio <= REGRESSION_LIMIT:
            continue
        worst = max(readings, key=lambda reading: scenario_ratio(reading, operation))
        lines.append(
            f"CPython {runtime}: {operation.name} {ratio:.2f}x like for like over the mix "
            f"(> {REGRESSION_LIMIT:.2f}x), worst {worst.scenario} at "
            f"{scenario_ratio(worst, operation):.2f}x — surfaced for human review"
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
            f"{REGRESSION_LIMIT:.2f}x like for like"
        ]
    return ["REVIEW REQUIRED", *(f"  {line}" for line in raised)]


# --------------------------------------------------------------------------- #
# Output.                                                                      #
# --------------------------------------------------------------------------- #


def _conditions(runtimes: Sequence[str], warmups: Sequence[int]) -> list[tuple[str, str]]:
    stated = ", ".join(str(count) for count in sorted(set(warmups)))
    return [
        ("Runtimes", f"CPython {', '.join(runtimes)} (this one is {platform.python_version()})"),
        ("Platform", f"{sys.platform}/{platform.machine()}"),
        ("Warm-up", f"{stated} unsampled runs before every window"),
        ("Timings", f"mean of {REPETITIONS} repetitions, taken untraced"),
        ("Build", f"one node against {MARGINAL_NODES}, split into per-node and per-call"),
        (
            "Scope",
            "everything the legacy fixture also does, timed inside a separate compact call",
        ),
        ("Isolation", "one fresh child interpreter per complete scenario"),
    ]


_HEADER: Final = (
    f"{'scenario':<12} {'fields':>6} {'arm':<9} {'cells':>5} {'retained B':>11} {'bare B':>9} "
    f"{'lifecycle B':>12} {'node us':>8} {'call us':>8} {'outside us':>11} {'read ns':>8} "
    f"{'dump us':>8} {'transient B':>12} {'peak B':>9}"
)


def _arm_line(scenario: str, fields: str, arm: str, reading: ArmReading) -> str:
    return (
        f"{scenario:<12} {fields:>6} {arm:<9} {reading.cells:>5} "
        f"{reading.retained_bytes:>11,} {reading.bare_bytes:>9,} "
        f"{reading.lifecycle_bytes:>12,} {reading.construct_ns / 1e3:>8.2f} "
        f"{reading.call_ns / 1e3:>8.2f} {reading.unreproduced_ns / 1e3:>11.2f} "
        f"{reading.read_ns:>8.1f} {reading.dump_ns / 1e3:>8.2f} "
        f"{reading.transient_bytes:>12,} {reading.peak_bytes:>9,}"
    )


def _comparison_line(against: str, retained: float, bare: float) -> str:
    """One reduction line, naming which arm the compact one is divided into.

    Named on every line rather than in a legend: two comparisons are printed per
    scenario and only one of them enters an aggregate.
    """
    return f"{against:<12} {'':>6} {'reduction':<9} {'':>5} {retained:>10.1%} {bare:>9.1%}"


def _reading_lines(reading: Reading) -> list[str]:
    return [
        _arm_line(reading.scenario, str(reading.fields), "ordinary", reading.ordinary),
        _arm_line("", "", "legacy", reading.legacy),
        _arm_line("", "", "compact", reading.compact),
        _comparison_line("vs legacy", reading.reduction, reading.bare_reduction),
        _comparison_line(
            "vs ordinary", reading.ordinary_reduction, reading.ordinary_bare_reduction
        ),
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
    lines.append("  the representation change — legacy arm against compact")
    for aggregate in aggregates(readings):
        lines.append(
            f"    {aggregate.label:<42} {aggregate.before:>7,} -> {aggregate.after:>7,} B "
            f"= {aggregate.reduction:>6.1%}"
        )
    lines.append(f"    {'over the mix':<42} {'arm against arm':>16} {'like for like':>16}")
    for operation in OPERATIONS:
        lines.append(
            f"    {operation.name:<42} {mix_ratio(readings, operation):>15.2f}x "
            f"{like_for_like_ratio(readings, operation):>15.2f}x"
        )
    lines.append("")
    lines.append("  stated separately, in no aggregate — ordinary arm against compact")
    ordinary = against_ordinary(readings)
    lines.append(
        f"    {ordinary.label:<42} {ordinary.before:>7,} -> {ordinary.after:>7,} B "
        f"= {ordinary.reduction:>6.1%}"
    )
    lines.append(
        f"    {'a published node retains':<42} {ordinary.retention:>28.1%} of an ordinary one"
    )
    for operation in OPERATIONS:
        lines.append(
            f"    {operation.name:<42} {ordinary_ratio(readings, operation):>21.2f}x over the mix"
        )
    return lines


def _scope() -> list[str]:
    """What each arm is, and which comparison each printed number makes.

    Stated beside the escalation block rather than in a document, because it is
    what a reader deciding on a surfaced regression needs at the moment of
    reading it.
    """
    return [
        "what the arms are, and what is compared with what",
        "  ordinary  the validating constructor: what a caller builds for themselves.",
        "  legacy    the node-building the publication flip replaced, as a fixture.",
        "  compact   the shipping publication path, EntityGraphConstruction.construct.",
        "",
        "  The aggregates and the regression rule divide LEGACY into compact: that pair is",
        "  the representation change this measurement was taken for. The ordinary arm is in",
        "  neither, and answers the other question — what a published node costs against one",
        "  a caller built — which is the comparison spec/python.md §2 states every figure",
        "  over, so its bytes and its three ratios are printed beside the aggregates.",
        "",
        "  `node us` is what one MORE node of that arm costs, measured by timing a 1-node",
        "  build against an 11-node one, and `call us` is what one call costs besides its",
        "  nodes. That split is what makes construction comparable at all: a compact node",
        "  arrives from a construct call that also pays a scope, a writer, root validation",
        "  and factory buffering, where the other two arms build a node and nothing else.",
        "",
        "  `outside us` is what is LEFT of `node us` once everything the legacy fixture also",
        "  does has been timed out of it, in a separate call. That list is closed because the",
        "  fixture is: it does four things per node, and each has one span. Its state factory",
        "  is timed; its node building is timed as the build callback; its lifecycle attach is",
        "  timed by repeating the same write, since construct performs its own in a loop no",
        "  callback can enter; and the result tuple its graph returns is timed as this arm's,",
        "  built and released inside the span as this arm's caller releases it. No clock runs",
        "  inside the call `node us` is taken over. What is left is the populated check, root",
        "  validation, a resolution view per node, factory buffering and construct's own root",
        "  tuple; the pre-flip path paid all of it through the same call. It is exactly zero",
        "  for the ordinary and legacy arms, whose call IS a loop over their node builder.",
        "",
        "  Every one of those spans prices its term HIGH and none prices one low: the repeated",
        "  attach releases the state it displaces where construct's own write finds the slot",
        "  empty, and each span carries the clock reads bounding it. So `outside us` is at",
        "  most the work the fixture never did, never more — which is what the corrected",
        "  ratio is worth, and all it is worth.",
        "",
        "  So every ratio is printed twice, and for construction BOTH ARE UPPER BOUNDS.",
        "  `arm against arm` divides the two `node us` columns as each was timed, which",
        "  charges compact for the whole of what the fixture did not reproduce. `like for",
        "  like` adds `outside us` to the legacy side instead, which is at most what the",
        "  pre-flip path paid, so it is the tighter bound and not a point estimate.",
        "  THE 20% RULE IS STATED OVER THE LIKE-FOR-LIKE FIGURE, because the limit is about",
        "  what the representation change cost — and over a bound in the safe direction: an",
        "  operation under the limit here is under it in truth, and one over it may not be.",
        "  For attribute read and serialization the two columns are equal by construction —",
        "  one call against one call on one node — so those two figures are exact rather than",
        "  bounded, which is what shows which operation needed a correction at all.",
        "",
        "  The ordinary construction ratio needs no such correction and gets none: a caller",
        "  building an ordinary instance pays no construct call at all, so both sides of it",
        "  are the same quantity — the marginal cost of one additional node, with each arm's",
        "  `call us` outside it.",
    ]


def _detail() -> list[str]:
    return [
        "what each scenario is",
        *(f"  {scenario.name:<12} {scenario.summary}" for scenario in REPORTED),
        "",
        "The aggregate is 1 - sum(after) / sum(before) over the summed columns, never the",
        "mean of the per-scenario percentages, and both sums come from one object layout:",
        "every arm is measured on this tree, in one child, so every framework slot one",
        "carries the others carry too. The `warmed` scenario is reported and excluded from",
        "every aggregate — a PrivateAttr's value and a cached_property's result are the",
        "author's state under every backing.",
    ]


def render(matrix: Matrix) -> list[str]:
    """The whole report, given a complete matrix."""
    lines = ["parallax published instance state — ordinary, legacy and compact arms", ""]
    warmups = [
        cell.warmup
        for cells in matrix.values()
        for cell in cells.values()
        if isinstance(cell, Reading)
    ]
    lines += [f"  {name:<10}{value}" for name, value in _conditions(tuple(matrix), warmups)]
    for runtime, cells in matrix.items():
        lines += ["", *_runtime_section(runtime, cells)]
    return [*lines, "", *escalation_block(matrix), "", *_scope(), "", *_detail()]


# --------------------------------------------------------------------------- #
# Entry points.                                                                #
# --------------------------------------------------------------------------- #


def main(argv: list[str]) -> int:
    """Spawn the children, print what they answer; judge only whether the
    measurement is complete.

    Exit codes: 0 — the measurement ran; 2 — usage error; 3 — a matrix cell has
    no reading. Every one of them is a statement about whether there is output to
    read, never about what the output says, which is what
    `core/spec/language-testing.md` §2 leaves a non-blocking operation: a number
    over its target changes what the escalation block DISPLAYS and nothing else.

    Takes no arguments, which is what leaves the reading itself outside this
    module: one scenario's reading is `tools/instance_state_reading.py`, run as a
    script by :func:`in_a_child`.
    """
    if argv:
        print("usage: python tools/instance_state_overhead.py", file=sys.stderr)
        return 2

    runtimes = supported_minors()
    matrix: Matrix = {
        runtime: {scenario.name: in_a_child(runtime, scenario) for scenario in REPORTED}
        for runtime in runtimes
    }
    absent = missing_cells(matrix, runtimes, REPORTED)
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
