"""An attempt's Ownership fixed to an explicit set of opened rows."""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work.plan import OwnedEndpoint


@dataclass(frozen=True)
class OpenedRows:
    """An attempt that opened exactly ``endpoints``."""

    endpoints: frozenset[OwnedEndpoint]

    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self.endpoints

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        return any(endpoint.entity == entity for endpoint in self.endpoints)
