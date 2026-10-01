from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard

from parallax.core.metamodel import AttributeIdentity, EntityIdentity, FacetKey, Metamodel
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    Concurrency,
    KeyedMutation,
    ObjectKey,
    RetainedObservation,
    SettledEvidence,
    WriteObservation,
)

__all__ = [
    "FACET_KEY",
    "OPT_LOCK_MODULE",
    "UNVERSIONED",
    "ExplicitVersion",
    "OptimisticKey",
    "OptimisticLockFacet",
    "TransactionTimeDerived",
    "Unversioned",
    "optimistic_lock_facet",
    "view",
]

OPT_LOCK_MODULE: Final[str] = "m-opt-lock"
"""The catalog identity that owns optimistic locking, its Issue Codes, and the
Optimistic Lock Facet."""


@dataclass(frozen=True, slots=True)
class Unversioned:
    """The family carries no version: a non-temporal family with no version
    Attribute. Its writes emit no gate and advance no version.

    With no gate to recover correctness with, it takes the Locking strategy
    under every preference, and an existing-row write settles against its
    OBJECT: the shared row lock its evidence rule demands is held on the object
    and covers every state the row can be in, so two such writes can never have
    observed two different states.
    """

    def effective_strategy(self, preference: Concurrency, /) -> Concurrency:
        del preference
        return "locking"

    def settled_evidence(
        self,
        mutation: KeyedMutation,
        /,
        *,
        object_key: ObjectKey | None,
        observation: WriteObservation | RetainedObservation | None,
    ) -> SettledEvidence | None:
        del observation
        return None if mutation in INSERT_MUTATIONS else object_key


# The shared instance of the nullary variant above. Variants are frozen value
# objects, so this is an allocation convenience rather than an identity: a fresh
# ``Unversioned()`` equals it and matches the same patterns.
UNVERSIONED: Final[Unversioned] = Unversioned()


@dataclass(frozen=True, slots=True)
class ExplicitVersion:
    """The family's root declares a version Attribute, named here by Identity.

    The preference decides its strategy, and an existing-row write settles
    against the exact state its source observed, because two writes of one key
    that observed two different states are two independent intents.
    """

    attribute: AttributeIdentity

    def effective_strategy(self, preference: Concurrency, /) -> Concurrency:
        return preference

    def settled_evidence(
        self,
        mutation: KeyedMutation,
        /,
        *,
        object_key: ObjectKey | None,
        observation: WriteObservation | RetainedObservation | None,
    ) -> SettledEvidence | None:
        del object_key
        return _observed_state(mutation, observation)


@dataclass(frozen=True, slots=True)
class TransactionTimeDerived:
    """The family is a Transaction-Time one, so its milestone start is the version.

    The observed start instant plays the part an explicit version plays: a
    concurrent chain that superseded the milestone left a fresh one, so its
    strategy and settled evidence are :class:`ExplicitVersion`'s.
    """

    start_attribute: AttributeIdentity

    def effective_strategy(self, preference: Concurrency, /) -> Concurrency:
        return preference

    def settled_evidence(
        self,
        mutation: KeyedMutation,
        /,
        *,
        object_key: ObjectKey | None,
        observation: WriteObservation | RetainedObservation | None,
    ) -> SettledEvidence | None:
        del object_key
        return _observed_state(mutation, observation)


def _observed_state(
    mutation: KeyedMutation, observation: WriteObservation | RetainedObservation | None
) -> SettledEvidence | None:
    """A versioned family's settled evidence: nothing for an insert, which opens
    a row rather than writing against one, and otherwise whatever its source
    observed — so a write whose source retained nothing settles against
    nothing, and the required-observation rule refuses it at settlement."""
    return None if mutation in INSERT_MUTATIONS else observation


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

    ``required_key`` answers the same key and raises ``KeyError`` for an
    Identity the model does not contain, for a consumer whose answer depends on
    which variant the family declares: reading a miss as :class:`Unversioned`
    would let an unrecognized Entity's write claim an object on the strength of
    what was missing.
    """

    def key(self, entity: EntityIdentity) -> OptimisticKey | None: ...

    def required_key(self, entity: EntityIdentity) -> OptimisticKey: ...


class _OptimisticLockFacet:
    """The compiled facet over a read-only key index nothing else holds."""

    __slots__ = ("_keys",)

    _keys: Mapping[EntityIdentity, OptimisticKey]

    def __init__(self, keys: Mapping[EntityIdentity, OptimisticKey]) -> None:
        self._keys = MappingProxyType(dict(keys))

    def key(self, entity: EntityIdentity) -> OptimisticKey | None:
        return self._keys.get(entity)

    def required_key(self, entity: EntityIdentity) -> OptimisticKey:
        key = self._keys.get(entity)
        if key is None:
            raise KeyError(
                f"{entity.canonical!r} names no Entity this model declares, so it carries no "
                "Optimistic Key; resolve a write's target against the model before deriving "
                "what that write settles against"
            )
        return key


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
