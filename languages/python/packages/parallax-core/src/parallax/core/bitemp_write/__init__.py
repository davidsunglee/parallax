from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.metamodel import TemporalDimension
from parallax.core.txtime_write import TemporalPlanningError
from parallax.core.unit_work import (
    AUTHORED_FROM,
    AUTHORED_STATE,
    AUTHORED_UNTIL,
    CARRIED_STATE,
    CHANGED_STATE,
    OPEN_END,
    PREDECESSOR_END,
    PREDECESSOR_START,
    SUPERSEDED,
    TERMINATED,
    MilestoneClosure,
    MilestoneSuccessor,
    MilestoneTopology,
    ValidTimeWindow,
)

__all__ = ["RECTANGLE_SPLIT", "RectangleSplit"]

# The inactivation gates on the observed Transaction-Time start exactly as a
# single-axis close does: the Valid-Time end addresses the rectangle, and the
# concurrency condition is a separate fact.
_SUPERSEDES: Final = MilestoneClosure(
    cause=SUPERSEDED, gate_basis=TemporalDimension.TRANSACTION_TIME
)
_TERMINATES: Final = MilestoneClosure(
    cause=TERMINATED, gate_basis=TemporalDimension.TRANSACTION_TIME
)

_HEAD: Final = MilestoneSuccessor(
    state=CARRIED_STATE, valid_window=ValidTimeWindow(start=PREDECESSOR_START, end=AUTHORED_FROM)
)
_OLD_TAIL: Final = MilestoneSuccessor(
    state=CARRIED_STATE, valid_window=ValidTimeWindow(start=AUTHORED_UNTIL, end=PREDECESSOR_END)
)
_MIDDLE: Final = MilestoneSuccessor(
    state=CHANGED_STATE, valid_window=ValidTimeWindow(start=AUTHORED_FROM, end=AUTHORED_UNTIL)
)
_NEW_TAIL: Final = MilestoneSuccessor(
    state=CHANGED_STATE, valid_window=ValidTimeWindow(start=AUTHORED_FROM, end=PREDECESSOR_END)
)
_OPEN_RECTANGLE: Final = MilestoneSuccessor(
    state=AUTHORED_STATE, valid_window=ValidTimeWindow(start=AUTHORED_FROM, end=OPEN_END)
)
_BOUNDED_RECTANGLE: Final = MilestoneSuccessor(
    state=AUTHORED_STATE, valid_window=ValidTimeWindow(start=AUTHORED_FROM, end=AUTHORED_UNTIL)
)

_TOPOLOGIES: Final[dict[str, MilestoneTopology]] = {
    "insert": MilestoneTopology(closure=None, successors=(_OPEN_RECTANGLE,)),
    "insertUntil": MilestoneTopology(closure=None, successors=(_BOUNDED_RECTANGLE,)),
    "update": MilestoneTopology(closure=_SUPERSEDES, successors=(_HEAD, _NEW_TAIL)),
    "updateUntil": MilestoneTopology(closure=_SUPERSEDES, successors=(_HEAD, _MIDDLE, _OLD_TAIL)),
    "terminate": MilestoneTopology(closure=_TERMINATES, successors=(_HEAD,)),
    "terminateUntil": MilestoneTopology(closure=_TERMINATES, successors=(_HEAD, _OLD_TAIL)),
}


@dataclass(frozen=True, slots=True)
class RectangleSplit:
    """The Bitemporal facet's topology answer."""

    def topology(self, mutation: str) -> MilestoneTopology:
        """``mutation``'s neutral rectangle split, or one of its degenerates."""
        described = _TOPOLOGIES.get(mutation)
        if described is None:
            raise TemporalPlanningError(f"{mutation!r} is not a Bitemporal milestone mutation")
        return described


RECTANGLE_SPLIT: Final[RectangleSplit] = RectangleSplit()
