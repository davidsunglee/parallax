"""An attempt's Ownership fixed to an explicit set of opened rows."""

from __future__ import annotations

from dataclasses import dataclass, field

from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work.plan import Derivation, Descent, OwnedEndpoint
from parallax.core.unit_work.planner import ObservedStateKey


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
        self, original: ObservedStateKey, start: object | None, until: object | None, /
    ) -> tuple[tuple[OwnedEndpoint, Descent], ...]:
        del start, until
        return tuple(
            (endpoint, descent)
            for endpoint, descent in self.descents.items()
            if descent.original == original
        )

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        return self.descents.get(endpoint)
