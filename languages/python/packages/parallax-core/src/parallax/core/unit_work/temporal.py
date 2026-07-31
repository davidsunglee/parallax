"""Applying one neutral milestone topology to one observed row (m-unit-work).

A temporal strategy answers the topology of an authored mutation — which
milestone closes, and the interval and represented state of each successor —
without naming a single value. This module performs the other half, split into
two steps so a caller resolving many rows from one topology (a Materialized
Write Group) does the first step once and the second per row:

- :func:`resolve_successors` resolves ``topology.successors`` as far as
  group-wide data (the mutation's own authored Valid-Time bounds) allows,
  fixing which Insert Origin kind and which bound expression applies to each
  successor without touching a predecessor.
- :func:`bind_successor` substitutes one row's own predecessor and authored
  values into an already-resolved successor, producing its concrete row and
  Insert Origin.

:func:`expand_milestone` composes both for a caller resolving a single
predecessor and authored row directly. Keeping the two halves apart is what
keeps every consumer of a temporal expansion — the finalized steps a flush
executes, and the tracked current milestone a later mutation observes —
deriving it identically.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from parallax.core.base import INFINITY_LITERAL
from parallax.core.unit_work.observe import PredecessorRow
from parallax.core.unit_work.planned import (
    NEW_LINEAGE,
    CarriedFrom,
    ChangedFrom,
    InsertOrigin,
)
from parallax.core.unit_work.strategy import (
    AuthoredFrom,
    AuthoredState,
    AuthoredUntil,
    CarriedState,
    ChangedState,
    MilestoneSuccessor,
    MilestoneTopology,
    OpenEnd,
    PredecessorEnd,
    PredecessorStart,
    SuccessorState,
    ValidTimeBound,
)

__all__ = [
    "ResolvedSuccessor",
    "SuccessorRow",
    "TemporalAxes",
    "bind_successor",
    "expand_milestone",
    "resolve_successors",
]


@dataclass(frozen=True, slots=True)
class TemporalAxes:
    """The Attribute names one family's As-Of Axes bound their intervals with.

    Valid-Time names are absent on a Transaction-Time-Only family, which is the
    same condition that leaves a successor without a Valid-Time window.
    """

    transaction_start: str
    transaction_end: str
    valid_start: str | None = None
    valid_end: str | None = None


@dataclass(frozen=True, slots=True)
class SuccessorRow:
    """One Milestone Successor resolved into its concrete row and Insert Origin.

    ``members`` is Attribute-named and complete — every carried member, every
    authored change, and every axis bound the mutation stamps — so it is both
    the row a finalized insert writes and the predecessor a later mutation
    observes.
    """

    origin: InsertOrigin
    members: Mapping[str, object]


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
    authored: Mapping[str, object],
    predecessor: PredecessorRow | None,
) -> SuccessorRow:
    """One already-resolved successor, bound against one row's own
    predecessor and authored values.

    Every opened row carries the fresh Transaction-Time interval
    ``[transaction_instant, infinity)``: a successor is always current when it
    is written, whatever Valid-Time window it covers.
    """
    members = dict(_represented(successor.state, authored, predecessor))
    if successor.window is not None:
        assert axes.valid_start is not None and axes.valid_end is not None  # a windowed family
        members[axes.valid_start] = _bind_bound(successor.window.start, axes, predecessor)
        members[axes.valid_end] = _bind_bound(successor.window.end, axes, predecessor)
    members[axes.transaction_start] = transaction_instant
    members[axes.transaction_end] = INFINITY_LITERAL
    return SuccessorRow(origin=_origin(successor.state, predecessor), members=members)


def expand_milestone(
    topology: MilestoneTopology,
    axes: TemporalAxes,
    *,
    transaction_instant: object,
    authored: Mapping[str, object],
    valid_from: object | None = None,
    until: object | None = None,
    predecessor: PredecessorRow | None = None,
) -> tuple[SuccessorRow, ...]:
    """The milestones ``topology`` opens for one predecessor and authored row.

    Composes :func:`resolve_successors` and :func:`bind_successor` for a
    caller resolving a single row directly.
    """
    resolved = resolve_successors(topology.successors, valid_from=valid_from, until=until)
    return tuple(
        bind_successor(
            successor,
            axes,
            transaction_instant=transaction_instant,
            authored=authored,
            predecessor=predecessor,
        )
        for successor in resolved
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


def _represented(
    state: SuccessorState, authored: Mapping[str, object], predecessor: PredecessorRow | None
) -> Mapping[str, object]:
    """The successor's represented state before its own axis bounds are stamped.

    A changed successor overlays the authored change set on the predecessor,
    which is why a sparse authored row still opens a complete milestone: every
    member it does not name carries forward unchanged.
    """
    match state:
        case AuthoredState():
            return authored
        case CarriedState():
            assert predecessor is not None  # a carried successor observed one
            return predecessor.members
        case ChangedState():
            assert predecessor is not None  # a changed successor observed one
            return {**predecessor.members, **authored}


def _bind_bound(
    resolved: ResolvedBound, axes: TemporalAxes, predecessor: PredecessorRow | None
) -> object:
    match resolved:
        case _Literal(value):
            return value
        case PredecessorStart():
            assert predecessor is not None and axes.valid_start is not None
            return predecessor.member(axes.valid_start)
        case PredecessorEnd():
            assert predecessor is not None and axes.valid_end is not None
            return predecessor.member(axes.valid_end)
