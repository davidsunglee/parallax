from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol, TypeGuard

from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.internal.metamodel._accepted import FacetKey, facet_of

__all__ = [
    "CONCURRENCY_MODULE",
    "FACET_KEY",
    "UNVERSIONED",
    "ConcurrencyFacet",
    "ConcurrencyPreference",
    "ConcurrencyStrategy",
    "EvidenceKind",
    "ExplicitVersion",
    "TransactionTimeVersion",
    "Unversioned",
    "VersionSource",
    "concurrency_facet",
    "concurrency_facet_of",
]

CONCURRENCY_MODULE: Final[str] = "m-concurrency"
"""The catalog identity that owns concurrency policy, its Issue Codes, and the
Concurrency Facet."""

ConcurrencyStrategy = Literal["locking", "optimistic"]
"""The Effective Concurrency Strategy one Entity participates under."""

ConcurrencyPreference = ConcurrencyStrategy
"""A unit of work's requested Concurrency Preference, spelled as the strategy
it asks for: ``optimistic`` asks for gates wherever the model supplies them."""

type EvidenceKind = Literal["observation", "object"]
"""What a family's write against an existing row settles against: the state its
source observed, or the object it writes."""


@dataclass(frozen=True, slots=True)
class Unversioned:
    """The family carries no version: a Non-Temporal family with no version
    Attribute."""


# Variants are frozen value objects, so this shared instance is an allocation
# convenience rather than an identity.
UNVERSIONED: Final[Unversioned] = Unversioned()


@dataclass(frozen=True, slots=True)
class ExplicitVersion:
    """The family's root declares a version Attribute, named here by Identity."""

    attribute: AttributeIdentity


@dataclass(frozen=True, slots=True)
class TransactionTimeVersion:
    """The family is a Transaction-Time one, so its milestone start is the version."""

    start_attribute: AttributeIdentity


type VersionSource = Unversioned | ExplicitVersion | TransactionTimeVersion
"""What identifies a row's version. The two versioned variants are mutually
exclusive: a Transaction-Time Entity may not also declare a version Attribute."""


class ConcurrencyFacet(Protocol):
    """Every accepted Entity's concurrency answers, precomputed once and uniform
    across a family, whose root decides them.

    For an Identity the model does not contain, each question answers the way
    that is safe for what it is used for: the strategy is Locking, the version
    Attribute and version source are absent, and :meth:`settles_against` raises
    ``KeyError``, because reading a miss as an object claim would let an
    unrecognized Entity's write claim an object on the strength of what was
    missing.
    """

    def effective_strategy(
        self, entity: EntityIdentity, preference: ConcurrencyPreference
    ) -> ConcurrencyStrategy: ...

    def version_attribute(self, entity: EntityIdentity) -> AttributeIdentity | None: ...

    def settles_against(self, entity: EntityIdentity) -> EvidenceKind: ...

    def version_source(self, entity: EntityIdentity) -> VersionSource | None: ...


class _CompiledConcurrencyFacet:
    """The compiled facet over read-only per-Entity answers nothing else holds."""

    __slots__ = ("_attributes", "_sources", "_versioned")

    _sources: Mapping[EntityIdentity, VersionSource]
    _attributes: Mapping[EntityIdentity, AttributeIdentity]
    _versioned: frozenset[EntityIdentity]

    def __init__(self, sources: Mapping[EntityIdentity, VersionSource]) -> None:
        self._sources = MappingProxyType(dict(sources))
        self._attributes = MappingProxyType(
            {
                entity: source.attribute
                for entity, source in sources.items()
                if isinstance(source, ExplicitVersion)
            }
        )
        self._versioned = frozenset(
            entity for entity, source in sources.items() if not isinstance(source, Unversioned)
        )

    def effective_strategy(
        self, entity: EntityIdentity, preference: ConcurrencyPreference
    ) -> ConcurrencyStrategy:
        return preference if entity in self._versioned else "locking"

    def version_attribute(self, entity: EntityIdentity) -> AttributeIdentity | None:
        return self._attributes.get(entity)

    def settles_against(self, entity: EntityIdentity) -> EvidenceKind:
        if entity in self._versioned:
            return "observation"
        if entity in self._sources:
            return "object"
        raise KeyError(
            f"{entity.canonical!r} names no Entity this model declares, so it has no version "
            "source; resolve a write's target against the model before deriving what that "
            "write settles against"
        )

    def version_source(self, entity: EntityIdentity) -> VersionSource | None:
        return self._sources.get(entity)


def concurrency_facet(sources: Mapping[EntityIdentity, VersionSource]) -> ConcurrencyFacet:
    """The facet answering from ``sources``, which names every Entity of one model.

    An Entity missing from ``sources`` is unknown to the facet, so the compiler
    supplies a version source for every accepted Entity, the unversioned ones
    included.
    """
    return _CompiledConcurrencyFacet(sources)


def is_concurrency_facet(value: object) -> TypeGuard[ConcurrencyFacet]:
    """Whether ``value`` is a Concurrency Facet this module compiled.

    ``m-concurrency`` owns the sole compiler for its facet and this is its only
    output type, so provenance decides rather than the surface a value presents.
    """
    return isinstance(value, _CompiledConcurrencyFacet)


FACET_KEY: Final[FacetKey[ConcurrencyFacet]] = FacetKey(CONCURRENCY_MODULE, is_concurrency_facet)
"""The typed key this module's facet is installed and retrieved under."""


def concurrency_facet_of(model: Metamodel) -> ConcurrencyFacet:
    """``model``'s Concurrency Facet, the typed retrieval every consumer uses.

    Total for an accepted Metamodel, which by construction carries the complete
    facet set.
    """
    return facet_of(model, FACET_KEY)
