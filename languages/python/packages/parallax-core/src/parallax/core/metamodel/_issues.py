"""The shared Metamodel Issue value and its canonical ordering law (m-metamodel).

One immutable issue representation serves foundational resolution and every
semantic Rule Set. Every issue is fatal, so there is no severity and no central
code enum: a code is a stable kebab-case token prefixed with its owning
module's catalog stem. Message text is explanatory and participates in neither
equality nor ordering, so a reworded diagnostic can never reorder a report.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from parallax.core.metamodel._identities import (
    AttributeIdentity,
    EntityIdentity,
    IndexIdentity,
    RelationshipIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.metamodel._values import TemporalDimension

__all__ = [
    "METAMODEL_MODULE",
    "MODEL_ROOT",
    "AsOfAxisLocation",
    "AttributeLocation",
    "EntityLocation",
    "IndexLocation",
    "IssueCode",
    "MetamodelIssue",
    "ModelLocation",
    "ModelLocationKey",
    "ModelRoot",
    "RelationshipLocation",
    "ValueObjectAttributeLocation",
    "ValueObjectLocation",
    "canonical_issue_key",
    "canonical_location_key",
    "sort_issues",
]

METAMODEL_MODULE: Final[str] = "m-metamodel"
"""The catalog identity that owns the foundational resolver and every
``metamodel-*`` Issue Code."""

type IssueCode = str
"""A stable owner-prefixed kebab-case token."""


@dataclass(frozen=True, slots=True)
class ModelRoot:
    """The whole model, for an issue that belongs to no single position."""


MODEL_ROOT: Final[ModelRoot] = ModelRoot()


@dataclass(frozen=True, slots=True)
class EntityLocation:
    """One Entity."""

    entity: EntityIdentity


@dataclass(frozen=True, slots=True)
class AttributeLocation:
    """One Attribute."""

    attribute: AttributeIdentity


@dataclass(frozen=True, slots=True)
class RelationshipLocation:
    """One Relationship declaration."""

    relationship: RelationshipIdentity


@dataclass(frozen=True, slots=True)
class ValueObjectLocation:
    """One Value Object occurrence."""

    value_object: ValueObjectIdentity


@dataclass(frozen=True, slots=True)
class ValueObjectAttributeLocation:
    """One scalar Attribute of a Value Object occurrence."""

    value_object_attribute: ValueObjectAttributeIdentity


@dataclass(frozen=True, slots=True)
class AsOfAxisLocation:
    """One temporal dimension of one Entity."""

    entity: EntityIdentity
    dimension: TemporalDimension


@dataclass(frozen=True, slots=True)
class IndexLocation:
    """One Index."""

    index: IndexIdentity


type ModelLocation = (
    ModelRoot
    | EntityLocation
    | AttributeLocation
    | RelationshipLocation
    | ValueObjectLocation
    | ValueObjectAttributeLocation
    | AsOfAxisLocation
    | IndexLocation
)
"""The closed, semantic-only location union. It carries no descriptor path,
language class name, source span, or arbitrary property string; a frontend maps
a location to source coordinates separately."""

type ModelLocationKey = tuple[int, str, str, int, tuple[str, ...], str, int]
"""The comparable form of a location: a Model Root discriminator, the Entity's
canonical namespace/name key, the member rank, and the rank's own detail."""

_ENTITY_RANK: Final[int] = 0
_ATTRIBUTE_RANK: Final[int] = 1
_RELATIONSHIP_RANK: Final[int] = 2
_VALUE_OBJECT_RANK: Final[int] = 3
_VALUE_OBJECT_ATTRIBUTE_RANK: Final[int] = 4
_AS_OF_AXIS_RANK: Final[int] = 5
_INDEX_RANK: Final[int] = 6


def canonical_location_key(location: ModelLocation) -> ModelLocationKey:
    """The sort key that places ``location`` in canonical order.

    Model Root sorts before every other location. The rest group by canonical
    Entity Identity and then by the fixed member rank Entity, Attribute,
    Relationship, Value Object, Value Object Attribute, As-Of Axis, Index.
    Containment paths compare lexicographically and Valid Time precedes
    Transaction Time.
    """
    match location:
        case ModelRoot():
            return (0, "", "", _ENTITY_RANK, (), "", 0)
        case EntityLocation(entity):
            namespace, name = entity.sort_key
            return (1, namespace, name, _ENTITY_RANK, (), "", 0)
        case AttributeLocation(attribute):
            namespace, name = attribute.entity.sort_key
            return (1, namespace, name, _ATTRIBUTE_RANK, (), attribute.name, 0)
        case RelationshipLocation(relationship):
            namespace, name = relationship.source_entity.sort_key
            return (1, namespace, name, _RELATIONSHIP_RANK, (), relationship.name, 0)
        case ValueObjectLocation(value_object):
            namespace, name = value_object.entity.sort_key
            return (1, namespace, name, _VALUE_OBJECT_RANK, value_object.path, "", 0)
        case ValueObjectAttributeLocation(member):
            namespace, name = member.value_object.entity.sort_key
            return (
                1,
                namespace,
                name,
                _VALUE_OBJECT_ATTRIBUTE_RANK,
                member.value_object.path,
                member.name,
                0,
            )
        case AsOfAxisLocation(entity, dimension):
            namespace, name = entity.sort_key
            return (1, namespace, name, _AS_OF_AXIS_RANK, (), "", dimension.value)
        case IndexLocation(index):
            namespace, name = index.entity.sort_key
            return (1, namespace, name, _INDEX_RANK, (), index.name, 0)


@dataclass(frozen=True, slots=True)
class MetamodelIssue:
    """One fatal model defect, located in the model's own vocabulary.

    Equality and hashing are ``(code, location, related)``: two emitters that
    report the same defect at the same position with different wording produce
    one issue identity. ``related`` preserves the emitter's semantic order.
    """

    code: IssueCode
    location: ModelLocation
    related: tuple[ModelLocation, ...] = ()
    message: str = field(default="", compare=False)


def canonical_issue_key(
    issue: MetamodelIssue,
) -> tuple[ModelLocationKey, str, tuple[ModelLocationKey, ...]]:
    """The sort key that places ``issue`` in canonical order.

    Location first, then Issue Code, then the related locations in their
    unchanged emitted order. Frontend, rule, profile, message, and scheduling
    order never participate.
    """
    return (
        canonical_location_key(issue.location),
        issue.code,
        tuple(canonical_location_key(related) for related in issue.related),
    )


def sort_issues(issues: Iterable[MetamodelIssue]) -> tuple[MetamodelIssue, ...]:
    """``issues`` in canonical order, independent of emission order."""
    return tuple(sorted(issues, key=canonical_issue_key))
