"""Every write lane plans through the composition-root factory.

``parallax.snapshot.handle.build_write_planner`` is the one place the optional
policy modules are wired into a Write Planner, so a lane that built a planner of
its own would plan under a second set of strategies free to drift from
production's. This grades that as behavior: the factory is made to hand back
planners this module can recognize, a real write is driven through each lane,
and every planning the drive performed is required to be one of theirs, in the
number that lane is expected to perform.

What the grader sees is a planning that runs on a ``WritePlanner``, and that is
the whole of what it decides. A lane obtaining its plan from an unrelated
implementation of the same interface — one inheriting nothing, and so absent
from the subclass registry too — performs no planning this module records, on a
driven lane as much as on any other. Nothing in the tree closes that shape. The
count narrows it: a lane planning partly through the factory and partly around
it comes up short, which is what makes the exact number load-bearing rather than
incidental.

The lanes driven here are ENUMERATED — the `Database` lane, and the conformance
engine's writeSequence, readless predicate write, and conflict entries — and
that enumeration is this module's other limit: a write lane added later and not
driven here is not graded here, and this module still passes. What covers the
shapes that limit admits is `test_source_enforcement_topology.py`, which finds
the spelling ``WritePlanner(`` in ``_planning.py`` alone and reads
``WritePlanner.__subclasses__()`` for a second planner class — so a new lane
reaches a planner through this factory, or else constructs one under an aliased
name, and that last is what neither module catches.

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

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from _transact_support import NEW_ROW, RecordingPort, account_db, new_account

from _support import mirrored_models as mm
from _support.repo import REPO_ROOT
from parallax.conformance import case_format, engine
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    NO_AUDIT,
    AuditStrategy,
    BatchingStrategy,
    ConcurrencyStrategy,
    PlanningRequest,
    TemporalStrategy,
    VersionObservation,
    WriteInstruction,
    WritePlan,
    WritePlanner,
    instructions,
)
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


@dataclass(slots=True)
class _Composition:
    """One drive's planning provenance: the planners the composition root built
    while it ran, and every planning that ran, each with its receiver."""

    lane: str
    built: list[_Built]
    planned: list[tuple[WritePlanner, PlanningRequest]]

    def escaped(self) -> list[PlanningRequest]:
        """The plannings whose receiver the composition root did not build."""
        return [
            request
            for planner, request in self.planned
            if not any(planner is built.planner for built in self.built)
        ]


def _watch(lane: str, monkeypatch: pytest.MonkeyPatch) -> _Composition:
    """Make the composition root hand back recognizable planners for ``lane``, and
    record every planning any planner performs while it is installed.

    What is replaced is the factory's own name for the planner CLASS, not the
    factory: both consumers bind ``build_write_planner`` at import time, so a
    patch of that name would intercept neither, while the class name is read
    inside the factory body on every call. ``raising`` is left on, so the day
    ``_planning`` stops holding that name this fails rather than silently
    watching nothing.

    ``plan`` is watched on the class rather than on the built planners, because
    that is what makes a planning that ran on some OTHER planner VISIBLE instead
    of merely absent — the one way a lane planning partly through the factory and
    partly around it can be told from one planning wholly through it.
    """
    seen = _Composition(lane=lane, built=[], planned=[])
    planning = WritePlanner.plan

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
        seen.planned.append((self, request))
        return planning(self, request)

    monkeypatch.setattr(_planning, "WritePlanner", construct)
    monkeypatch.setattr(WritePlanner, "plan", plan)
    return seen


def _assert_planned_only_through_the_factory(seen: _Composition, plannings: int) -> None:
    escaped = seen.escaped()
    assert not escaped, (
        f"{seen.lane}: {len(escaped)} of {len(seen.planned)} plannings ran on a planner the "
        f"composition root did not build (it built {len(seen.built)}); the first of them "
        f"planned {_buffer_shapes(escaped[0])}"
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
    assert all(planner is seen.built[0].planner for planner, _request in seen.planned)


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
    assert len({id(planner) for planner, _request in seen.planned}) == 2
