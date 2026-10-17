from __future__ import annotations

import datetime as _dt
from collections.abc import Iterator
from dataclasses import dataclass

from parallax.core.metamodel import AsOfAxisMetadata, AttributeIdentity, TemporalDimension


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
    perspective with neither field is that of a non-temporal target. A
    perspective in the other dimension's field, or Valid Time without
    Transaction Time, raises :class:`ValueError`.
    """

    valid_time: AxisPerspective | None = None
    transaction_time: AxisPerspective | None = None

    def __post_init__(self) -> None:
        if (
            self.valid_time is not None
            and self.valid_time.axis.dimension is not TemporalDimension.VALID_TIME
        ):
            raise ValueError("a Valid-Time perspective is over the Valid-Time axis")
        if (
            self.transaction_time is not None
            and self.transaction_time.axis.dimension is not TemporalDimension.TRANSACTION_TIME
        ):
            raise ValueError("a Transaction-Time perspective is over the Transaction-Time axis")
        if self.valid_time is not None and self.transaction_time is None:
            raise ValueError("a Valid-Time perspective requires a Transaction-Time perspective")

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
