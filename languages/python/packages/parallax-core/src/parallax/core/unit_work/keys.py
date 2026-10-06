from __future__ import annotations

from collections.abc import Mapping

from parallax.core import inheritance
from parallax.core.metamodel import EntityMetadata, Metamodel, entity_by_name
from parallax.core.unit_work.instructions import (
    KeyedWrite,
    PreparedKeyedWrite,
    PreparedWrite,
    WriteInstruction,
)
from parallax.core.write_plan.keys import ObjectKey

__all__ = [
    "object_key",
    "resolve_object_key",
]


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
        return resolve_object_key(instruction, inheritance.view(model))
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) != 1:
        return None
    entity = entity_by_name(model, instruction.entity)
    if entity is None:
        return None
    return _row_identity(entity, inheritance.view(model), instruction.rows[0])


def resolve_object_key(
    instruction: PreparedWrite, families: inheritance.InheritanceFacet
) -> ObjectKey | None:
    """:func:`object_key` for a caller that already holds the Inheritance Facet.

    The key is the family's: an inheritance participant's key is declared on the
    root alone (m-inheritance "Inherited members"), so the Entity's own
    declarations are wrongly empty for a concrete subtype, and the compiled view
    names the root's key Attribute at every position.
    """
    if not isinstance(instruction, PreparedKeyedWrite) or len(instruction.rows) != 1:
        return None
    return _row_identity(instruction.target, families, instruction.rows[0])


def _row_identity(
    entity: EntityMetadata, families: inheritance.InheritanceFacet, row: Mapping[str, object]
) -> ObjectKey | None:
    """``row``'s Object Key under ``entity`` — the one key derivation both
    entry points share, so the family primary key stays one decision."""
    position = families.entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    name = position.primary_key.identity.name
    if name not in row:
        return None
    value = row[name]
    if isinstance(value, Mapping):
        return None
    return ObjectKey(entity.identity, ((name, value),))
