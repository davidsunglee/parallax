from __future__ import annotations

import datetime as _dt
from collections.abc import Iterator
from dataclasses import dataclass

from parallax.core.internal.metamodel import AsOfAxisMetadata, AttributeIdentity


@dataclass(frozen=True, slots=True)
class LatestPerspective:
    """The current milestone on ``axis``: its end is the open bound."""

    axis: AsOfAxisMetadata


@dataclass(frozen=True, slots=True)
class AtPerspective:
    """The milestone on ``axis`` whose half-open interval contains ``instant``."""

    axis: AsOfAxisMetadata
    instant: _dt.datetime


type AxisPerspective = LatestPerspective | AtPerspective


@dataclass(frozen=True, slots=True)
class TemporalPerspective:
    """The milestones visible on each As-Of Axis a target declares.

    An absent field means the target declares no axis in that dimension, so a
    perspective with neither field is that of a non-temporal target.
    """

    valid_time: AxisPerspective | None = None
    transaction_time: AxisPerspective | None = None

    def ranked_perspectives(self) -> Iterator[AxisPerspective]:
        """The present per-axis perspectives in canonical axis rank."""
        if self.valid_time is not None:
            yield self.valid_time
        if self.transaction_time is not None:
            yield self.transaction_time

    @property
    def is_temporal(self) -> bool:
        """Whether the target declares any As-Of Axis."""
        return self.transaction_time is not None

    def is_latest_end(self, attribute: AttributeIdentity) -> bool:
        """Whether ``attribute`` is the end of an axis selected at Latest, which
        fixes that end to the open bound; an instant fixes no end."""
        return any(
            isinstance(perspective, LatestPerspective)
            and perspective.axis.end_attribute == attribute
            for perspective in self.ranked_perspectives()
        )
