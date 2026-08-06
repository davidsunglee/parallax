"""``parallax.core.bitemp_write`` enforcement scope (m-bitemp-write).

The Bitemporal (Valid Time + Transaction Time) RECTANGLE-SPLIT planning scope: it
extends :mod:`parallax.core.txtime_write`'s close-and-chain arithmetic to a second
axis. Like its sibling it renders no SQL, takes no dialect, and contributes its
arithmetic to write finalization as a neutral topology description
(`m-bitemp-write.md` "What this module contributes to planning").

Six mutations, each a closure (the inactivation) plus zero-to-three opened
rectangles, in the facet's canonical order — head, middle, tail where each
exists:

- **insert** / **insertUntil** — no closure and one rectangle carrying the
  authored row alone, over ``[validFrom, infinity)`` or the bounded
  ``[validFrom, until)``.
- **updateUntil** — `Superseded`, then the **head** ``[obsStart, validFrom)``
  carrying the predecessor's state, the **middle** ``[validFrom, until)``
  carrying it changed, and the **tail** ``[until, obsEnd)`` carrying it again.
- **terminateUntil** — `Terminated`, then head and tail only: the window between
  them is left covered by no current-on-Transaction-Time rectangle.
- **update** — the two-way degenerate of ``updateUntil``: `Superseded`, a carried
  head ``[obsStart, validFrom)``, and a changed tail ``[validFrom, obsEnd)``
  running unbounded from the correction.
- **terminate** — `Terminated` and a carried head only: the value is absent from
  ``validFrom`` onward.

A terminate's surviving head and tail are carried from their predecessor, never
themselves terminated: the closure's cause records the absence.

The description names no bound value, payload, or observation — only where each
bound comes from — so one description serves every rectangle a predicate-selected
mutation resolves. Finalization applies it
(:func:`~parallax.core.unit_work.temporal.expand_milestone`), and the two-axis
address the inactivation needs is the Milestone Target it settles alongside: the
observed rectangle's own Valid-Time end is what keeps the close on the intended
rectangle when several disjoint rectangles of one key are current on Transaction
Time, while the observed Transaction-Time start rides the gate alone.

Prior art (Reladomo; semantics, not idioms): the rectangle dispatch mirrors
``GenericBiTemporalDirector.updateUntil`` / ``.splitTailEnd`` (research §6, the
bitemporal rectangle split); the plain (unbounded) trio is the open-window,
tailless degenerate of the same director's unbounded ``insert`` / ``update`` /
``terminate``.
"""

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
