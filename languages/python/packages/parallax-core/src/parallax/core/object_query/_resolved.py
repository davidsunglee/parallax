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
    TemporalDimension,
)
from parallax.core.predicate._resolved import ResolvedPredicate


@dataclass(frozen=True, slots=True)
class ResolvedLatestSelection:
    axis: AsOfAxisMetadata


@dataclass(frozen=True, slots=True)
class ResolvedHistorySelection:
    axis: AsOfAxisMetadata


@dataclass(frozen=True, slots=True)
class ResolvedAsOfSelection:
    axis: AsOfAxisMetadata
    coordinate: ManagedValue


@dataclass(frozen=True, slots=True)
class ResolvedRangeSelection:
    axis: AsOfAxisMetadata
    start: ManagedValue
    end: ManagedValue


type ResolvedTemporalSelection = (
    ResolvedLatestSelection
    | ResolvedHistorySelection
    | ResolvedAsOfSelection
    | ResolvedRangeSelection
)


def latest_temporal_selections(
    root: EntityMetadata,
) -> tuple[ResolvedTemporalSelection, ...]:
    """Produce resolved Latest selections for an internal mutation read."""
    return tuple(ResolvedLatestSelection(axis) for axis in root.declared_as_of_axes)


def selections_at_valid_time(
    root: EntityMetadata, instant: ManagedValue
) -> tuple[ResolvedTemporalSelection, ...]:
    """Produce resolved selections for an internal mutation read as of
    ``instant`` on Valid Time and at Latest on every other axis."""
    return tuple(
        ResolvedAsOfSelection(axis, instant)
        if axis.dimension is TemporalDimension.VALID_TIME
        else ResolvedLatestSelection(axis)
        for axis in root.declared_as_of_axes
    )


@dataclass(frozen=True, slots=True)
class ResolvedOrderTerm:
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
class ResolvedSeek:
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

    seek: ResolvedSeek | None = None


@dataclass(frozen=True, slots=True)
class ResolvedIncludeSegment:
    relationship: RelationshipIdentity
    target: EntityMetadata
    position: tuple[EntityIdentity, ...]
    authored_narrow: bool


@dataclass(frozen=True, slots=True)
class ResolvedIncludePath:
    source_position: tuple[EntityIdentity, ...]
    segments: tuple[ResolvedIncludeSegment, ...]


@dataclass(frozen=True, slots=True)
class ResolvedObjectQuery:
    """The complete resolved meaning of one accepted query."""

    root: EntityMetadata
    predicate: ResolvedPredicate
    temporal: tuple[ResolvedTemporalSelection, ...]
    order_by: tuple[ResolvedOrderTerm, ...]
    includes: tuple[ResolvedIncludePath, ...]
    narrow_to: tuple[EntityMetadata, ...] | None
    limit: int | None
    paging: Paging | None = None


def resolved_order_term(
    member: AttributeMetadata,
    *,
    direction: Literal["asc", "desc"],
    nulls: Literal["first", "last"],
) -> ResolvedOrderTerm:
    """Produce a generated resolved order term inside the owner module."""
    return ResolvedOrderTerm(member, direction, nulls)


def derive_page(
    base: ResolvedObjectQuery,
    *,
    paging: Paging,
    order_by: tuple[ResolvedOrderTerm, ...],
    limit: int,
) -> ResolvedObjectQuery:
    """Derive one page without re-resolving any accepted clause.

    The seek rides on ``paging`` rather than on the predicate: a coordinate is a
    physical carrier the database evaluated, while a resolved predicate holds
    only managed operands. A page's own predicate is therefore the caller's,
    untouched.
    """
    return replace(base, order_by=order_by, limit=limit, paging=paging)
