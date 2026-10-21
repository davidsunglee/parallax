"""An attempt's Temporal Write Ownership fixed to an explicit set of opened rows."""

from __future__ import annotations

import datetime as dt
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field

from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey
from parallax.core.write_plan.observe import PredecessorRow
from parallax.core.write_plan.plan import TemporalRowCoordinates


@dataclass(frozen=True)
class OpenedRows:
    """An attempt that opened exactly the rows at ``coordinates``, ``inserted``
    among them as coverage an admitted insertion contributed — only its
    ``insertion_parts`` of each, where they are given, else the whole row —
    whose completed writes left the ``demanded`` predecessor states to its
    sources, changed each observation ``continuing`` names into the surviving
    parts it lists, and hold the ``current`` rows of each object for them."""

    coordinates: frozenset[TemporalRowCoordinates]
    inserted: frozenset[TemporalRowCoordinates] = frozenset()
    insertion_parts: tuple[TimeInterval, ...] | None = None
    demanded_states: frozenset[ObjectStateKey] = frozenset()
    continuing: dict[Hashable, tuple[TimeInterval | None, ...]] = field(
        default_factory=dict[Hashable, tuple[TimeInterval | None, ...]]
    )
    current: dict[ObjectKey, tuple[PredecessorRow, ...]] = field(
        default_factory=dict[ObjectKey, tuple[PredecessorRow, ...]]
    )

    def owns(self, coordinates: TemporalRowCoordinates, /) -> bool:
        return coordinates in self.coordinates

    def continues_insertion(self, coordinates: TemporalRowCoordinates, /) -> bool:
        return coordinates in self.inserted

    def insertion_coverage(
        self, coordinates: TemporalRowCoordinates, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        if coordinates not in self.inserted:
            return ()
        parts = self.insertion_parts
        if parts is None or valid_time_coverage is None:
            return (valid_time_coverage,)
        return tuple(
            shared
            for shared in (part.intersection(valid_time_coverage) for part in parts)
            if shared is not None
        )

    def demanded(
        self, predecessor: ObjectStateKey, coordinates: TemporalRowCoordinates | None, /
    ) -> bool:
        del coordinates
        return predecessor in self.demanded_states

    def continues(self, observation: Hashable, pin: dt.datetime | None, /) -> bool | None:
        parts = self.continuing.get(observation)
        if parts is None:
            return None
        if pin is None:
            return bool(parts)
        return any(part is None or part.contains(pin) for part in parts)

    def current_rows(
        self, target: ObjectKey, valid_time_window: TimeInterval | None, /
    ) -> Sequence[PredecessorRow]:
        del valid_time_window
        return self.current.get(target, ())
