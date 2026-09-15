"""Document shape construction and presence (m-document-codec)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, Self

from parallax.core.metamodel import (
    AttributeMetadata,
    DocumentMember,
    DocumentShape,
    Leaf,
    NestedValueObjectMetadata,
    NestedValueObjectOccurrenceDeclaration,
    Occurrence,
    ValueObjectMetadata,
    ValueObjectShapeDeclaration,
)

__all__ = [
    "MISSING",
    "NULL",
    "DocumentMember",
    "DocumentShape",
    "ExplicitNull",
    "Leaf",
    "Missing",
    "Occurrence",
    "Presence",
    "Present",
    "entity_shape",
    "occurrence_shape",
    "resolve",
    "shape_of_declaration",
]


@dataclass(frozen=True, slots=True)
class Present:
    """A member that holds ``value``: a leaf's ``NeutralValue``, or an occurrence's
    own document."""

    value: object


class ExplicitNull:
    """A member written as JSON null, distinct from an absent one.

    Sameness is identity: :data:`NULL` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[ExplicitNull | None] = None

    def __new__(cls) -> ExplicitNull:
        if ExplicitNull._instance is None:
            ExplicitNull._instance = super().__new__(cls)
        return ExplicitNull._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("ExplicitNull admits one instance and therefore no subclass")

    def __repr__(self) -> str:
        return "NULL"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "NULL"


class Missing:
    """A member whose key the document does not carry.

    Sameness is identity: :data:`MISSING` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[Missing | None] = None

    def __new__(cls) -> Missing:
        if Missing._instance is None:
            Missing._instance = super().__new__(cls)
        return Missing._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("Missing admits one instance and therefore no subclass")

    def __repr__(self) -> str:
        return "MISSING"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "MISSING"


type Presence = Present | ExplicitNull | Missing
"""Classified against one member of a shape; the member's own kind fixes what a
:class:`Present` carries."""

NULL: Final[ExplicitNull] = ExplicitNull()
MISSING: Final[Missing] = Missing()


def shape_of_declaration(declaration: ValueObjectShapeDeclaration) -> DocumentShape:
    """The document shape of one reusable Value Object shape declaration.

    Leaves precede nested occurrences, matching the declaration's own two sequences.
    """
    leaves: tuple[DocumentMember, ...] = tuple(
        Leaf(name=attribute.name, type=attribute.type, nullable=attribute.nullable)
        for attribute in declaration.attributes
    )
    nested = tuple(map(_declared_occurrence, declaration.value_objects))
    return DocumentShape(members=leaves + nested)


def _declared_occurrence(nested: NestedValueObjectOccurrenceDeclaration) -> Occurrence:
    return Occurrence(
        name=nested.name,
        multiplicity=nested.multiplicity,
        nullable=nested.nullable,
        shape=shape_of_declaration(nested.shape),
    )


def occurrence_shape(container: ValueObjectMetadata | NestedValueObjectMetadata) -> DocumentShape:
    """The document shape held by one accepted Value Object occurrence."""
    return container.document_shape


def entity_shape(
    attributes: Sequence[AttributeMetadata],
    value_objects: Sequence[ValueObjectMetadata],
) -> DocumentShape:
    """One root document shape over the Entity members it is given.

    The Entity counterpart of :func:`occurrence_shape`: one root object holding
    the given attributes and value objects, each addressed by its canonical
    declared name, leaves before occurrences in the order given. This only unwinds
    their declarations into shape members.

    WHICH members is the CALLER's answer, because ``m-storage-layout``'s Member
    Placement decides residency and this module may not read a layout. A caller
    shaping a stored Structured Column passes that column's residents alone; one
    stating a layout-neutral rule over a whole row — the effective-change
    comparison, which a placement cannot change — passes every applicable member.
    """
    return DocumentShape.of(attributes, value_objects)


def resolve(shape: DocumentShape, path: Sequence[str]) -> DocumentMember:
    """The member ``path`` names, walking nested occurrences by name.

    A path naming no member of ``shape`` is a caller error rather than an absence, so
    this raises :class:`KeyError` instead of answering ``Missing``.
    """
    if not path:
        raise KeyError("a document path names at least one member")
    current = shape
    for name in path[:-1]:
        member = _named(current, path, name)
        if not isinstance(member, Occurrence):
            raise KeyError(f"{'.'.join(path)!r}: the path continues past the leaf {name!r}")
        current = member.shape
    return _named(current, path, path[-1])


def _named(shape: DocumentShape, path: Sequence[str], name: str) -> DocumentMember:
    member = shape.member(name)
    if member is None:
        raise KeyError(f"{'.'.join(path)!r}: {name!r} names no member of the shape")
    return member
