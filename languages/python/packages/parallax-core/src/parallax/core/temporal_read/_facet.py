"""The Temporal Facet and its typed retrieval (m-temporal-read).

Temporality is a whole-family coordinate system its root declares, so "which
axes apply here?" is a question no single position answers on its own. This
module owns the answer as one immutable per-formation view, precomputed once so
behavioral modules never resolve a family root to read an axis again.

The shape algebra is closed and each variant carries exactly the axes it
declares, which is what makes the unsupported Valid-Time-Only formation
unrepresentable: no variant declares Valid Time without Transaction Time. Every
axis a view returns is the declaring root's accepted value by reference, so its
Attribute Identities still name the root.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard

from parallax.core.metamodel import (
    AsOfAxisMetadata,
    EntityIdentity,
    FacetKey,
    Metamodel,
    TemporalDimension,
)

__all__ = [
    "FACET_KEY",
    "NON_TEMPORAL",
    "TEMPORAL_READ_MODULE",
    "Bitemporal",
    "NonTemporal",
    "TemporalFacet",
    "TemporalShape",
    "TransactionTimeOnly",
    "is_temporal_facet",
    "temporal_facet",
    "view",
]

TEMPORAL_READ_MODULE: Final[str] = "m-temporal-read"
"""The catalog identity that owns as-of reads and the Temporal Facet."""


@dataclass(frozen=True, slots=True)
class NonTemporal:
    """The family declares no As-Of Axis; its rows are not milestones."""


# The shared instance of the nullary variant above. Variants are frozen value
# objects, so this is an allocation convenience rather than an identity: a fresh
# ``NonTemporal()`` equals it and matches the same patterns.
NON_TEMPORAL: Final[NonTemporal] = NonTemporal()


@dataclass(frozen=True, slots=True)
class TransactionTimeOnly:
    """The family declares Transaction Time alone — the audit-only shape.

    A wrongly dimensioned axis raises :class:`ValueError`, so the variant cannot
    stand in for a shape it does not describe.
    """

    transaction_time: AsOfAxisMetadata

    def __post_init__(self) -> None:
        if self.transaction_time.dimension is not TemporalDimension.TRANSACTION_TIME:
            raise ValueError("a Transaction-Time-Only shape carries the Transaction-Time axis")


@dataclass(frozen=True, slots=True)
class Bitemporal:
    """The family declares Valid Time and Transaction Time.

    Members are ordered as the canonical nesting is — Valid Time outside
    Transaction Time. A wrongly dimensioned axis raises :class:`ValueError`.
    """

    valid_time: AsOfAxisMetadata
    transaction_time: AsOfAxisMetadata

    def __post_init__(self) -> None:
        if self.valid_time.dimension is not TemporalDimension.VALID_TIME:
            raise ValueError("a Bitemporal shape's first axis is the Valid-Time axis")
        if self.transaction_time.dimension is not TemporalDimension.TRANSACTION_TIME:
            raise ValueError("a Bitemporal shape's second axis is the Transaction-Time axis")


type TemporalShape = NonTemporal | TransactionTimeOnly | Bitemporal
"""The closed algebra of supported temporal Entity shapes. Valid-Time-Only is
unsupported and has no variant, so it cannot be formed."""


class TemporalFacet(Protocol):
    """Every accepted Entity's effective temporal shape, precomputed once.

    Both lookups are total, nonthrowing, and expected amortized ``O(1)``.
    ``shape`` covers every accepted Entity — a standalone Entity is its own
    family root — and is absent only for an Identity the model does not contain.
    ``axis`` is absent for such an Identity too, and for a dimension the Entity's
    shape does not declare.
    """

    def shape(self, entity: EntityIdentity) -> TemporalShape | None: ...
    def axis(
        self, entity: EntityIdentity, dimension: TemporalDimension
    ) -> AsOfAxisMetadata | None: ...


def _declared_axis(shape: TemporalShape, dimension: TemporalDimension) -> AsOfAxisMetadata | None:
    """The axis ``shape`` declares for ``dimension``, or absence.

    Derived from the shape rather than indexed alongside it: the variant already
    carries exactly the axes it declares, so a second index could disagree with
    it."""
    match shape, dimension:
        case NonTemporal(), _:
            return None
        case TransactionTimeOnly(transaction_time), TemporalDimension.TRANSACTION_TIME:
            return transaction_time
        case TransactionTimeOnly(), TemporalDimension.VALID_TIME:
            return None
        case Bitemporal(valid_time, _), TemporalDimension.VALID_TIME:
            return valid_time
        case Bitemporal(_, transaction_time), TemporalDimension.TRANSACTION_TIME:
            return transaction_time


class _TemporalFacet:
    """The compiled facet over a read-only shape index nothing else holds."""

    __slots__ = ("_shapes",)

    _shapes: Mapping[EntityIdentity, TemporalShape]

    def __init__(self, shapes: Mapping[EntityIdentity, TemporalShape]) -> None:
        self._shapes = MappingProxyType(dict(shapes))

    def shape(self, entity: EntityIdentity) -> TemporalShape | None:
        return self._shapes.get(entity)

    def axis(self, entity: EntityIdentity, dimension: TemporalDimension) -> AsOfAxisMetadata | None:
        shape = self._shapes.get(entity)
        return None if shape is None else _declared_axis(shape, dimension)


def temporal_facet(shapes: Mapping[EntityIdentity, TemporalShape]) -> TemporalFacet:
    """The facet serving ``shapes``, which names every Entity of one model.

    An Entity missing from ``shapes`` is unknown to the facet, so the compiler
    supplies a shape for every accepted Entity — including the non-temporal ones.
    """
    return _TemporalFacet(shapes)


def is_temporal_facet(value: object) -> TypeGuard[TemporalFacet]:
    """Whether ``value`` is a Temporal Facet this module compiled.

    ``m-temporal-read`` owns the sole compiler for its facet and this is its only
    output type, so provenance decides rather than the surface a value presents.

    Exists for the formation seam that receives a compiler's result and must
    classify a wrong-typed one as a contract failure rather than install it.
    """
    return isinstance(value, _TemporalFacet)


FACET_KEY: Final[FacetKey[TemporalFacet]] = FacetKey(TEMPORAL_READ_MODULE, is_temporal_facet)
"""The typed key this module's facet is installed and retrieved under."""


def view(model: Metamodel) -> TemporalFacet:
    """``model``'s Temporal Facet.

    The typed retrieval every behavioral consumer uses, so generic facet lookup
    stays an internal formation seam. Total for an accepted Metamodel, which by
    construction carries the complete facet set.
    """
    return model.facet(FACET_KEY)
