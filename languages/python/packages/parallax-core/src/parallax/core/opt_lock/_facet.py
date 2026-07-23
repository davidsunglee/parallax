"""The Optimistic Lock Facet and its typed retrieval (m-opt-lock).

A write needs one answer before it can gate or advance anything: what identifies
the version of this row? That answer is family-level — a family is versioned
together or not at all — and it has exactly three forms. This module owns them as
one immutable per-formation view, precomputed once so a write path never
rediscovers a version column.

The keyed variants carry Attribute Identities rather than Attribute Metadata, so
a consumer resolves the physical column through the Metamodel's own local lookup
and nothing here duplicates it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard

from parallax.core.metamodel import AttributeIdentity, EntityIdentity, FacetKey, Metamodel

__all__ = [
    "FACET_KEY",
    "OPT_LOCK_MODULE",
    "UNVERSIONED",
    "ExplicitVersion",
    "OptimisticKey",
    "OptimisticLockFacet",
    "TransactionTimeDerived",
    "Unversioned",
    "is_optimistic_lock_facet",
    "optimistic_lock_facet",
    "view",
]

OPT_LOCK_MODULE: Final[str] = "m-opt-lock"
"""The catalog identity that owns optimistic locking, its Issue Codes, and the
Optimistic Lock Facet."""


@dataclass(frozen=True, slots=True)
class Unversioned:
    """The family carries no version: a non-temporal family with no version
    Attribute. Its writes emit no gate and advance no version."""


# The shared instance of the nullary variant above. Variants are frozen value
# objects, so this is an allocation convenience rather than an identity: a fresh
# ``Unversioned()`` equals it and matches the same patterns.
UNVERSIONED: Final[Unversioned] = Unversioned()


@dataclass(frozen=True, slots=True)
class ExplicitVersion:
    """The family's root declares a version Attribute, named here by Identity."""

    attribute: AttributeIdentity


@dataclass(frozen=True, slots=True)
class TransactionTimeDerived:
    """The family is a Transaction-Time one, so its milestone start is the version.

    The observed start instant plays the part an explicit version plays: a
    concurrent chain that superseded the milestone left a fresh one.
    """

    start_attribute: AttributeIdentity


type OptimisticKey = Unversioned | ExplicitVersion | TransactionTimeDerived
"""What identifies a row's version. The two keyed variants are mutually
exclusive: a Transaction-Time Entity may not also declare a version Attribute,
and no supported temporal shape lacks Transaction Time."""


class OptimisticLockFacet(Protocol):
    """Every accepted Entity's optimistic key, precomputed once.

    ``key`` is total, nonthrowing, and expected amortized ``O(1)``, absent only
    for an Identity the model does not contain. It is family-uniform: every
    position in one family answers with its root's key, and a standalone Entity
    is its own root.
    """

    def key(self, entity: EntityIdentity) -> OptimisticKey | None: ...


class _OptimisticLockFacet:
    """The compiled facet over a read-only key index nothing else holds."""

    __slots__ = ("_keys",)

    _keys: Mapping[EntityIdentity, OptimisticKey]

    def __init__(self, keys: Mapping[EntityIdentity, OptimisticKey]) -> None:
        self._keys = MappingProxyType(dict(keys))

    def key(self, entity: EntityIdentity) -> OptimisticKey | None:
        return self._keys.get(entity)


def optimistic_lock_facet(keys: Mapping[EntityIdentity, OptimisticKey]) -> OptimisticLockFacet:
    """The facet serving ``keys``, which names every Entity of one model.

    An Entity missing from ``keys`` is unknown to the facet, so the compiler
    supplies a key for every accepted Entity — including the unversioned ones.
    """
    return _OptimisticLockFacet(keys)


def is_optimistic_lock_facet(value: object) -> TypeGuard[OptimisticLockFacet]:
    """Whether ``value`` is an Optimistic Lock Facet this module compiled.

    ``m-opt-lock`` owns the sole compiler for its facet and this is its only
    output type, so provenance decides rather than the surface a value presents.

    Exists for the formation seam that receives a compiler's result and must
    classify a wrong-typed one as a contract failure rather than install it.
    """
    return isinstance(value, _OptimisticLockFacet)


FACET_KEY: Final[FacetKey[OptimisticLockFacet]] = FacetKey(
    OPT_LOCK_MODULE, is_optimistic_lock_facet
)
"""The typed key this module's facet is installed and retrieved under."""


def view(model: Metamodel) -> OptimisticLockFacet:
    """``model``'s Optimistic Lock Facet.

    The typed retrieval every behavioral consumer uses, so generic facet lookup
    stays an internal formation seam. Total for an accepted Metamodel, which by
    construction carries the complete facet set.
    """
    return model.facet(FACET_KEY)
