"""Applying one neutral milestone topology to one observed row (m-unit-work).

A temporal strategy answers the topology of an authored mutation — which
milestone closes, and the interval and represented state of each successor —
without naming a single value. This module performs the other half: it resolves
that description against one predecessor and one authored row into the ordered
milestones the mutation opens, each with its Insert Origin.

Keeping the two halves apart is what makes the description reusable across a
resolved group. Keeping them in one place is what keeps every consumer of a
temporal expansion — the finalized steps a flush executes, and the tracked
current milestone a later mutation observes — deriving it identically.
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
    MilestoneTopology,
    OpenEnd,
    PredecessorEnd,
    PredecessorStart,
    SuccessorState,
    ValidTimeBound,
    ValidTimeWindow,
)

__all__ = ["OpenedMilestone", "TemporalAxes", "expand_milestone"]


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
class OpenedMilestone:
    """One successor resolved into the whole milestone row it opens.

    ``members`` is Attribute-named and complete — every carried member, every
    authored change, and every axis bound the mutation stamps — so it is both
    the row a finalized insert writes and the predecessor a later mutation
    observes.
    """

    origin: InsertOrigin
    members: Mapping[str, object]


def expand_milestone(
    topology: MilestoneTopology,
    axes: TemporalAxes,
    *,
    transaction_instant: object,
    authored: Mapping[str, object],
    valid_from: object | None = None,
    until: object | None = None,
    predecessor: PredecessorRow | None = None,
) -> tuple[OpenedMilestone, ...]:
    """The milestones ``topology`` opens for one predecessor and authored row.

    Every opened row carries the fresh Transaction-Time interval
    ``[transaction_instant, infinity)``: a successor is always current when it
    is written, whatever Valid-Time window it covers.
    """
    return tuple(
        OpenedMilestone(
            origin=_origin(successor.state, predecessor),
            members=_members(
                successor.state,
                axes,
                window=successor.valid_window,
                transaction_instant=transaction_instant,
                authored=authored,
                valid_from=valid_from,
                until=until,
                predecessor=predecessor,
            ),
        )
        for successor in topology.successors
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


def _members(
    state: SuccessorState,
    axes: TemporalAxes,
    *,
    window: ValidTimeWindow | None,
    transaction_instant: object,
    authored: Mapping[str, object],
    valid_from: object | None,
    until: object | None,
    predecessor: PredecessorRow | None,
) -> Mapping[str, object]:
    members = dict(_represented(state, authored, predecessor))
    if window is not None:
        assert axes.valid_start is not None and axes.valid_end is not None  # a windowed family
        members[axes.valid_start] = _bound(window.start, axes, valid_from, until, predecessor)
        members[axes.valid_end] = _bound(window.end, axes, valid_from, until, predecessor)
    members[axes.transaction_start] = transaction_instant
    members[axes.transaction_end] = INFINITY_LITERAL
    return members


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


def _bound(
    bound: ValidTimeBound,
    axes: TemporalAxes,
    valid_from: object | None,
    until: object | None,
    predecessor: PredecessorRow | None,
) -> object:
    match bound:
        case AuthoredFrom():
            assert valid_from is not None  # every windowed mutation authors one
            return valid_from
        case AuthoredUntil():
            assert until is not None  # every bounded mutation authors one
            return until
        case PredecessorStart():
            assert predecessor is not None and axes.valid_start is not None
            return predecessor.member(axes.valid_start)
        case PredecessorEnd():
            assert predecessor is not None and axes.valid_end is not None
            return predecessor.member(axes.valid_end)
        case OpenEnd():
            return INFINITY_LITERAL
