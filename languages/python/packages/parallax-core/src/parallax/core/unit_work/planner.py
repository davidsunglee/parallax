"""Shared write-planning foundation: entity resolution and the buffer item
shapes (m-unit-work).

:class:`Targets` is one planning call's resolution of the write IR's own
entity spellings and family membership, computed once per flush and threaded
through every stage that needs it — :mod:`~parallax.core.unit_work.
write_planner`'s coalescing, batching, ordering, and finalization stages, and
this module's own :func:`object_key`. :data:`BufferItem` is the buffered-write
shape those stages consume: an ordinary write instruction, or a materializing
predicate write's compact
:class:`~parallax.core.unit_work.materialized.MaterializedWriteGroup`.

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
    EntityMetadata,
    Metamodel,
    Multiplicity,
    PrimaryKey,
    ValueObjectIdentity,
)
from parallax.core.unit_work.instructions import KeyedWrite, WriteInstruction
from parallax.core.unit_work.materialized import MaterializedWriteGroup

__all__ = [
    "BufferItem",
    "ObjectKey",
    "Targets",
    "object_key",
    "primary_key_names",
    "resolve_object_key",
    "targets",
]

# One object's identity: (entity, ordered (pk-attribute-name, value) pairs). The
# coalescing scope and the observation binding are keyed by it.
ObjectKey = tuple[str, tuple[tuple[str, object], ...]]

# One writable member's resolved semantic identity, keyed by the spelling a
# write row names it with.
type _Members = Mapping[str, AttributeIdentity | ValueObjectIdentity]


@dataclass(frozen=True, slots=True)
class Targets:
    """One planning call's resolution of the write IR's own entity spellings.

    A write instruction names its entity by the spelling its canonical document
    carries (`write-instruction.schema.json`), which is a wire spelling rather
    than an Entity Identity. Resolving it needs the model, and every stage below
    then needs the same Entity's family-effective members, declaring root, and
    family-effective primary key, so one resolution is made per flush and
    threaded down rather than repeated per instruction or per stage.
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


# One buffer item: an ordinary write instruction, or a materializing predicate
# write's compact Materialized Write Group (`m-unit-work` "Materialized Write
# Groups", ADR 0014). A group is buffered as ONE opaque item at the call
# position (never split, never reordered internally) — EXEMPT from same-object
# coalescing (a materializing resolve only ever matches EXISTING rows, which
# read-your-own-writes has already flushed past any pending same-key insert,
# so no coalescing candidate can structurally arise) and from cross-unit
# reordering (dependency ordering moves it as ONE block, ranked by its own
# target entity, never reordering its rows internally). It settles directly
# into Planned Steps at finalization; a frozen Write Plan never carries this
# type at all.
BufferItem = WriteInstruction | MaterializedWriteGroup


def object_key(instruction: WriteInstruction, model: Metamodel) -> ObjectKey | None:
    """The identity of the single object a keyed write targets, or ``None``.

    ``None`` when the instruction is not a single-row keyed write, when its
    entity spelling names no Entity of ``model``, when the row does not carry
    every primary-key attribute (a pk-generated insert whose key is entirely
    DB-computed), or when a carried primary-key VALUE is itself a DB-computed
    marker (`m-pk-gen`'s `{computed: ...}` / `{increment: ...}` — a
    marker-shaped pk value has no coalescing identity, exactly like an absent
    one) — an unidentifiable write is never coalesced nor observation-bound.
    """
    return resolve_object_key(instruction, targets(model))


def resolve_object_key(instruction: WriteInstruction, resolved: Targets) -> ObjectKey | None:
    """:func:`object_key` over an already-resolved flush context.

    Primary-key resolution is FAMILY-EFFECTIVE: an inheritance participant's key
    is declared on the root alone (m-inheritance "Inherited members"), so the
    Entity's own declared Attributes are wrongly empty for a concrete subtype —
    every corpus family's own keyed writes — and the applicable member chain the
    Inheritance Facet precomputes is what carries the inherited key.
    """
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) != 1:
        return None
    entity = resolved.entity(instruction.entity)
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
    return (instruction.entity, tuple(pairs))


def primary_key_names(resolved: Targets, entity: EntityMetadata) -> list[str]:
    """``entity``'s family-effective primary-key Attribute names, in chain order."""
    return [attribute.identity.name for attribute in resolved.family_primary_key(entity)]
