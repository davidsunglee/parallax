"""Immutable fully resolved Object Query products."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from parallax.core.base import ManagedValue
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    RelationshipIdentity,
)
from parallax.core.object_query._nodes import ObjectQueryNode, OrderKey
from parallax.core.predicate._validated import ValidatedPredicate, conjunction


@dataclass(frozen=True, slots=True)
class ValidatedLatestSelection:
    axis: AsOfAxisMetadata


@dataclass(frozen=True, slots=True)
class ValidatedHistorySelection:
    axis: AsOfAxisMetadata


@dataclass(frozen=True, slots=True)
class ValidatedAsOfSelection:
    axis: AsOfAxisMetadata
    coordinate: ManagedValue


@dataclass(frozen=True, slots=True)
class ValidatedRangeSelection:
    axis: AsOfAxisMetadata
    start: ManagedValue
    end: ManagedValue


type ValidatedTemporalSelection = (
    ValidatedLatestSelection
    | ValidatedHistorySelection
    | ValidatedAsOfSelection
    | ValidatedRangeSelection
)


def latest_temporal_selections(
    root: EntityMetadata,
) -> tuple[ValidatedTemporalSelection, ...]:
    """Produce resolved Latest selections for an internal mutation read."""
    return tuple(ValidatedLatestSelection(axis) for axis in root.declared_as_of_axes)


@dataclass(frozen=True, slots=True)
class ValidatedOrderTerm:
    member: AttributeMetadata
    direction: Literal["asc", "desc"]
    nulls: Literal["first", "last"]


@dataclass(frozen=True, slots=True)
class ValidatedIncludeSegment:
    relationship: RelationshipIdentity
    target: EntityMetadata
    position: tuple[EntityIdentity, ...]
    authored_narrow: bool


@dataclass(frozen=True, slots=True)
class ValidatedIncludePath:
    source_position: tuple[EntityIdentity, ...]
    segments: tuple[ValidatedIncludeSegment, ...]


@dataclass(frozen=True, slots=True)
class ValidatedObjectQuery:
    """The complete resolved meaning of one accepted authored query."""

    authored: ObjectQueryNode
    root: EntityMetadata
    predicate: ValidatedPredicate
    temporal: tuple[ValidatedTemporalSelection, ...]
    order_by: tuple[ValidatedOrderTerm, ...]
    includes: tuple[ValidatedIncludePath, ...]
    narrow_to: tuple[EntityMetadata, ...] | None
    limit: int | None


def resolved_order_term(
    member: AttributeMetadata,
    *,
    direction: Literal["asc", "desc"],
    nulls: Literal["first", "last"],
) -> ValidatedOrderTerm:
    """Produce a generated resolved order term inside the owner module."""
    return ValidatedOrderTerm(member, direction, nulls)


def derive_page(
    base: ValidatedObjectQuery,
    *,
    seek: ValidatedPredicate | None,
    order_by: tuple[ValidatedOrderTerm, ...],
    limit: int,
) -> ValidatedObjectQuery:
    """Derive one page without re-resolving any accepted clause."""
    predicate = base.predicate if seek is None else conjunction(base.predicate, seek)
    authored_order = tuple(
        base.authored.order_by[index]
        if index < len(base.order_by) and term == base.order_by[index]
        else OrderKey(
            attr=f"{term.member.identity.entity.canonical}.{term.member.identity.name}",
            direction=term.direction,
            nulls=None,
        )
        for index, term in enumerate(order_by)
    )
    return replace(
        base,
        authored=replace(
            base.authored, predicate=predicate.authored, order_by=authored_order, limit=limit
        ),
        predicate=predicate,
        order_by=order_by,
        limit=limit,
    )
