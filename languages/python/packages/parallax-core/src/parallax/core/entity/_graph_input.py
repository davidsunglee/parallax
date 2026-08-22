"""The immutable carrier algebra Entity Graph Construction is stated in.

Scoped apart from the collaboration that consumes it so a lifecycle package
materializing Entities can be granted the carriers alone: every producer of
them and Entity Graph Construction share one exact recursive immutable algebra,
and defining it twice would let the two drift. Granting only this scope is what
keeps a carrier producer structurally unable to reach model formation, the
writer, or ``construct`` itself.

Frozen slotted records and exact built-in tuples only: no mapping, abstract
sequence, mutable collection, raw document dictionary, or caller-defined
collection subtype crosses the seam these describe. Absence is represented by
omitting an entry, never by a sentinel value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.metamodel import (
    AttributeIdentity,
    RelationshipIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)

__all__ = [
    "LOADED_NULL",
    "UNLOADED_VIEW",
    "EntityAttributeInput",
    "EntityRelationshipInput",
    "LoadedMany",
    "LoadedNull",
    "LoadedOne",
    "NodeHandle",
    "RelationshipInput",
    "Unloaded",
    "ValueObjectAttributeInput",
    "ValueObjectOccurrenceInput",
    "ValueObjectRecord",
]


class NodeHandle:
    """An opaque, callback-scoped reference to one allocated node.

    It holds nothing whatever: the issuing construction owns the mapping from
    handle to allocation index, so a handle exposes no attribute to read, no
    index to restate, and no route to a partially built instance. A caller
    composes graph shape by passing handles back, never by reading anything off
    one, and a handle means nothing outside the ``construct(...)`` call that
    issued it.
    """

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class EntityAttributeInput:
    """One scalar Attribute entry: its structured identity and its Neutral Value.

    ``value`` is ``None`` exactly for a loaded-null scalar, which is legal only
    where the Attribute is nullable. Omitting the entry entirely leaves the member
    at its declared default instead.
    """

    identity: AttributeIdentity
    value: object | None


@dataclass(frozen=True, slots=True)
class ValueObjectAttributeInput:
    """One scalar leaf of one Value Object occurrence."""

    identity: ValueObjectAttributeIdentity
    value: object | None


@dataclass(frozen=True, slots=True)
class ValueObjectRecord:
    """One Value Object value, as its scalar leaves and nested occurrences.

    Entry order in either tuple is non-semantic: entries are indexed by structured
    identity and constructed in accepted metadata declaration order. Absence is
    represented only by omitting the entry.
    """

    attributes: tuple[ValueObjectAttributeInput, ...] = ()
    value_objects: tuple[ValueObjectOccurrenceInput, ...] = ()


@dataclass(frozen=True, slots=True)
class ValueObjectOccurrenceInput:
    """One Value Object occurrence entry at any containment depth.

    A One occurrence carries a record or ``None``; a Many occurrence carries an
    ordered tuple of records whose order is semantic and preserved exactly.
    """

    identity: ValueObjectIdentity
    value: ValueObjectRecord | tuple[ValueObjectRecord, ...] | None


@dataclass(frozen=True, slots=True)
class Unloaded:
    """The relationship arm meaning the read did not fetch this view at all."""


@dataclass(frozen=True, slots=True)
class LoadedNull:
    """The relationship arm meaning a to-one view was fetched and is null."""


@dataclass(frozen=True, slots=True)
class LoadedOne:
    """The relationship arm meaning a to-one view was fetched and reached a node."""

    node: NodeHandle


@dataclass(frozen=True, slots=True)
class LoadedMany:
    """The relationship arm meaning a to-many view was fetched; order is semantic
    and ``()`` is loaded-empty."""

    nodes: tuple[NodeHandle, ...]


type RelationshipInput = Unloaded | LoadedNull | LoadedOne | LoadedMany
"""The closed arm algebra one relationship view's populated state is stated in."""

UNLOADED_VIEW: Final[Unloaded] = Unloaded()
"""The sole :class:`Unloaded` value; the arms are values rather than sentinels so
a mistyped arm is a shape rejection rather than a silent pass-through."""

LOADED_NULL: Final[LoadedNull] = LoadedNull()
"""The sole :class:`LoadedNull` value."""


@dataclass(frozen=True, slots=True)
class EntityRelationshipInput:
    """One relationship view entry: the direction it names and its loaded state."""

    identity: RelationshipIdentity
    value: RelationshipInput
