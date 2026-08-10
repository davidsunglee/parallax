"""The compile-only recipe, and the runtime Write Plan that is never published.

Two halves of one contract. The compile lane reaches production's planning path
DIRECTLY — ``buffered_write`` into ``build_write_planner(model).plan(...)`` into
``stream_lowered(...)`` — so the emission oracle and the executed SQL are one
computation rather than two that agree. And runtime returns and retains no
``WritePlan``: there is no ``plan_neutral``, no ``compile_neutral``, no
``connect_neutral``, and no public flush, so a caller can neither reach a plan nor
decide when one executes.

Both are structural facts a reader would otherwise re-derive by walking every
entry point, which is exactly the kind of claim that rots silently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from _transact_support import RecordingPort, account_db, new_account

from _support.repo import REPO_ROOT
from parallax.conformance import case_format, engine
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import PlanningRequest, WritePlan, WritePlanner
from parallax.snapshot import handle
from parallax.snapshot.handle import Transaction

_FORBIDDEN_ENTRY_POINTS = ("plan_neutral", "compile_neutral", "connect_neutral", "flush_neutral")

_CASE: Path = (
    REPO_ROOT / "core" / "compatibility" / "cases" / "m-unit-work-003-fk-insert-ordering.yaml"
)


def test_the_compile_lane_names_the_same_seams_the_runtime_flush_does() -> None:
    """Not "an equivalent planner" — the identical factory and lowering
    function ``Database.transact`` injects, reached under their own names."""
    lane: Mapping[str, object] = vars(engine)
    assert lane["build_write_planner"] is handle.build_write_planner
    assert lane["stream_lowered"] is handle.stream_lowered


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
    original_plan = WritePlanner.plan

    def plan(self: WritePlanner, request: PlanningRequest) -> WritePlan:
        result = original_plan(self, request)
        planned.append(result)
        return result

    monkeypatch.setattr(WritePlanner, "plan", plan)
    case = case_format.load_case(_CASE)
    emissions, _round_trips = engine.compile_write_sequence_case(case, "postgres")

    assert planned, "the emissions come from a plan rather than from a re-lowering"
    assert len({id(value) for value in planned}) == len(planned), "no buffer is planned twice"
    model = engine.case_model(engine.load_case_metamodel(case))
    expected = [
        statement
        for value in planned
        for _step, statement in handle.stream_lowered(value, model, POSTGRES)
    ]
    assert [(emission.sql, emission.binds) for emission in emissions] == [
        (statement.sql, statement.binds) for statement in expected
    ]


def test_a_transaction_result_publishes_no_write_plan() -> None:
    port = RecordingPort()

    def body(tx: Transaction) -> None:
        tx.insert(new_account())

    result = account_db(port).transact(body)
    assert not _reaches_a_write_plan(result)


def test_the_public_surface_offers_no_plan_and_no_flush() -> None:
    exported = set(handle.__all__)
    assert "WritePlan" not in exported
    assert not exported.intersection(_FORBIDDEN_ENTRY_POINTS)
    for name in ("flush", *_FORBIDDEN_ENTRY_POINTS):
        assert not hasattr(handle.Transaction, name)
        assert not hasattr(handle.Database, name)


def _reaches_a_write_plan(value: object, seen: set[int] | None = None) -> bool:
    """Whether ``value``'s retained graph reaches a ``WritePlan`` at all.

    A reachability walk rather than a field check: the claim is that no plan
    SURVIVES the flush that consumed it, which an assertion about the result
    type's own fields would not catch.
    """
    seen = set() if seen is None else seen
    if id(value) in seen:
        return False
    seen.add(id(value))
    if isinstance(value, WritePlan):
        return True
    if isinstance(value, (str, bytes, int, float, bool, type(None))):
        return False
    if isinstance(value, Sequence):
        items = cast("Sequence[object]", value)
        return any(_reaches_a_write_plan(item, seen) for item in items)
    declared: Any = getattr(type(value), "__slots__", ())
    slots = (declared,) if isinstance(declared, str) else tuple(declared)
    attributes = (*slots, *getattr(value, "__dict__", {}))
    return any(
        _reaches_a_write_plan(getattr(value, name), seen)
        for name in attributes
        if hasattr(value, name)
    )
