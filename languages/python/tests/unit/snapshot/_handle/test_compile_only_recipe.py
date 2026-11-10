"""The compile-only recipe, and the runtime Write Plan that is never published.

Two halves of one contract. The compile lane reaches production's write path
DIRECTLY — each simulated transaction buffers into an ordinary ``UnitOfWork``
planned by ``build_write_planner(model)``, whose steps simulated step execution
lowers through ``stream_physical(...)`` — so the emission oracle and the
executed SQL are one computation rather than two that agree. And the public
surface offers no ``WritePlan``: there is no ``plan_neutral``, no
``compile_neutral``, no ``connect_neutral``, and no public flush, so a caller can
neither reach a plan nor decide when one executes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import parallax.snapshot
from parallax.conformance import case_format, engine
from parallax.core._execution._write_lowering import stream_physical
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import WritePlanner, WritePlanningRequest
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import WritePlan
from parallax.snapshot import Database, TxnContext
from tests._support.planner_probes import plan_steps
from tests._support.repo import REPO_ROOT

_FORBIDDEN_ENTRY_POINTS = ("plan_neutral", "compile_neutral", "connect_neutral", "flush_neutral")

_CASE: Path = (
    REPO_ROOT / "core" / "compatibility" / "cases" / "m-unit-work-003-fk-insert-ordering.yaml"
)


def test_the_compile_lane_emits_exactly_one_plans_own_lowering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Measured on output rather than by spying on the lowering: the case's
    emissions ARE the production lowering of the plans the lane planned, in
    order, so a re-lowered or hand-rolled emission would show up as a difference.

    A write sequence is a sequence of INDEPENDENT units of work, so it plans once
    per entry; what the lane never does is plan one buffer twice to predict what
    the first plan would emit.
    """
    planned: list[WritePlan] = []
    original_finalize = WritePlanner.finalize

    def finalize(self: WritePlanner, request: WritePlanningRequest) -> WritePlan:
        result = original_finalize(self, request)
        planned.append(result)
        return result

    monkeypatch.setattr(WritePlanner, "finalize", finalize)
    case = case_format.load_case(_CASE)
    emissions, _database_calls = engine.compile_write_sequence_case(case, "postgres")

    assert planned, "the emissions come from a plan rather than from a re-lowering"
    assert len({id(value) for value in planned}) == len(planned), "no buffer is planned twice"
    model = engine.load_case_metamodel(case)
    expected = [
        statement
        for value in planned
        for statement in stream_physical(
            plan_steps(value), LayoutPayloadPreparer(model), model, POSTGRES
        )
    ]
    assert [(emission.sql, emission.binds) for emission in emissions] == [
        (statement.sql, statement.binds) for statement in expected
    ]


def test_the_public_surface_offers_no_plan_and_no_flush() -> None:
    exported = set(parallax.snapshot.__all__)
    assert "WritePlan" not in exported
    assert not exported.intersection(_FORBIDDEN_ENTRY_POINTS)
    for name in ("flush", *_FORBIDDEN_ENTRY_POINTS):
        assert not hasattr(TxnContext, name)
        assert not hasattr(Database, name)
