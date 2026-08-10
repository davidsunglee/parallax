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

from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
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


class _Slotted:
    __slots__ = ("held",)

    def __init__(self, held: object) -> None:
        self.held = held


class _SlottedSubclass(_Slotted):
    __slots__ = ("also",)

    def __init__(self, held: object, also: object) -> None:
        super().__init__(held)
        self.also = also


class _PrivateSlotted:
    __slots__ = ("__held",)

    def __init__(self, held: object) -> None:
        self.__held = held


class _Attributed:
    def __init__(self, held: object) -> None:
        self.held = held


_RETAINING_SHAPES: tuple[tuple[str, Callable[[WritePlan], object]], ...] = (
    ("itself", lambda plan: plan),
    ("a-sequence", lambda plan: [plan]),
    ("a-mapping-value", lambda plan: {"k": plan}),
    ("a-mapping-key", lambda plan: {plan: "v"}),
    ("a-set", lambda plan: {plan}),
    ("a-frozenset", lambda plan: frozenset({plan})),
    ("an-instance-dict", _Attributed),
    ("a-slot", _Slotted),
    ("a-private-slot", _PrivateSlotted),
    ("an-inherited-slot", lambda plan: _SlottedSubclass(plan, None)),
    ("nested", lambda plan: _Attributed([{"k": {plan}}])),
)


@pytest.mark.parametrize(
    "retaining", [pytest.param(shape, id=name) for name, shape in _RETAINING_SHAPES]
)
def test_the_reachability_walk_reaches_every_shape_a_plan_could_hide_in(
    retaining: Callable[[WritePlan], object],
) -> None:
    """The negative assertion above is only worth what this walk covers, so each
    container shape carries a plan the walk must find. ``an-inherited-slot``
    hides it on the BASE class's slot while the subclass declares its own, which
    is the shadowing case a type-level ``__slots__`` read misses;
    ``a-private-slot`` hides it under a slot whose declared spelling is not the
    attribute name, which is the mangling case a raw ``__slots__`` read misses."""
    plan = WritePlan()
    assert _reaches_a_write_plan(retaining(plan))


def test_the_reachability_walk_answers_no_for_a_graph_holding_none() -> None:
    held: list[dict[str, set[object]]] = [{"k": {frozenset[object](), "s", 1}}]
    assert not _reaches_a_write_plan(_Attributed(held))


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
    type's own fields would not catch. The walk has to cover every shape a
    reference can hide in — a sequence, a mapping's keys or values, a set, an
    instance dictionary, and a slot declared anywhere on the MRO under the name
    the slot actually binds — because the assertion it serves is a NEGATIVE one:
    a container this missed would report the absence it exists to detect.

    Its boundary is data: what a result HOLDS. A reference reachable only by
    executing code (a closure cell, a property, a descriptor computing a value)
    is outside it, and so is a weak reference, which retains nothing. The
    surfaces under test are frozen data classes, tuples, and mappings, so a plan
    that survived them would have to survive as one of the shapes above.
    """
    seen = set() if seen is None else seen
    if id(value) in seen:
        return False
    seen.add(id(value))
    if isinstance(value, WritePlan):
        return True
    if isinstance(value, (str, bytes, bytearray, int, float, complex, bool, type(None))):
        return False
    if isinstance(value, Mapping):
        entries = cast("Mapping[object, object]", value)
        return any(_reaches_a_write_plan(item, seen) for entry in entries.items() for item in entry)
    if isinstance(value, (Sequence, AbstractSet)):
        items = cast("Iterable[object]", value)
        return any(_reaches_a_write_plan(item, seen) for item in items)
    return any(
        _reaches_a_write_plan(getattr(value, name), seen)
        for name in _reference_names(value)
        if hasattr(value, name)
    )


def _reference_names(value: object) -> tuple[str, ...]:
    """Every attribute name ``value`` can hold a reference under.

    ``__slots__`` is read off each class's own ``__dict__`` along the MRO rather
    than off the type: a subclass declaring slots of its own SHADOWS the
    attribute lookup, so a base class's slots would otherwise go unwalked. Each
    declared slot is then mangled against the class that declared it, because a
    private slot's attribute name is not its declared spelling and reading the
    spelling back finds nothing.
    """
    names: list[str] = []
    for cls in type(value).__mro__:
        declared: Any = cls.__dict__.get("__slots__", ())
        spellings = (declared,) if isinstance(declared, str) else tuple(declared)
        names.extend(_mangled(cls, spelling) for spelling in spellings)
    names.extend(getattr(value, "__dict__", {}))
    return tuple(names)


def _mangled(cls: type, spelling: str) -> str:
    """``spelling`` as the attribute name it becomes inside ``cls``'s body.

    Python mangles a private identifier — two leading underscores, at most one
    trailing — to ``_<class>__<name>`` with the class's own leading underscores
    stripped, and a slot's descriptor is created under that mangled name.
    """
    if spelling.startswith("__") and not spelling.endswith("__"):
        return f"_{cls.__name__.lstrip('_')}{spelling}"
    return spelling
