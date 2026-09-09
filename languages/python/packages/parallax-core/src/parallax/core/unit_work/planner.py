"""Shared write-planning foundation: entity resolution and the buffer item
shapes (m-unit-work).

:class:`FamilyFacts` is the accepted model and its compiled Inheritance Facet read
together, built once per model-scoped planner and threaded through every stage that
needs declaring roots, family-effective primary keys, and the compiled member view.
It holds two references and no index of its own. Raw authored input is the only
form that names its Entity by spelling, and it resolves through the accepted
model's own reference-position rule,
:func:`~parallax.core.metamodel.entity_by_name`, on that branch alone. The
buffered-write shapes those stages
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

from collections.abc import Mapping
from dataclasses import dataclass

from parallax.core import inheritance
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
    entity_by_name,
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
    "FamilyFacts",
    "ObjectKey",
    "ObservedStateKey",
    "TemporalStateKey",
    "VersionedStateKey",
    "family_facts",
    "object_key",
    "observed_state_key",
    "primary_key_names",
    "resolve_object_key",
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


@dataclass(frozen=True, slots=True)
class FamilyFacts:
    """One accepted model's family-effective facts, read off the Inheritance
    Facet it already carries.

    Two references and no index: every fact answered here is an O(1) read of a
    precompiled :class:`~parallax.core.inheritance.InheritanceEntityView`, so a
    model-scoped holder builds one once and prepares nothing the facet does not
    already hold. It resolves no entity spelling — a prepared write carries the
    exact target Metadata, and raw authored input resolves its spelling
    through :func:`~parallax.core.metamodel.entity_by_name`, the accepted
    model's own rule for an Entity spelling in a reference position.
    """

    model: Metamodel
    families: inheritance.InheritanceFacet

    def view(self, entity: EntityMetadata) -> inheritance.InheritanceEntityView:
        """``entity``'s compiled family-effective view — its applicable member
        chain and the indexes over it a write row's names resolve through.

        An inheritance participant declares only its own members while its
        writes name every inherited one, so the applicable chain, not the
        Entity's own declarations, is what a write-side member lookup reads.
        """
        position = self.families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
        return position

    def declaring(self, entity: EntityMetadata) -> EntityMetadata:
        """The accepted Metadata that DECLARES ``entity``'s family facts — its
        family root, itself for a standalone Entity.

        Temporality, the version column, and the physical primary key are
        family-wide and root-owned (`m-inheritance` "Inherited members"), so
        every write-side family fact resolves through this rather than through
        a possibly-empty local declaration.
        """
        root = self.model.entity(self.view(entity).root)
        return entity if root is None else root

    def primary_key(self, entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
        """``entity``'s family-effective primary key, in chain order."""
        return tuple(
            attribute
            for attribute in self.view(entity).applicable_attributes
            if isinstance(attribute.primary_key, PrimaryKey)
        )


def family_facts(model: Metamodel) -> FamilyFacts:
    """``model``'s family-fact reader over the Inheritance Facet it carries."""
    return FamilyFacts(model=model, families=inheritance.view(model))


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
    if isinstance(instruction, PreparedKeyedWrite):
        return resolve_object_key(instruction, family_facts(model))
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) != 1:
        return None
    entity = entity_by_name(model, instruction.entity)
    if entity is None:
        return None
    return _row_identity(entity, family_facts(model), instruction.rows[0])


def resolve_object_key(instruction: PreparedWrite, families: FamilyFacts) -> ObjectKey | None:
    """:func:`object_key` for a caller that already holds the family facts.

    Primary-key resolution is FAMILY-EFFECTIVE: an inheritance participant's key
    is declared on the root alone (m-inheritance "Inherited members"), so the
    Entity's own declared Attributes are wrongly empty for a concrete subtype —
    every corpus family's own keyed writes — and the applicable member chain the
    Inheritance Facet precomputes is what carries the inherited key.
    """
    if not isinstance(instruction, PreparedKeyedWrite) or len(instruction.rows) != 1:
        return None
    return _row_identity(instruction.target, families, instruction.rows[0])


def _row_identity(
    entity: EntityMetadata, families: FamilyFacts, row: Mapping[str, object]
) -> ObjectKey | None:
    """``row``'s Object Key under ``entity`` — the one key derivation both
    entry points share, so the family-effective primary key stays one decision."""
    # An accepted Entity always carries a primary key, so the family-effective
    # chain is never empty and only the row itself can leave a write unkeyed.
    pairs: list[tuple[str, object]] = []
    for name in primary_key_names(families, entity):
        if name not in row:
            return None
        value = row[name]
        if isinstance(value, Mapping):
            return None
        pairs.append((name, value))
    return ObjectKey(entity.identity, tuple(pairs))


def primary_key_names(families: FamilyFacts, entity: EntityMetadata) -> list[str]:
    """``entity``'s family-effective primary-key Attribute names, in chain order."""
    return [attribute.identity.name for attribute in families.primary_key(entity)]
