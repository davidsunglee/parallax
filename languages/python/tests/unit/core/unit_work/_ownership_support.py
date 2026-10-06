"""An attempt's Ownership fixed to an explicit set of opened rows."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObservedStateKey
from parallax.core.write_plan.plan import Derivation, Descent, OwnedEndpoint


@dataclass(frozen=True)
class OpenedRows:
    """An attempt that opened exactly ``endpoints``, ``inserted`` among them
    as coverage an admitted insertion opened, and whose running flush already
    transformed the originals ``proofs`` names, deriving the rows
    ``descents`` names."""

    endpoints: frozenset[OwnedEndpoint]
    inserted: frozenset[OwnedEndpoint] = frozenset()
    proofs: dict[ObservedStateKey, Derivation] = field(
        default_factory=dict[ObservedStateKey, Derivation]
    )
    descents: dict[OwnedEndpoint, Descent] = field(default_factory=dict[OwnedEndpoint, Descent])

    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self.endpoints

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        return any(endpoint.entity == entity for endpoint in self.endpoints)

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self.inserted

    def proven(self, original: ObservedStateKey, /) -> Derivation | None:
        return self.proofs.get(original)

    def descendants(
        self, original: ObservedStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterator[tuple[OwnedEndpoint, Descent]]:
        for endpoint, descent in self.descents.items():
            coverage = descent.valid_time_coverage
            if descent.original == original and (
                valid_time_window is None
                or coverage is None
                or coverage.overlaps(valid_time_window)
            ):
                yield endpoint, descent

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        return self.descents.get(endpoint)
