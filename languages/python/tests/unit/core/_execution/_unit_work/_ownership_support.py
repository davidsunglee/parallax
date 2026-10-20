"""An attempt's Temporal Write Ownership fixed to an explicit set of opened rows."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass, field

from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectStateKey
from parallax.core.write_plan.plan import Derivation, Descent, OwnedEndpoint

_AXISLESS = dt.datetime.min.replace(tzinfo=dt.UTC)


@dataclass(frozen=True)
class OpenedRows:
    """An attempt that opened exactly ``endpoints``, ``inserted`` among them
    as coverage an admitted insertion contributed — only its
    ``insertion_parts`` of each, where they are given, else the whole row —
    and whose running flush already transformed the originals ``proofs``
    names, deriving the rows ``descents`` names."""

    endpoints: frozenset[OwnedEndpoint]
    inserted: frozenset[OwnedEndpoint] = frozenset()
    proofs: dict[ObjectStateKey, Derivation] = field(
        default_factory=dict[ObjectStateKey, Derivation]
    )
    descents: dict[OwnedEndpoint, Descent] = field(default_factory=dict[OwnedEndpoint, Descent])
    insertion_parts: tuple[TimeInterval, ...] | None = None

    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self.endpoints

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self.inserted

    def insertion_coverage(
        self, endpoint: OwnedEndpoint, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        if endpoint not in self.inserted:
            return ()
        parts = self.insertion_parts
        if parts is None or valid_time_coverage is None:
            return (valid_time_coverage,)
        return tuple(
            shared
            for shared in (part.intersection(valid_time_coverage) for part in parts)
            if shared is not None
        )

    def proven(self, original: ObjectStateKey, /) -> Derivation | None:
        return self.proofs.get(original)

    def descendants(
        self, original: ObjectStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterator[tuple[OwnedEndpoint, Descent]]:
        reached = [
            (_AXISLESS if contributed is None else contributed.start, endpoint, descent)
            for endpoint, descent in self.descents.items()
            for contributor, contributed in descent.contributions
            if contributor == original
            and (
                valid_time_window is None
                or (contributed is not None and contributed.overlaps(valid_time_window))
            )
        ]
        reached.sort(key=lambda part: part[0])
        for _start, endpoint, descent in reached:
            yield endpoint, descent

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        return self.descents.get(endpoint)
