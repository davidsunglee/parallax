"""The identity-paired view of two endpoints every later stage reads.

Declarations are paired exactly once, by structured identity and never by
guessing a rename, so the differ, the classifier, and the impact analyzers never
re-pair. The value is internal to this scope and dies with the ``evolve`` call
that built it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core.inheritance import InheritanceEntityView
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.evolution.model_evolution._values import Absent

__all__ = ["EntityFacts", "Matching", "Paired", "match"]


@dataclass(frozen=True, slots=True)
class EntityFacts:
    """One Entity's accepted declaration beside its family-effective view.

    Both answer at one key because both are needed at once: a field delta
    reports the accepted declaration, while classification and the Behavioral
    Impacts compare the effective ancestry, physical facts, and Persistence Mode
    the family's root fixes.
    """

    declaration: EntityMetadata
    family: InheritanceEntityView


@dataclass(frozen=True, slots=True)
class Paired[I, D]:
    """One declaration kind's declarations, partitioned by which endpoints hold them."""

    added: Mapping[I, D]
    removed: Mapping[I, D]
    surviving: Mapping[I, tuple[D, D]]


@dataclass(frozen=True, slots=True)
class Matching:
    """Both accepted endpoints and their identity-paired declarations.

    ``earlier`` is ``None`` only for the fresh-provisioning evolution, where
    every later declaration is an addition.
    """

    earlier: Metamodel | None
    later: Metamodel
    entities: Paired[EntityIdentity, EntityFacts]
    attributes: Paired[AttributeIdentity, AttributeMetadata]


def pair[I, D](earlier: Sequence[tuple[I, D]], later: Sequence[tuple[I, D]]) -> Paired[I, D]:
    """Partition two identity-keyed declaration sequences into one :class:`Paired`."""
    earlier_by_identity = dict(earlier)
    later_by_identity = dict(later)
    return Paired(
        added=MappingProxyType(
            {
                identity: declaration
                for identity, declaration in later_by_identity.items()
                if identity not in earlier_by_identity
            }
        ),
        removed=MappingProxyType(
            {
                identity: declaration
                for identity, declaration in earlier_by_identity.items()
                if identity not in later_by_identity
            }
        ),
        surviving=MappingProxyType(
            {
                identity: (earlier_by_identity[identity], declaration)
                for identity, declaration in later_by_identity.items()
                if identity in earlier_by_identity
            }
        ),
    )


def match(earlier: Metamodel | Absent, later: Metamodel) -> Matching:
    """Pair both endpoints' declarations by structured identity."""
    earlier_model = None if isinstance(earlier, Absent) else earlier
    return Matching(
        earlier=earlier_model,
        later=later,
        entities=pair(() if earlier_model is None else _entities(earlier_model), _entities(later)),
        attributes=pair(
            () if earlier_model is None else _attributes(earlier_model), _attributes(later)
        ),
    )


def _entities(model: Metamodel) -> tuple[tuple[EntityIdentity, EntityFacts], ...]:
    facet = inheritance_view(model)
    paired: list[tuple[EntityIdentity, EntityFacts]] = []
    for entity in model.entities:
        family = facet.entity(entity.identity)
        if family is None:  # pragma: no cover - the facet covers every accepted Entity
            continue
        paired.append((entity.identity, EntityFacts(entity, family)))
    return tuple(paired)


def _attributes(model: Metamodel) -> tuple[tuple[AttributeIdentity, AttributeMetadata], ...]:
    """Every declared scalar Attribute, keyed by its own Identity.

    Declared rather than applicable: an inherited member belongs to the ancestor
    that introduced it, so pairing the applicable sequences would describe one
    declaration once per descendant.
    """
    return tuple(
        (attribute.identity, attribute)
        for entity in model.entities
        for attribute in entity.declared_attributes
    )
