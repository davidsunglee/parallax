"""Immutable fully resolved Object Query products."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from parallax.core.base import ManagedValue, inert_scalar
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    RelationshipIdentity,
)
from parallax.core.object_query._nodes import ObjectQueryNode, OrderKey
from parallax.core.predicate._validated import ValidatedPredicate


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
class ContinuationTerm:
    """One member of the Continuation Order, as the seek reads it.

    Everything a lexicographic branch needs of a term and nothing physical:
    which member it orders by, in which direction, where it asks NULLs to be
    placed, and whether the member can hold one at all. Where the database
    actually placed them, and what expression it ordered by, are m-sql's.
    """

    identity: AttributeIdentity
    direction: Literal["asc", "desc"]
    nulls: Literal["first", "last"]
    nullable: bool


@dataclass(frozen=True, slots=True)
class ContinuationCoordinate:
    """Where one root stood in the Continuation Order, as the database evaluated it.

    ``carriers`` is one opaque value per term, positionally, exactly as that
    term's ``ORDER BY`` expression produced it and normalized once at capture.
    Nothing outside m-sql interprets a carrier: this value is constructed by the
    module that chose the expressions, carried opaquely by continuation, and
    handed back to be rebound.

    Equality is therefore the coordinate's own rule rather than its holder's — a
    caller comparing two positions in a delivery asks the value, and never the
    carriers inside it.
    """

    carriers: tuple[object, ...]

    def snapshot(self) -> tuple[object, ...]:
        """An inert copy for diagnostics, with no way back to a coordinate.

        A carrier may arrive as a buffer its provider still owns, so byte-likes
        are copied; every other scalar is already immutable. What comes back is
        an ordinary tuple, which nothing turns into pagination authority again.
        """
        return tuple(inert_scalar(carrier) for carrier in self.carriers)


@dataclass(frozen=True, slots=True)
class ValidatedSeek:
    """The roots a page admits: everything strictly after ``coordinate``.

    ``terms`` is the WHOLE Continuation Order — the authored Sort Keys, the
    family-declared primary key, and a milestone scan's As-Of Axis starts alike
    — positionally aligned with ``coordinate``'s carriers. Continuation composes
    this; m-sql expands it into the lexicographic branch tree, which cannot be
    settled without knowing where the dialect placed a NULL.
    """

    terms: tuple[ContinuationTerm, ...]
    coordinate: ContinuationCoordinate


@dataclass(frozen=True, slots=True)
class Paging:
    """That a read is one page of a streamed delivery, and where that page starts.

    Present at all means the read captures a coordinate per ordering term; a
    ``seek`` additionally means it skips everything already delivered. One field
    rather than two booleans, because capturing nothing while seeking from
    somewhere is not a state that means anything: a first page is ``Paging()``
    and an eager read carries no ``Paging`` at all.
    """

    seek: ValidatedSeek | None = None


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
    paging: Paging | None = None


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
    paging: Paging,
    order_by: tuple[ValidatedOrderTerm, ...],
    limit: int,
) -> ValidatedObjectQuery:
    """Derive one page without re-resolving any accepted clause.

    The seek rides on ``paging`` rather than on the predicate: a coordinate is a
    physical carrier the database evaluated, while an authored predicate admits
    only managed operands. A page's own predicate is therefore the caller's,
    untouched.
    """
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
        authored=replace(base.authored, order_by=authored_order, limit=limit),
        order_by=order_by,
        limit=limit,
        paging=paging,
    )
