from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.internal.db_port import AcquisitionReason, FallbackReason, Route, RoutePolicy

__all__ = ["PlanStep", "RoutePlan"]


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One route an acquisition may be served on, and the share of the
    acquisition budget, measured from its start, by which that route must have
    served it."""

    route: Route
    share: float


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """The routes one policy's acquisitions try, in order.

    Pure: it reads no route's state and no clock. Every step but the last is
    one a classified failure may leave for the next, and the last always spends
    whatever remains of the whole budget.
    """

    steps: tuple[PlanStep, ...]

    @classmethod
    def for_policy(cls, policy: RoutePolicy, *, has_reader: bool) -> RoutePlan:
        """The plan ``policy`` is served by.

        Core resolves a policy against the routes a runtime declares before
        asking, so a reader policy without a reader is a caller defect rather
        than a condition to classify.
        """
        if policy == "writer_only":
            return _WRITER_ONLY
        if has_reader and policy == "reader_only":
            return _READER_ONLY
        if has_reader and policy == "reader_preferred":
            return _READER_PREFERRED
        raise ValueError(f"this runtime does not serve read_policy={policy!r}")

    @staticmethod
    def falls_back_on(
        failure: AcquisitionReason | Literal["connection_lost"],
    ) -> FallbackReason | None:
        """The fallback a step's failure earns, or ``None`` where it ends the acquisition.

        Only a route that could not be reached and a connection lost while it
        was still being set up qualify: anything else — a spent share, a
        refused credential, login, or role, a closed runtime — is something the
        next route would not fix, or a healthy route merely being busy.
        """
        if failure == "unavailable":
            return "unavailable"
        if failure == "connection_lost":
            return "connection_lost"
        return None


_WRITER_ONLY: Final = RoutePlan((PlanStep("writer", 1.0),))
_READER_ONLY: Final = RoutePlan((PlanStep("reader", 1.0),))
_READER_PREFERRED: Final = RoutePlan((PlanStep("reader", 0.5), PlanStep("writer", 1.0)))
