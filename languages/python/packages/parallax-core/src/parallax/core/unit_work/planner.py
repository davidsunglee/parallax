"""Shared write-planning foundation: entity resolution and the buffer item
shapes (m-unit-work).

:class:`Targets` is one planning call's accepted-model resolution context,
computed once per flush and threaded through every stage that needs family-effective
members, declaring roots, and primary keys. Prepared writes already retain exact target
metadata; the spelling index remains only for :func:`object_key`'s raw authored-input
utility. The buffered-write shapes those stages
consume are :mod:`~parallax.core.unit_work.materialized`'s, which is also where
the evidence they carry lives.

Bare (non-underscored) names here are intra-package shared infrastructure —
privacy is carried by ``__all__`` and by this being an internal engine seam
nothing outside ``parallax.core.unit_work`` imports, not by per-name
underscores, mirroring :mod:`parallax.snapshot.handle._family`'s own
convention for the same reason: an underscored name imported across a sibling
module is a Pyright strict ``reportPrivateUsage`` error.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core import inheritance
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    PrimaryKey,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import Edge, milestone_edge_from_members
from parallax.core.unit_work.instructions import (
    KeyedWrite,
    PreparedKeyedWrite,
    PreparedWrite,
    WriteInstruction,
)
from parallax.core.unit_work.observe import TemporalObservation, WriteObservation

__all__ = [
    "ObjectKey",
    "ObservedStateKey",
    "Targets",
    "TemporalStateKey",
    "VersionedStateKey",
    "object_key",
    "observed_state_key",
    "primary_key_names",
    "resolve_object_key",
    "targets",
]


@dataclass(frozen=True, slots=True)
class ObjectKey:
    """One object's identity: its Entity and its ordered
    ``(pk-attribute-name, value)`` pairs. The coalescing scope is keyed by it,
    and it is the identity half of every :data:`ObservedStateKey`.

    It is deliberately STATE-independent — no version, no milestone — so it
    addresses the object across its states, which is what write coalescing,
    cancellation, and buffered-insert recognition each ask about.

    ``entity`` is the structured Entity Identity rather than a spelling of one,
    so no producer stringifies an identity it already holds and two entities
    sharing a bare name across namespaces cannot resolve one another's
    observations.
    """

    entity: EntityIdentity
    primary_key: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class VersionedStateKey:
    """One exact observed state of a versioned Non-Temporal object: the object,
    and the optimistic-lock version the read saw it at.

    The version is part of the key rather than payload beside it, so two reads
    that saw two generations of one row address two states and neither can erase
    the other's evidence.
    """

    object: ObjectKey
    version: int


@dataclass(frozen=True, slots=True)
class TemporalStateKey:
    """One exact observed state of a temporal object: the object, and the
    milestone the read saw it at.

    A milestone chain holds more than one row per primary key at a time, so
    identity alone cannot address the evidence a write needs. Two reads of ONE
    milestone at different pins share one coordinate and therefore one state: an
    observation records the row that was read and nothing about the read that
    reached it, so the two are equal.
    """

    object: ObjectKey
    milestone: Edge


type ObservedStateKey = VersionedStateKey | TemporalStateKey
"""What one Write Observation is evidence ABOUT: one exact observed state.

