"""The symmetric Relationship Facet and its typed retrieval (m-relationship).

A relationship is authored once, from one side, but navigated from both. This
module owns the resulting directional value and the immutable per-formation view
that serves it: one value per accepted declaration, reachable by exact Identity
in expected amortized constant time and enumerable per Entity in local
declaration order. The facet is the only place a reverse direction's join and
cardinality exist; accepted Entity Metadata keeps its declarations exactly as
authored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard

from parallax.core.metamodel import (
    Cardinality,
    EntityIdentity,
    FacetKey,
    Metamodel,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipOrder,
)

__all__ = [
    "FACET_KEY",
    "RELATIONSHIP_MODULE",
    "RelationshipFacet",
    "RelationshipMetadata",
    "inverted",
    "is_relationship_facet",
    "relationship_facet",
    "view",
]

RELATIONSHIP_MODULE: Final[str] = "m-relationship"
"""The catalog identity that owns relationship formation, its Issue Codes, and
the Relationship Facet."""

_INVERSE: Final[Mapping[Cardinality, Cardinality]] = {
    Cardinality.ONE_TO_ONE: Cardinality.ONE_TO_ONE,
    Cardinality.MANY_TO_ONE: Cardinality.ONE_TO_MANY,
    Cardinality.ONE_TO_MANY: Cardinality.MANY_TO_ONE,
}


def inverted(cardinality: Cardinality) -> Cardinality:
    """The cardinality of the direction opposite ``cardinality``.

    Inversion exchanges the two sides, so the opposite direction's target
    Multiplicity is this direction's source Multiplicity and vice versa.
    """
    return _INVERSE[cardinality]


@dataclass(frozen=True, slots=True)
class RelationshipMetadata:
    """One navigable direction of one association.

    The target is ``join.target.entity`` and appears nowhere else: there is no
    second target member, foreign-key hint, or many-to-many value. ``reverse``
    names the peer direction's local relationship name on the far Entity when the
    association is bidirectional, and is absent for a one-way one; it is a name
    rather than a parallel pair map, so nothing indexes directions twice.
    ``order_by`` is the direction's own ordering over target-local Attributes. An
    empty reverse name raises :class:`ValueError`.
    """

    identity: RelationshipIdentity
    cardinality: Cardinality
    join: RelationshipJoin
    reverse: str | None = None
    dependent: bool = False
    order_by: tuple[RelationshipOrder, ...] = ()

    def __post_init__(self) -> None:
        if self.reverse is not None and not self.reverse:
            raise ValueError("a reverse relationship name is either absent or nonempty")


class RelationshipFacet(Protocol):
    """Every accepted relationship direction, precomputed once per formation.

    ``relationship`` is total, nonthrowing, and expected amortized ``O(1)``.
    ``relationships`` distinguishes the two absences a behavioral consumer must
    tell apart: an Entity the model does not contain answers ``None``, while an
    Entity that declares no relationship answers an empty sequence. A known
    Entity's sequence preserves its local declaration order. There is no global
    enumeration and no separate reverse-pair lookup — a direction is reached by
    its own Identity or through its Entity.
    """

    def relationship(self, identity: RelationshipIdentity) -> RelationshipMetadata | None: ...
    def relationships(self, entity: EntityIdentity) -> Sequence[RelationshipMetadata] | None: ...


class _RelationshipFacet:
    """The compiled facet over read-only indexes nothing else holds."""

    __slots__ = ("_by_entity", "_by_identity")

    _by_entity: Mapping[EntityIdentity, tuple[RelationshipMetadata, ...]]
    _by_identity: Mapping[RelationshipIdentity, RelationshipMetadata]

    def __init__(
        self, by_entity: Mapping[EntityIdentity, tuple[RelationshipMetadata, ...]]
    ) -> None:
        self._by_entity = MappingProxyType(dict(by_entity))
        self._by_identity = MappingProxyType(
            {
                value.identity: value
                for directions in self._by_entity.values()
                for value in directions
            }
        )

    def relationship(self, identity: RelationshipIdentity) -> RelationshipMetadata | None:
        return self._by_identity.get(identity)

    def relationships(self, entity: EntityIdentity) -> Sequence[RelationshipMetadata] | None:
        return self._by_entity.get(entity)


def relationship_facet(
    by_entity: Mapping[EntityIdentity, tuple[RelationshipMetadata, ...]],
) -> RelationshipFacet:
    """The facet serving ``by_entity``, which names every Entity of one model.

    An Entity missing from ``by_entity`` is unknown to the facet, so the compiler
    supplies an entry for every accepted Entity — including the ones that declare
    no relationship at all.
    """
    return _RelationshipFacet(by_entity)


def is_relationship_facet(value: object) -> TypeGuard[RelationshipFacet]:
    """Whether ``value`` is a Relationship Facet this module compiled.

    ``m-relationship`` owns the sole compiler for its facet and this is its only
    output type, so provenance decides rather than the surface a value presents.

    Exists for the formation seam that receives a compiler's result and must
    classify a wrong-typed one as a contract failure rather than install it.
    """
    return isinstance(value, _RelationshipFacet)


FACET_KEY: Final[FacetKey[RelationshipFacet]] = FacetKey(RELATIONSHIP_MODULE, is_relationship_facet)
"""The typed key this module's facet is installed and retrieved under."""


def view(model: Metamodel) -> RelationshipFacet:
    """``model``'s Relationship Facet.

    The typed retrieval every behavioral consumer uses, so generic facet lookup
    stays an internal formation seam. Total for an accepted Metamodel, which by
    construction carries the complete facet set.
    """
    return model.facet(FACET_KEY)
