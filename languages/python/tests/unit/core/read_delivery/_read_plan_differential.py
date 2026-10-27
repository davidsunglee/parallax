"""Corpus reads, valid same-structure variants of them, and exact statement
observations, built independently of the planner's own operand traversal."""

from __future__ import annotations

import datetime as dt
import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Literal, cast

from parallax.conformance import _case_ingress, case_format, engine
from parallax.core._execution._read_query import resolve_read_query
from parallax.core.base import Float32 as Float32Type
from parallax.core.base import NeutralType, matches_neutral_type
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import deserialize
from parallax.core.object_query._resolved import (
    ResolvedAsOfSelection,
    ResolvedObjectQuery,
    ResolvedRangeSelection,
)
from parallax.core.predicate._resolved import (
    ResolvedAnd,
    ResolvedComparison,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedStringMatch,
)
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import scans_resolved_axis
from tests._support.binary32 import narrowed
from tests._support.sweep_goldens import COMPILE_EXERCISED, read_golden_statements


@dataclass(frozen=True, slots=True)
class CorpusRead:
    """One corpus read case's model, resolved query, and result form."""

    case: case_format.Case
    meta: Metamodel
    query: ResolvedObjectQuery
    result_form: Literal["row", "instance"]

    @property
    def golden_applies(self) -> bool:
        """Whether the case's one golden statement is this read's root planned
        alone: a compile-exercised, standalone read of no scanned axis, whose
        delivery orders its milestones first."""
        return (
            self.case.case_id in COMPILE_EXERCISED
            and not isinstance(_when(self.case).get("uow"), Mapping)
            and not scans_resolved_axis(self.query.temporal)
            and len(read_golden_statements(self.case)) == 1
        )


def _when(case: case_format.Case) -> Mapping[str, object]:
    return cast("Mapping[str, object]", case.document["when"])


def corpus_read(case: case_format.Case) -> CorpusRead:
    """``case``'s read as the binding resolves it before planning."""
    then = cast("Mapping[str, object]", case.document.get("then", {}))
    instance = "graph" in then or "graphs" in then
    meta = engine.load_case_metamodel(case)
    node = _case_ingress.normalize_case_query(deserialize(_when(case)["objectQuery"]), meta)
    query = resolve_read_query(node, model=meta, form="graph" if instance else "rows")
    return CorpusRead(case, meta, query, "instance" if instance else "row")


def selects_a_finite_instant(query: ResolvedObjectQuery) -> bool:
    return any(
        isinstance(selection, ResolvedAsOfSelection | ResolvedRangeSelection)
        for selection in query.temporal
    )


def varied(query: ResolvedObjectQuery) -> ResolvedObjectQuery:
    """``query`` with every authored operand changed to another valid value of
    the same exact carrier type, Decimal exponent, membership width, and affix
    escape category; an operand no such value exists for is kept."""
    return replace(query, predicate=_varied(query.predicate))


def _varied(predicate: ResolvedPredicate) -> ResolvedPredicate:
    match predicate:
        case ResolvedComparison(member=member, value=value, framework=False):
            return replace(predicate, value=_changed(value, member.type))
        case ResolvedRange(member=member, lower=lower, upper=upper):
            lower, upper = _ordered_change(lower, upper, member.type)
            return replace(predicate, lower=lower, upper=upper)
        case ResolvedMembership(member=member, values=tuple() as values):
            return replace(
                predicate, values=tuple(_changed(value, member.type) for value in values)
            )
        case ResolvedStringMatch(pattern=pattern):
            # A prefix of ordinary text escapes nothing, so the escape
            # category stays the authored one.
            return replace(predicate, pattern=f"v{pattern}")
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            return replace(predicate, operands=tuple(_varied(operand) for operand in operands))
        case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
            return replace(predicate, operand=_varied(operand))
        case ResolvedNarrow(operand=operand) if operand is not None:
            return replace(predicate, operand=_varied(operand))
        case ResolvedQuantifier(where=where) | ResolvedPresence(where=where) if where is not None:
            return replace(predicate, where=_varied(where))
        case _:
            return predicate


def _changed(value: object, neutral_type: NeutralType) -> object:
    if isinstance(value, bool):
        return not value
    for step in (1, -1):
        candidate = _stepped(value, neutral_type, step)
        if candidate is not None:
            return candidate
    return value


def _ordered_change(lower: Any, upper: Any, neutral_type: NeutralType) -> tuple[Any, Any]:
    """Both bounds moved the same way, so a valid range stays valid."""
    for step in (1, -1):
        moved = (_stepped(lower, neutral_type, step), _stepped(upper, neutral_type, step))
        if moved[0] is not None and moved[1] is not None and not cast("Any", moved[1]) < moved[0]:
            return moved
    return lower, upper


def _stepped(value: object, neutral_type: NeutralType, step: int) -> object | None:  # noqa: C901 - exhaustive dispatcher
    """A value of ``value``'s carrier type ordered ``step``'s way from it, if
    ``neutral_type`` admits one."""
    candidate: object
    try:
        match value:
            case bool():
                return None
            case int():
                candidate = value + step
            case float():
                candidate = value + step
                if isinstance(neutral_type, Float32Type):
                    candidate = narrowed(candidate)
                if candidate == value or not math.isfinite(candidate):
                    return None
            case Decimal():
                exponent = value.as_tuple().exponent
                assert isinstance(exponent, int)
                candidate = value + step * Decimal(1).scaleb(exponent)
            case str():
                candidate = f"v{value}" if step > 0 else None
            case bytes():
                candidate = b"v" + value if step > 0 else None
            case dt.datetime():
                candidate = value + dt.timedelta(microseconds=step)
            case dt.date():
                candidate = value + dt.timedelta(days=step)
            case dt.time():
                moved = dt.datetime.combine(dt.date(2000, 1, 2), value) + dt.timedelta(
                    microseconds=step
                )
                candidate = moved.time() if moved.date() == dt.date(2000, 1, 2) else None
            case uuid.UUID():
                candidate = uuid.UUID(int=value.int + step)
            case _:
                return None
    except (OverflowError, ValueError):
        return None
    if (
        candidate is None
        or type(candidate) is not type(value)
        or not matches_neutral_type(candidate, neutral_type)
    ):
        return None
    if isinstance(value, Decimal):
        assert isinstance(candidate, Decimal)
        if candidate.as_tuple().exponent != value.as_tuple().exponent:
            return None
    return candidate


def observed(read: CompiledRead) -> tuple[object, ...]:
    """Everything a delivered read observes of its statement, carriers compared
    by exact type, Decimal exponent, and float sign as well as value."""
    statement = read.statement
    return (
        read,
        statement.sql,
        tuple(_carrier(bind) for bind in statement.binds),
        statement.typed_bind_spans,
        statement.wire_bind_overrides,
        statement.wire_binds(),
    )


def _carrier(bind: object) -> tuple[object, ...]:
    if isinstance(bind, Decimal):
        return Decimal, bind, bind.as_tuple()
    if isinstance(bind, float):
        return float, bind, math.copysign(1.0, bind)
    return type(bind), bind
