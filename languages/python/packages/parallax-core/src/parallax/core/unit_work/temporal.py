from __future__ import annotations

from dataclasses import dataclass

from parallax.core.base import INFINITY_LITERAL
from parallax.core.metamodel import AttributeIdentity, ValueObjectIdentity
from parallax.core.unit_work.observe import PredecessorRow
from parallax.core.unit_work.planned import (
    NEW_LINEAGE,
    CarriedFrom,
    ChangedFrom,
    InsertEntry,
    InsertOrigin,
    PlannedValue,
    adopt_planned_row,
)
from parallax.core.unit_work.strategy import (
    AuthoredFrom,
    AuthoredState,
    AuthoredUntil,
    CarriedState,
    ChangedState,
    MilestoneSuccessor,
    OpenEnd,
    PredecessorEnd,
    PredecessorStart,
    SuccessorState,
    ValidTimeBound,
)

__all__ = [
    "ResolvedSuccessor",
    "TemporalAxes",
    "bind_successor",
    "resolve_successors",
]


@dataclass(frozen=True, slots=True)
class TemporalAxes:
    """The Attribute identities one family's As-Of Axes bind intervals with.

    Valid-Time identities are absent on a Transaction-Time-Only family, which is the
    same condition that leaves a successor without a Valid-Time window.
    """

    transaction_start: AttributeIdentity
    transaction_end: AttributeIdentity
    valid_start: AttributeIdentity | None = None
    valid_end: AttributeIdentity | None = None


@dataclass(frozen=True, slots=True)
class _Literal:
    """One Valid-Time bound already resolved to a group-wide constant."""

    value: object


type ResolvedBound = _Literal | PredecessorStart | PredecessorEnd
"""One successor's Valid-Time bound, resolved as far as group-wide data
allows: a literal value once the mutation's own authored bound or the open
end already decides it, or the Predecessor Start/End marker unchanged when
only a row's own predecessor can supply it."""


@dataclass(frozen=True, slots=True)
class ResolvedWindow:
    """One successor's Valid-Time window with every group-wide bound resolved."""

    start: ResolvedBound
    end: ResolvedBound


@dataclass(frozen=True, slots=True)
class ResolvedSuccessor:
    """One Milestone Successor with every group-wide fact already decided.

    ``state`` fixes the Insert Origin kind (`m-unit-work` "Insert Origin and
    Close Cause"): a resolved successor's ONLY remaining unknowns are one
    row's own predecessor and authored values, which :func:`bind_successor`
    substitutes.
    """

    state: SuccessorState
    window: ResolvedWindow | None = None


def resolve_successors(
    successors: tuple[MilestoneSuccessor, ...],
    *,
    valid_from: object | None = None,
    until: object | None = None,
) -> tuple[ResolvedSuccessor, ...]:
    """``successors`` with every Valid-Time bound group-wide data can decide.

    An authored bound or the open end is the same for every row one
    Materialized Write Group resolves, so binding it here — once, for the
    whole group — is what keeps :func:`bind_successor` a pure per-row data
    substitution rather than a repeated decision.
    """
    return tuple(
        ResolvedSuccessor(
            state=successor.state,
            window=(
                None
                if successor.valid_window is None
                else ResolvedWindow(
                    start=_resolve_bound(successor.valid_window.start, valid_from, until),
                    end=_resolve_bound(successor.valid_window.end, valid_from, until),
                )
            ),
        )
        for successor in successors
    )


def _resolve_bound(
    bound: ValidTimeBound, valid_from: object | None, until: object | None
) -> ResolvedBound:
    match bound:
        case AuthoredFrom():
            assert valid_from is not None  # every windowed mutation authors one
            return _Literal(valid_from)
        case AuthoredUntil():
            assert until is not None  # every bounded mutation authors one
            return _Literal(until)
        case OpenEnd():
            return _Literal(INFINITY_LITERAL)
        case PredecessorStart() | PredecessorEnd():
            return bound


def bind_successor(
    successor: ResolvedSuccessor,
    axes: TemporalAxes,
    *,
    transaction_instant: object,
    attributes: dict[AttributeIdentity, PlannedValue],
    value_objects: dict[ValueObjectIdentity, object],
    predecessor: PredecessorRow | None,
) -> InsertEntry:
    """One already-resolved successor built directly into its final insert entry.

    Every opened row carries the fresh Transaction-Time interval
    ``[transaction_instant, infinity)``: a successor is always current when it
    is written, whatever Valid-Time window it covers.
    """
    if successor.window is not None:
        assert axes.valid_start is not None and axes.valid_end is not None  # a windowed family
        attributes[axes.valid_start] = _bind_bound(successor.window.start, axes, predecessor)
        attributes[axes.valid_end] = _bind_bound(successor.window.end, axes, predecessor)
    attributes[axes.transaction_start] = transaction_instant
    attributes[axes.transaction_end] = INFINITY_LITERAL
    return InsertEntry(
        row=adopt_planned_row(attributes, value_objects),
        origin=_origin(successor.state, predecessor),
    )


def _origin(state: SuccessorState, predecessor: PredecessorRow | None) -> InsertOrigin:
    match state:
        case AuthoredState():
            return NEW_LINEAGE
        case CarriedState():
            assert predecessor is not None  # a carried successor observed one
            return CarriedFrom(predecessor=predecessor)
        case ChangedState():
            assert predecessor is not None  # a changed successor observed one
            return ChangedFrom(predecessor=predecessor)


def _bind_bound(
    resolved: ResolvedBound, axes: TemporalAxes, predecessor: PredecessorRow | None
) -> object:
    match resolved:
        case _Literal(value):
            return value
        case PredecessorStart():
            assert predecessor is not None and axes.valid_start is not None
            return predecessor.member(axes.valid_start.name)
        case PredecessorEnd():
            assert predecessor is not None and axes.valid_end is not None
            return predecessor.member(axes.valid_end.name)
