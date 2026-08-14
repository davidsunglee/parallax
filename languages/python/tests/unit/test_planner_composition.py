"""Every write lane plans through the composition-root factory.

``parallax.snapshot.handle.build_write_planner`` is the one place the optional
policy modules are wired into a Write Planner, so a lane that built a planner of
its own would plan under a second set of strategies free to drift from
production's. This grades that as behavior: the factory is made to hand back
planners this module can recognize, a real write is driven through each lane, and
the drive is then followed all the way to the statements it emits.

The chain is closed link by link. Every planning the drive performed ran on a
planner the factory built. Every Write Plan that was streamed through
``stream_lowered`` is by identity a plan one of those plannings returned, and the
plans streamed are the plans planned, in order, so a factory plan the lane
discarded is named too. Every step rendered by ``lower_step`` — the one function
that turns a settled step into a statement — is by identity a step of one of
those streamed plans. An unrelated implementation of the planner interface
inherits nothing, so it performs no planning this module records and appears in
no subclass registry; but its plan still has to become SQL, and every route from
a plan to SQL runs through those two functions under a name this module replaced.

Both functions are replaced on every imported ``parallax`` module holding them,
the modules defining them included, so a caller reaching the seam under a second
name — or binding it while the watch is installed, since every route to it reads
one of the replaced attributes — is watched rather than missed. A plan handed to
a stream nobody consumed renders nothing and is recorded nowhere.

What remains uncovered is stated exactly: a lane that emitted DML without
rendering a step at all, assembling a statement from the SQL layer directly, and
a write lane this module does not drive. The lanes it drives are ENUMERATED — the
`Database` lane, and the conformance engine's writeSequence, readless predicate
write, and conflict entries. On an undriven lane,
`test_source_enforcement_topology.py` still finds a second ``WritePlanner``
construction and a second planner class, but a planner constructed through an
alias is caught by neither module.

The `Database` lane is graded on identity as well as provenance. One planner
serves the whole transaction, so a typed verb and ``tx.write_neutral`` are held
to feeding the SAME object rather than two equivalently wired ones — the direct
statement of spec §5's model-neutral seam. The conformance engine builds a
planner per lowering and holds none, so its drives claim provenance rather than
identity.

The factory's own wiring is graded here too, for the one strategy whose
production value is a decision rather than an implementation: the audit port it
injects is the neutral one, so no planner a write path reaches can decorate.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from _transact_support import NEW_ROW, RecordingPort, account_db, new_account

from _support import mirrored_models as mm
from _support.repo import REPO_ROOT
from parallax.conformance import case_format, engine
from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import (
    NO_AUDIT,
    AuditStrategy,
    BatchingStrategy,
    ConcurrencyStrategy,
    PlannedWrite,
    PlanningRequest,
    TemporalStrategy,
    VersionObservation,
    WriteInstruction,
    WritePlan,
    WritePlanner,
    instructions,
)
from parallax.snapshot import handle
from parallax.snapshot.handle import Transaction, _planning

type _CompileCase = Callable[[case_format.Case, str], tuple[list[engine.Emission], int]]

_CASES: Path = REPO_ROOT / "core" / "compatibility" / "cases"


@dataclass(frozen=True, slots=True)
class _Built:
    """One planner the composition root built, and the audit strategy it wired.

    The strategy is taken where the factory injects it rather than read back off
    the planner, which holds it privately.
    """

    planner: WritePlanner
    audit: AuditStrategy


@dataclass(frozen=True, slots=True)
class _Planning:
    """One planning: its receiver, what it was asked to plan, and what it returned."""

    planner: WritePlanner
    request: PlanningRequest
    plan: WritePlan


@dataclass(slots=True)
class _Composition:
    """One drive's planning provenance: the planners the composition root built
    while it ran, every planning that ran, every plan whose lowering was streamed,
    and every step rendered into a statement."""

    lane: str
    built: list[_Built]
    planned: list[_Planning]
    lowered: list[WritePlan]
    rendered: list[PlannedWrite]

    def escaped(self) -> list[PlanningRequest]:
        """The plannings whose receiver the composition root did not build."""
        return [
            one.request
            for one in self.planned
            if not any(one.planner is built.planner for built in self.built)
        ]

    def unaccounted(self) -> list[WritePlan]:
        """The lowered plans no planning recorded here produced."""
        return [plan for plan in self.lowered if not any(plan is one.plan for one in self.planned)]

    def steps_of_lowered_plans(self) -> list[PlannedWrite]:
        """Every step the streamed plans hold, in the order streaming reaches them."""
        return [step for plan in self.lowered for step in plan.steps]


def _bindings_of(name: str) -> list[ModuleType]:
    """Every imported ``parallax`` module holding the handle's ``name``.

    A module that imported the function keeps a binding of its own, which
    replacing the name in the module that defines it leaves untouched. Asking
    which modules hold the object is what makes the watch complete without
    anyone having had to list the callers.
    """
    original = getattr(handle, name)
    return [
        module
        for module in list(sys.modules.values())
        if getattr(module, "__name__", "").startswith("parallax.")
        and getattr(module, name, None) is original
    ]


def _watch(lane: str, monkeypatch: pytest.MonkeyPatch) -> _Composition:
    """Make the composition root hand back recognizable planners for ``lane``, and
    record every planning any planner performs, every plan whose lowering is
    streamed, and every step rendered into a statement while it is installed.

    What is replaced is the factory's own name for the planner CLASS, not the
    factory: both consumers bind ``build_write_planner`` at import time, so a
    patch of that name would intercept neither, while the class name is read
    inside the factory body on every call. ``raising`` is left on throughout and a
    lowering function nothing holds fails the watch outright, so the day a name
    moves this fails rather than silently watching nothing.

    ``plan`` is watched on the class rather than on the built planners, so a
    planning that ran on some OTHER ``WritePlanner`` is visible instead of merely
    absent. The lowering functions are watched because a plan an unrelated
    implementation produced runs no watched ``plan`` at all and would otherwise be
    invisible right up to the statements it emits; the plan is recorded when its
    stream is STARTED rather than when the seam is called, so a stream nobody
    consumed accounts for nothing.
    """
    seen = _Composition(lane=lane, built=[], planned=[], lowered=[], rendered=[])
    planning = WritePlanner.plan
    streaming = handle.stream_lowered
    rendering = handle.lower_step

    def construct(
        model: Metamodel,
        *,
        batching: BatchingStrategy,
        concurrency: ConcurrencyStrategy,
        temporal: TemporalStrategy,
        audit: AuditStrategy,
    ) -> WritePlanner:
        planner = WritePlanner(
            model, batching=batching, concurrency=concurrency, temporal=temporal, audit=audit
        )
        seen.built.append(_Built(planner=planner, audit=audit))
        return planner

    def plan(self: WritePlanner, request: PlanningRequest) -> WritePlan:
        planned = planning(self, request)
        seen.planned.append(_Planning(planner=self, request=request, plan=planned))
        return planned

    def lower(
        plan: WritePlan, meta: Metamodel, dialect: Dialect
    ) -> Iterator[tuple[PlannedWrite, LoweredStatement]]:
        seen.lowered.append(plan)
        yield from streaming(plan, meta, dialect)

    def render(step: PlannedWrite, meta: Metamodel, dialect: Dialect) -> LoweredStatement:
        seen.rendered.append(step)
        return rendering(step, meta, dialect)

    monkeypatch.setattr(_planning, "WritePlanner", construct)
    monkeypatch.setattr(WritePlanner, "plan", plan)
    for replacement, name in ((lower, "stream_lowered"), (render, "lower_step")):
        holders = _bindings_of(name)
        assert holders, f"nothing imported holds {name}, so watching it grades nothing"
        for module in holders:
            monkeypatch.setattr(module, name, replacement)
    return seen


def _assert_planned_only_through_the_factory(seen: _Composition, plannings: int) -> None:
    escaped = seen.escaped()
    assert not escaped, (
        f"{seen.lane}: {len(escaped)} of {len(seen.planned)} plannings ran on a planner the "
        f"composition root did not build (it built {len(seen.built)}); the first of them "
        f"planned {_buffer_shapes(escaped[0])}"
    )
    unaccounted = seen.unaccounted()
    assert not unaccounted, (
        f"{seen.lane}: {len(unaccounted)} of {len(seen.lowered)} plans reached the write-"
        f"lowering seam without any planning recorded here having produced them, so something "
        f"other than this factory's planners planned them"
    )
    assert [id(one.plan) for one in seen.planned] == [id(plan) for plan in seen.lowered], (
        f"{seen.lane}: {len(seen.planned)} plannings produced plans but {len(seen.lowered)} "
        f"reached the write-lowering seam — a plan this factory produced was discarded, or one "
        f"was lowered twice"
    )
    assert [id(step) for step in seen.rendered] == [
        id(step) for step in seen.steps_of_lowered_plans()
    ], (
        f"{seen.lane}: {len(seen.rendered)} steps became statements against "
        f"{len(seen.steps_of_lowered_plans())} held by the plans lowered here — a statement was "
        f"rendered from a step no plan this factory produced holds, or a lowered plan's step never "
        f"became one"
    )
    assert len(seen.planned) == plannings, (
        f"{seen.lane}: {len(seen.planned)} plannings ran on a planner this factory built, "
        f"not {plannings} — a drive that obtained a plan anywhere else comes up short here "
        f"rather than escaping above"
    )


def _buffer_shapes(request: PlanningRequest) -> list[str]:
    """One planning's buffer as the item shapes it held — what a failure needs to
    say about a planning nothing here accounts for."""
    return [type(item).__name__ for item in request.buffered_writes]


def _neutral_update() -> WriteInstruction:
    return instructions.deserialize(
        {
            "mutation": "update",
            "entity": "parallax.compatibility.Account",
            "rows": [{"id": 7, "balance": 11}],
        }
    )


def test_the_database_lane_plans_every_ingress_through_one_factory_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _watch("Database", monkeypatch)
    port = RecordingPort(rows=[NEW_ROW])
    database = account_db(port)

    def body(tx: Transaction) -> None:
        tx.insert(new_account())
        # A participating read force-flushes the buffered insert, so the neutral
        # write below reaches a SECOND planning rather than being coalesced into
        # the typed verb's own — which is what leaves two receivers to compare.
        tx.find(mm.Account.where(mm.Account.id == 7))
        tx.write_neutral(_neutral_update(), observation=VersionObservation(observed_version=1))

    database.transact(body)

    _assert_planned_only_through_the_factory(seen, plannings=2)
    assert len(seen.built) == 1, "one connected Metamodel, one planner"
    assert all(one.planner is seen.built[0].planner for one in seen.planned)


def test_the_composition_root_wires_the_audit_port_to_the_neutral_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit decoration is a wired port with nothing behind it, and this is the
    # wiring half: the planner a write path plans through holds the neutral
    # strategy, so no step reaching stage 8 meets one that could decorate. The
    # other half — that the neutral strategy hands back the step it was given —
    # is a property of the strategy itself and lives with the rest of the
    # algebra's behavior in `test_planned_algebra.py`.
    #
    # Which classes SATISFY the port is deliberately not asked. It is a
    # runtime-checkable Protocol, so satisfying it means owning a method named
    # `decorate`: the question answers yes for any decorator with nothing to do
    # with audit, and no for a hand-written stamp under another name.
    #
    # The limit: a value stamped by hand onto a row, under a name of its own and
    # ahead of the reserved audit property names, reaches no strategy and so
    # passes here. What a write emits is a property of the statement and its
    # binds, constrained where write behavior is — an extra column or an extra
    # bind fails an exact-statement assertion for the write shapes those
    # assertions cover, and a stamp that never varies survives every comparison
    # of two writes to each other.
    seen = _watch("Database", monkeypatch)
    account_db(RecordingPort())

    assert seen.built, "connecting built no planner, so this grades no wiring"
    assert all(built.audit is NO_AUDIT for built in seen.built)


# The planning count is the case's own shape: one per flush the lowering
# performs, so the write-sequence case's two steps plan twice and the
# single-statement predicate write plans once.
@pytest.mark.parametrize(
    ("lane", "case", "compile_case", "plannings"),
    [
        pytest.param(
            "conformance writeSequence",
            _CASES / "m-unit-work-003-fk-insert-ordering.yaml",
            engine.compile_write_sequence_case,
            2,
            id="write-sequence",
        ),
        pytest.param(
            "conformance readless predicate write",
            _CASES / "m-batch-write-006-predicate-update-readless-column-order.yaml",
            engine.compile_scenario_case,
            1,
            id="predicate-write",
        ),
    ],
)
def test_the_conformance_lane_plans_through_planners_the_factory_built(
    lane: str,
    case: Path,
    compile_case: _CompileCase,
    plannings: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _watch(lane, monkeypatch)
    emissions, _round_trips = compile_case(case_format.load_case(case), "postgres")

    assert emissions, "a case that emitted nothing exercised no write lane"
    _assert_planned_only_through_the_factory(seen, plannings=plannings)


def test_the_conformance_conflict_lane_plans_through_planners_the_factory_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _watch("conformance conflict", monkeypatch)
    case = case_format.load_case(_CASES / "m-opt-lock-006-success.yaml")
    emissions, _affected, _state, _log, _round_trips = engine.run_conflict_case(
        case, "postgres", RecordingPort()
    )

    assert emissions, "a case that emitted nothing exercised no write lane"
    _assert_planned_only_through_the_factory(seen, plannings=2)
    # This drive crosses BOTH consumers: a `Database` executes the attempt while
    # the engine re-lowers the same buffer as its emissions oracle. Two receivers
    # is what says the oracle planned on a planner of its own rather than
    # borrowing the transaction's — the shape the other engine entries reach
    # without a `Database` in play.
    assert len({id(one.planner) for one in seen.planned}) == 2
