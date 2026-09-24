from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.metamodel import TemporalDimension
from parallax.core.unit_work import (
    AUTHORED_STATE,
    CHANGED_STATE,
    SUPERSEDED,
    TERMINATED,
    MilestoneClosure,
    MilestoneSuccessor,
    MilestoneTopology,
)

__all__ = [
    "MILESTONE_CHAIN",
    "TemporalPlanningError",
]

_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
_TERMINATE_MUTATIONS: Final[frozenset[str]] = frozenset({"terminate", "terminateUntil"})
_UPDATE_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})

# The one axis this facet closes on, and therefore the one an optimistic close
# gates on: a Transaction-Time-Only milestone carries no other start to observe.
_GATE_BASIS: Final[TemporalDimension] = TemporalDimension.TRANSACTION_TIME


class TemporalPlanningError(ValueError):
    """A temporal mutation cannot be described (a shape this scope's own caller
    is responsible for never producing, e.g. a verb this facet does not
    recognize; a defensive backstop, not a normal-path outcome for a well-formed
    instruction)."""


@dataclass(frozen=True, slots=True)
class TransactionTimeChaining:
    """The Transaction-Time-Only facet's topology answer."""

    def topology(self, mutation: str) -> MilestoneTopology:
        """``mutation``'s neutral close-and-chain topology.

        A ``*Until`` verb reaching this facet carries a Valid-Time bound the
        target declares no axis for, so its successor has no window and the
        bound is simply unused — the verb chains exactly as its unbounded
        sibling does.
        """
        if mutation in _INSERT_MUTATIONS:
            return MilestoneTopology(
                closure=None, successors=(MilestoneSuccessor(state=AUTHORED_STATE),)
            )
        if mutation in _TERMINATE_MUTATIONS:
            return MilestoneTopology(
                closure=MilestoneClosure(cause=TERMINATED, gate_basis=_GATE_BASIS), successors=()
            )
        if mutation in _UPDATE_MUTATIONS:
            return MilestoneTopology(
                closure=MilestoneClosure(cause=SUPERSEDED, gate_basis=_GATE_BASIS),
                successors=(MilestoneSuccessor(state=CHANGED_STATE),),
            )
        raise TemporalPlanningError(
            f"{mutation!r} is not a Transaction-Time-Only milestone mutation"
        )


MILESTONE_CHAIN: Final[TransactionTimeChaining] = TransactionTimeChaining()