Closed and structural. An insert and an unversioned Non-Temporal write observe
no state and therefore have no Observed State Key at all — the absence is the
missing arm, never a key with an empty coordinate.
"""


def observed_state_key(
    object_key: ObjectKey, observation: WriteObservation, declaring_entity: EntityMetadata
) -> ObservedStateKey:
    """The exact state ``observation`` is evidence about: ``object_key``
    qualified by the coordinate the observation itself carries.

    The coordinate is derived from the observation's OWN evidence rather than
    supplied beside it, so a recorder cannot file an observation under a state
    other than the one it is recording — the two-sides-agree property holds by
    construction rather than by every recording site being careful.

    ``declaring_entity`` is the family root that declares the As-Of Axes, whose
    start Attributes name the members a temporal coordinate is read from.
    """
    if not isinstance(observation, TemporalObservation):
        return VersionedStateKey(object_key, observation.observed_version)
    return TemporalStateKey(
        object_key,
        milestone_edge_from_members(declaring_entity, observation.predecessor.members),
    )


# One writable member's resolved semantic identity, keyed by the spelling a
# write row names it with.
type _Members = Mapping[str, AttributeIdentity | ValueObjectIdentity]


@dataclass(frozen=True, slots=True)
class Targets:
    """One flush's accepted-model context for prepared-write planning.

    Prepared writes retain exact target Metadata. The context centralizes the target's
    family-effective members, declaring root, and primary key; ``by_spelling`` supports
    only the raw authored-input form accepted by :func:`object_key`.
    """

    model: Metamodel
    by_spelling: Mapping[str, EntityMetadata]
    families: inheritance.InheritanceFacet

    def entity(self, spelling: str) -> EntityMetadata | None:
        """The accepted Metadata ``spelling`` names, or absence.

        The canonical spelling always resolves; a bare declared name resolves
        only when the model declares it once, so an ambiguous bare name reaches
        no Entity rather than an arbitrary one.
        """
        return self.by_spelling.get(spelling)

    def members(self, entity: EntityMetadata) -> Sequence[AttributeMetadata]:
        """``entity``'s family-effective Attributes, root first.

        An inheritance participant declares only its own members while its
        writes name every inherited one, so the applicable chain — not the
        Entity's own declarations — is what a write-side member lookup reads.
        """
        position = self.families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            return entity.declared_attributes
        return position.applicable_attributes

    def declaring(self, entity: EntityMetadata) -> EntityMetadata:
        """The accepted Metadata that DECLARES ``entity``'s family facts — its
        family root, itself for a standalone Entity.

        Temporality, the version column, and the physical primary key are
        family-wide and root-owned (`m-inheritance` "Inherited members"), so
        every write-side family fact resolves through this rather than through
        a possibly-empty local declaration.
        """
        position = self.families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            return entity
        root = self.model.entity(position.root)
        return entity if root is None else root

    def family_primary_key(self, entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
        """``entity``'s family-effective primary key, in chain order."""
        return tuple(
            attribute
            for attribute in self.members(entity)
            if isinstance(attribute.primary_key, PrimaryKey)
        )

    def applicable_members(self, entity: EntityMetadata) -> _Members:
        """``entity``'s family-effective writable members, by the spelling a
        write row names each one with.

        An inheritance participant declares its own members while its writes
        name every inherited one, so the applicable member chain — not the
        Entity's own declarations — is what a write-side lookup reads.
        """
        position = self.families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            return {}
        resolved: dict[str, AttributeIdentity | ValueObjectIdentity] = {
            attribute.identity.name: attribute.identity
            for attribute in position.applicable_attributes
        }
        for value_object in position.applicable_value_objects:
            resolved[value_object.identity.path[-1]] = value_object.identity
        return resolved

    def zero_state_members(self, entity: EntityMetadata) -> tuple[str, ...]:
        """The member spellings whose ABSENCE from an opening row is a value.

        Exactly ``entity``'s family-effective `many` Value Object occurrences.
        Absence and the empty collection are one logical zero state for a `many`
        (`m-value-object`), so a row that does not name one has said it holds no
        elements — which makes the occurrence part of that row's canonical member
        set whether or not the row spells it out.
        """
        position = self.families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            return ()
        return tuple(
            value_object.identity.path[-1]
            for value_object in position.applicable_value_objects
            if value_object.multiplicity is Multiplicity.MANY
        )


def targets(model: Metamodel) -> Targets:
    by_spelling = {entity.identity.canonical: entity for entity in model.entities}
    counts: dict[str, int] = {}
    for entity in model.entities:
        counts[entity.identity.name] = counts.get(entity.identity.name, 0) + 1
    for entity in model.entities:
        if counts[entity.identity.name] == 1:
            by_spelling.setdefault(entity.identity.name, entity)
    return Targets(model=model, by_spelling=by_spelling, families=inheritance.view(model))


def object_key(instruction: WriteInstruction | PreparedWrite, model: Metamodel) -> ObjectKey | None:
    """The identity of the single object a keyed write targets, or ``None``.

    Prepared input consumes its retained target Metadata; the raw authored-input utility
    resolves an entity spelling against ``model``. ``None`` results when the instruction
    is not a single-row keyed write, that raw spelling is unresolved, or the row lacks
    every primary-key attribute (a pk-generated insert whose key is entirely
    DB-computed), or when a carried primary-key VALUE is itself a DB-computed
    marker (`m-pk-gen`'s `{computed: ...}` / `{increment: ...}` — a
    marker-shaped pk value has no coalescing identity, exactly like an absent
    one) — an unidentifiable write is never coalesced nor observation-bound.
    """
    return resolve_object_key(instruction, targets(model))


def resolve_object_key(
    instruction: WriteInstruction | PreparedWrite, resolved: Targets
) -> ObjectKey | None:
    """:func:`object_key` over an already-resolved flush context.

    Primary-key resolution is FAMILY-EFFECTIVE: an inheritance participant's key
    is declared on the root alone (m-inheritance "Inherited members"), so the
    Entity's own declared Attributes are wrongly empty for a concrete subtype —
    every corpus family's own keyed writes — and the applicable member chain the
    Inheritance Facet precomputes is what carries the inherited key.

    The key always names the resolved Entity Identity. Prepared input carries that target
    directly; raw authored input resolves either accepted spelling to the same identity.
    """
    if not isinstance(instruction, (KeyedWrite, PreparedKeyedWrite)) or len(instruction.rows) != 1:
        return None
    entity = (
        instruction.target
        if isinstance(instruction, PreparedKeyedWrite)
        else resolved.entity(instruction.entity)
    )
    if entity is None:
        return None
    # An accepted Entity always carries a primary key, so the family-effective
    # chain is never empty and only the row itself can leave a write unkeyed.
    pk_names = primary_key_names(resolved, entity)
    row = instruction.rows[0]
    pairs: list[tuple[str, object]] = []
    for name in pk_names:
        if name not in row:
            return None
        value = row[name]
        if isinstance(value, Mapping):
            return None
        pairs.append((name, value))
    return ObjectKey(entity.identity, tuple(pairs))


def primary_key_names(resolved: Targets, entity: EntityMetadata) -> list[str]:
    """``entity``'s family-effective primary-key Attribute names, in chain order."""
    return [attribute.identity.name for attribute in resolved.family_primary_key(entity)]
