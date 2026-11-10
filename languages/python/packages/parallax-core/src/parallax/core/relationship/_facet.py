from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard

from parallax.core.metamodel import (
    Cardinality,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipOrder,
)
from parallax.core.metamodel._accepted import FacetKey, facet_of

__all__ = [
    "FACET_KEY",
    "RELATIONSHIP_MODULE",
    "EntityRelationships",
    "RelationshipFacet",
    "RelationshipMetadata",
    "inverted",
    "relationship_facet",
    "relationship_facet_of",
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

    def is_back_reference_from(self, arrival: RelationshipMetadata | None) -> bool:
        """Whether this direction is a to-one peer of ``arrival``, the two navigable
        directions of ONE association, each naming the other as its reverse.

        This is what proves a hop lands on the very object the path arrived from
        rather than merely on that object's family: the two directions share one
        join, so the arrived-at row's correlation attribute holds the arrival hop's
        own source key. Both reverse names are checked, and the target Entity with
        them, so two unrelated associations sharing a local relationship name cannot
        pair. An absent arrival is a hop leaving the root, which nothing preceded.
        """
        return (
            arrival is not None
            and self.cardinality is not Cardinality.ONE_TO_MANY
            and arrival.reverse == self.identity.name
            and self.reverse == arrival.identity.name
            and self.join.target.entity == arrival.identity.source_entity
        )


@dataclass(frozen=True, slots=True)
class EntityRelationships:
    """One Entity's compiled relationship record.

    ``rank`` is the Entity's referential rank: every Entity whose foreign key it
    holds ranks lower, so ascending rank is a safe insert order and descending
    rank a safe delete order. Otherwise independent Entities, and the Entities
    of a referential cycle, rank in canonical Entity order.
    """

    directions: tuple[RelationshipMetadata, ...]
    rank: int


class RelationshipFacet(Protocol):
    """Every accepted relationship direction, precomputed once per formation.

    ``relationship`` is total, nonthrowing, and expected amortized ``O(1)``.
    ``relationships`` distinguishes the two absences a behavioral consumer must
    tell apart: an Entity the model does not contain answers ``None``, while an
    Entity that declares no relationship answers an empty sequence. A known
    Entity's sequence preserves its local declaration order. There is no global
    enumeration and no separate reverse-pair lookup — a direction is reached by
    its own Identity or through its Entity. ``referential_rank`` answers
    :attr:`EntityRelationships.rank`, or ``None`` for an unknown Entity.
    """

    def relationship(self, identity: RelationshipIdentity) -> RelationshipMetadata | None: ...
    def relationships(self, entity: EntityIdentity) -> Sequence[RelationshipMetadata] | None: ...
    def referential_rank(self, entity: EntityIdentity) -> int | None: ...


class _RelationshipFacet:
    """The compiled facet over read-only indices nothing else holds."""

    __slots__ = ("_by_entity", "_by_identity")

    _by_entity: Mapping[EntityIdentity, EntityRelationships]
    _by_identity: Mapping[RelationshipIdentity, RelationshipMetadata]

    def __init__(self, by_entity: Mapping[EntityIdentity, EntityRelationships]) -> None:
        self._by_entity = MappingProxyType(dict(by_entity))
        self._by_identity = MappingProxyType(
            {
                value.identity: value
                for record in self._by_entity.values()
                for value in record.directions
            }
        )

    def relationship(self, identity: RelationshipIdentity) -> RelationshipMetadata | None:
        return self._by_identity.get(identity)

    def relationships(self, entity: EntityIdentity) -> Sequence[RelationshipMetadata] | None:
        record = self._by_entity.get(entity)
        return None if record is None else record.directions

    def referential_rank(self, entity: EntityIdentity) -> int | None:
        record = self._by_entity.get(entity)
        return None if record is None else record.rank


def relationship_facet(
    by_entity: Mapping[EntityIdentity, EntityRelationships],
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


def relationship_facet_of(model: Metamodel) -> RelationshipFacet:
    """``model``'s Relationship Facet, the typed retrieval every consumer uses.

    Total for an accepted Metamodel, which by construction carries the complete
    facet set.
    """
    return facet_of(model, FACET_KEY)
