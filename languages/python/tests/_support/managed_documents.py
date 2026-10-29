from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core.base import FrozenMap
from parallax.core.document_codec import MemberShape, OccurrenceDefinition, ScalarDefinition
from parallax.core.document_codec._document import encode_managed_document
from parallax.core.metamodel import Multiplicity

__all__ = ["OMITTED", "document_cells", "encoded_document"]

OMITTED: Final = object()
"""The marker an omitted member's cell holds in :func:`document_cells`."""


def document_cells(shape: MemberShape, values: Mapping[str, object]) -> tuple[object, ...]:
    """The managed document ``values`` names by member, in its positional form
    over ``shape``, an omitted member :data:`OMITTED`."""
    return tuple(_cell(member, values.get(member.name, OMITTED)) for member in shape.members)


def _cell(member: ScalarDefinition | OccurrenceDefinition, value: object) -> object:
    if value is OMITTED or value is None or isinstance(member, ScalarDefinition):
        return value
    if member.multiplicity is Multiplicity.MANY:
        return tuple(
            document_cells(member.shape, element)
            for element in cast("Sequence[Mapping[str, object]]", value)
        )
    return document_cells(member.shape, cast("Mapping[str, object]", value))


def encoded_document(shape: MemberShape, values: Mapping[str, object]) -> FrozenMap[str, object]:
    """The managed document ``values`` names by member, encoded."""
    return encode_managed_document(shape, document_cells(shape, values), OMITTED)
