from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from parallax.core import inheritance
from parallax.core._execution._unit_work.instructions import (
    KeyedWriteInstruction,
    PreparedInstruction,
    PreparedKeyedInstruction,
    WriteInstruction,
)
from parallax.core.metamodel import AttributeIdentity, EntityMetadata, Metamodel, entity_by_name
from parallax.core.write_plan.keys import ObjectKey
from parallax.core.write_plan.steps import MaxPlusOne

__all__ = [
    "object_key",
    "resolve_object_key",
]


def object_key(
    instruction: WriteInstruction | PreparedInstruction, model: Metamodel
) -> ObjectKey | None:
    """The identity of the single object a keyed write targets, or ``None``.

    Prepared input consumes its retained target Metadata; the raw authored-input utility
    resolves an entity spelling against ``model``. ``None`` results when the instruction
    is not a single-row keyed write, that raw spelling is unresolved, or the row lacks
    every primary-key attribute (a pk-generated insert whose key is entirely
    DB-computed), or when a carried primary-key VALUE is itself DB-computed —
    an authored `m-pk-gen` marker (`{computed: ...}` / `{increment: ...}`) or
    the allocation preparation planned from it. A DB-computed pk value has no
    coalescing identity, exactly like an absent one: an unidentifiable write is
    never coalesced nor observation-bound, and opens no insertion.
    """
    if isinstance(instruction, PreparedKeyedInstruction):
        return resolve_object_key(instruction, inheritance.view(model))
    if not isinstance(instruction, KeyedWriteInstruction) or len(instruction.rows) != 1:
        return None
    entity = entity_by_name(model, instruction.entity)
    if entity is None:
        return None
    name = _key_attribute(entity, inheritance.view(model)).name
    row = instruction.rows[0]
    return _identity(entity, name, row.get(name, _UNSTATED))


def resolve_object_key(
    instruction: PreparedInstruction, families: inheritance.InheritanceFacet
) -> ObjectKey | None:
    """:func:`object_key` for a caller that already holds the Inheritance Facet.

    The key is the family's: an inheritance participant's key is declared on the
    root alone (m-inheritance "Inherited members"), so the Entity's own
    declarations are wrongly empty for a concrete subtype, and the compiled view
    names the root's key Attribute at every position.
    """
    if not isinstance(instruction, PreparedKeyedInstruction) or len(instruction.rows) != 1:
        return None
    entity = instruction.target
    attribute = _key_attribute(entity, families)
    (row,) = instruction.rows
    value = row.cell(attribute)
    return _identity(entity, attribute.name, _UNSTATED if value is row.selection.absent else value)


_UNSTATED: Final = object()


def _key_attribute(
    entity: EntityMetadata, families: inheritance.InheritanceFacet
) -> AttributeIdentity:
    """``entity``'s family primary-key Attribute — the one key derivation both
    entry points share, so the family primary key stays one decision."""
    position = families.entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    return position.primary_key.identity


def _identity(entity: EntityMetadata, name: str, value: object) -> ObjectKey | None:
    if value is _UNSTATED or isinstance(value, Mapping | MaxPlusOne):
        return None
    return ObjectKey(entity.identity, ((name, value),))
