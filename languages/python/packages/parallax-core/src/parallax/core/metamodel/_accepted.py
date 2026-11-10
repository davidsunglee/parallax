from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeGuard, cast, final

from parallax.core.metamodel._identities import EntityIdentity
from parallax.core.metamodel._states import CompiledEntity, CompiledMetadata

__all__ = ["FacetKey", "Metamodel", "accept_metamodel", "facet_of"]


@dataclass(frozen=True, slots=True)
class FacetKey[T]:
    """The typed key one compiling module's facet is installed and retrieved under.

    Identity is the owning module's catalog identity alone, so a module owns
    exactly one key and two keys naming one owner are the same key. The type
    parameter carries the facet's type through :func:`facet_of` and is erased at
    run time, so ``accepts`` is its run-time counterpart: the owner's own
    decision procedure for "is this value my facet?", which the formation seam
    calls on whatever a compiler returned before installing it. Only the owner
    can answer that — a facet may be a Protocol, and no generic check can see
    through the erased parameter — so supplying ``accepts`` is part of declaring
    a key, and a value it rejects is a compiler contract failure. ``accepts``
    never participates in equality or hashing, so an equal key may carry any
    check at all; the seam therefore calls the check on the key its own
    authoritative declaration holds, never one a contributor handed it.
    """

    owner: str
    accepts: Callable[[object], TypeGuard[T]] = field(compare=False)


@final
@dataclass(frozen=True, slots=True)
class Metamodel:
    """The accepted model: Compiled Metadata plus its complete facet set.

    It exists only after every formation rule succeeded and every compiler ran,
    and it is not a subtype of either formation input. Construct one only through
    :func:`accept_metamodel`. Its facets are owner machinery: each owning module
    reads its own through a typed ``<owner>_facet_of(model)`` accessor.
    """

    _metadata: CompiledMetadata
    _facets: Mapping[FacetKey[Any], object]

    @property
    def entities(self) -> Sequence[CompiledEntity]:
        """Every accepted Entity, in canonical Entity Identity order."""
        return self._metadata.entities

    def entity(self, identity: EntityIdentity) -> CompiledEntity | None:
        """The accepted Entity ``identity`` names, or ``None``."""
        return self._metadata.entity(identity)


def accept_metamodel(
    metadata: CompiledMetadata, facets: Mapping[FacetKey[Any], object]
) -> Metamodel:
    """Combine the exact Compiled Metadata graph with its complete facet set.

    The accepted Metamodel delegates lookup to that graph rather than copying or
    re-indexing it. The facet mapping is snapshotted into a read-only view, so a
    caller that keeps its own mapping cannot alter an accepted model's facets.
    """
    return Metamodel(metadata, MappingProxyType(dict(facets)))


def facet_of[T](model: Metamodel, key: FacetKey[T]) -> T:
    """``model``'s facet installed under ``key``.

    Total for an accepted Formation Profile, which the formation runner
    establishes before any compiler runs; a key the model does not carry is a
    ``KeyError``. Only an owning module's typed accessor calls this.
    """
    facets = model._facets  # pyright: ignore[reportPrivateUsage] - the accepted model's own facet retrieval
    return cast(T, facets[key])
