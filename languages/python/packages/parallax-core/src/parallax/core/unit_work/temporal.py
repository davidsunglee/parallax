from __future__ import annotations

from dataclasses import dataclass

from parallax.core.base import INFINITY
from parallax.core.metamodel import AsOfAxisMetadata
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work.strategy import (
    AuthoredFrom,
    AuthoredUntil,
    MilestoneSuccessor,
    OpenEnd,
    PredecessorEnd,
    PredecessorStart,
    SuccessorState,
    ValidTimeBound,
)
from parallax.core.write_plan.observe import PredecessorRow

__all__ = [
    "ResolvedSuccessor",
    "bound_cell",
    "bound_value",
    "resolve_successors",
]


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
    """One Milestone Successor of a topology table with every group-wide fact
    already decided: its remaining unknowns are one row's own predecessor and
    authored values."""

    state: SuccessorState
    window: ResolvedWindow | None = None


def resolve_successors(
    successors: tuple[MilestoneSuccessor, ...],
    *,
    valid_time_window: TimeInterval | None = None,
) -> tuple[ResolvedSuccessor, ...]:
    """``successors`` with every Valid-Time bound group-wide data can decide.

    An authored bound or the open end is the same for every row one
    Materialized Write Group resolves, so binding it here — once, for the
    whole group — leaves each row's successor a pure data substitution.
    """
    return tuple(
        ResolvedSuccessor(
            state=successor.state,
            window=(
                None
                if successor.valid_window is None
                else ResolvedWindow(
                    start=_resolve_bound(successor.valid_window.start, valid_time_window),
                    end=_resolve_bound(successor.valid_window.end, valid_time_window),
                )
            ),
        )
        for successor in successors
    )


def _resolve_bound(bound: ValidTimeBound, window: TimeInterval | None) -> ResolvedBound:
    match bound:
        case AuthoredFrom():
            assert window is not None  # every windowed mutation authors one
            return _Literal(window.start)
        case AuthoredUntil():
            assert window is not None and window.end is not INFINITY  # a bounded mutation's
            return _Literal(window.end)
        case OpenEnd():
            return _Literal(INFINITY)
        case PredecessorStart() | PredecessorEnd():
            return bound


def bound_value(resolved: ResolvedBound, start: object, end: object) -> object:
    """The Valid-Time bound ``resolved`` names, given its predecessor's own
    Valid-Time ``start`` and ``end`` cells."""
    match resolved:
        case _Literal(value):
            return value
        case PredecessorStart():
            return start
        case PredecessorEnd():
            return end


def bound_cell(
    resolved: ResolvedBound, valid_time: AsOfAxisMetadata, predecessor: PredecessorRow
) -> object:
    """The Valid-Time bound ``resolved`` names, reading only the predecessor
    cell it needs."""
    match resolved:
        case _Literal(value):
            return value
        case PredecessorStart():
            return predecessor.cell(valid_time.start_attribute)
        case PredecessorEnd():
            return predecessor.cell(valid_time.end_attribute)
