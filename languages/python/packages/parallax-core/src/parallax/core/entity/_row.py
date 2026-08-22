"""The positional member row: the sentinel it spells absence with, and what it
becomes at Entity Graph Construction's door.

A runtime that materializes values from stored rows lays each row out against
its exact Entity's member layout (:mod:`parallax.core.entity._layout`) and hands
the result to the writer as the immutable carrier algebra
(:mod:`parallax.core.entity._graph_input`). Both ends of that translation are
facts about the accepted model and the carriers, so the walk between them is
owned here rather than by whichever runtime reads a row first: two managed value
lifecycles materializing from one row read it the one way, and neither declares
an absence marker the other's rows do not hold.

Scoped apart from the frontend for the same reason the carriers are, and one
step further: producing a carrier must not reach the writer, ``construct``, or
model formation, and this scope's own grants are what prove it.

A row is positional and therefore cannot omit, which is the one distinction the
carriers do not share — an absent position contributes no entry at all, which is
what their algebra means by absence, at every containment depth.
"""

from __future__ import annotations

from typing import Final, cast

from parallax.core.entity._graph_input import (
    EntityAttributeInput,
    ValueObjectAttributeInput,
    ValueObjectOccurrenceInput,
    ValueObjectRecord,
)
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)

__all__ = ["ABSENT", "Absent", "member_carriers"]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata


class Absent:
    """The type of :data:`ABSENT`, named so a reader can spell the test."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT: Final[Absent] = Absent()
"""The one absent-or-unloaded sentinel a positional member row spells absence
with, private to this implementation.

Deliberately not the document codec's ``MISSING`` or ``UNAVAILABLE``, which are
consumed and discarded inside decoding and describe a stored document rather
than a materialized row. It never escapes as a final public value: every
consumer of a row either skips an absent position or is refused before
publication.
"""


def member_carriers(
    layout: EntityLayout, values: tuple[object, ...]
) -> tuple[tuple[EntityAttributeInput, ...], tuple[ValueObjectOccurrenceInput, ...]]:
    """One node's member row as the writer's Attribute and Value Object carriers.

    ``values`` is read against ``layout``: its Attributes in the layout's own
    order, then its top-level Value Object occurrences in theirs. An absent
    position contributes no entry, which is what the carrier algebra means by
    absence.

    The pair is one node's worth, answered in ``populate``'s own argument order
    so a caller hands it straight over rather than binding it: ``populate``
    retains none of it, and a name outliving that call is the only thing that
    makes carrier cost more than one node's.
    """
    return _attributes(layout, values), _value_objects(layout, values)


def _attributes(
    layout: EntityLayout, values: tuple[object, ...]
) -> tuple[EntityAttributeInput, ...]:
    return tuple(
        EntityAttributeInput(attribute.identity, values[position])
        for position, attribute in enumerate(layout.attributes)
        if values[position] is not ABSENT
    )


def _value_objects(
    layout: EntityLayout, values: tuple[object, ...]
) -> tuple[ValueObjectOccurrenceInput, ...]:
    return tuple(
        ValueObjectOccurrenceInput(occurrence.identity, _occurrence(values[position], occurrence))
        for position, occurrence in enumerate(layout.occurrences, start=layout.attribute_count)
        if values[position] is not ABSENT
    )


def _occurrence(
    value: object, declared: _VoContainer
) -> ValueObjectRecord | tuple[ValueObjectRecord, ...] | None:
    """One occurrence slot as the writer's record algebra.

    The declared multiplicity decides the shape rather than the value does: a One
    slot's member row and a Many slot's tuple of them are both tuples, and only
    the declaration distinguishes them.
    """
    if declared.multiplicity is Multiplicity.MANY:
        return tuple(
            _value_object(cast("tuple[object, ...]", row), declared) for row in _rows(value)
        )
    if value is None:
        return None
    return _value_object(cast("tuple[object, ...]", value), declared)


def _rows(value: object) -> tuple[object, ...]:
    return cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()


def _value_object(row: tuple[object, ...], declared: _VoContainer) -> ValueObjectRecord:
    """One positional member row as one writer record, at every depth."""
    return ValueObjectRecord(
        attributes=tuple(
            ValueObjectAttributeInput(leaf.identity, row[position])
            for position, leaf in enumerate(declared.attributes)
            if row[position] is not ABSENT
        ),
        value_objects=tuple(
            ValueObjectOccurrenceInput(nested.identity, _occurrence(row[position], nested))
            for position, nested in enumerate(
                declared.value_objects, start=len(declared.attributes)
            )
            if row[position] is not ABSENT
        ),
    )
