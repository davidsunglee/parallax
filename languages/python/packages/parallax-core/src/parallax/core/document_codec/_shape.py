"""Document shapes and presence (m-document-codec, "Shapes, documents, and values").

A :class:`DocumentShape` is the codec's own reading of accepted Metadata: canonical
member names, declared Neutral Types, multiplicity, and nullability, and nothing
physical. Two kinds of document reach it — a Value Object occurrence's own shape and
the applicable document shape of one Entity — and both are the same structure here,
which is what stops the two representations from drifting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core.base import NeutralType
from parallax.core.metamodel import (
    Multiplicity,
    NestedValueObjectMetadata,
    NestedValueObjectOccurrenceDeclaration,
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
    "occurrence_shape",
    "resolve",
    "shape_of_declaration",
]


@dataclass(frozen=True, slots=True)
class Leaf:
    """One scalar member of a document, spelled by its declared Neutral Type."""

    name: str
    type: NeutralType
    nullable: bool


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One nested Value Object member: an object for ``ONE``, an array for ``MANY``."""

    name: str
    multiplicity: Multiplicity
    nullable: bool
    shape: DocumentShape


type DocumentMember = Leaf | Occurrence
"""A document member is a scalar :class:`Leaf` or a nested :class:`Occurrence`; the
union is closed, so every path this module resolves ends at one of the two."""


@dataclass(frozen=True, slots=True)
class DocumentShape:
    """The applicable members of one document, in canonical order.

    Emission order is the member order held here, so one set of logical values always
    produces one document.
    """

    members: tuple[DocumentMember, ...]

    def member(self, name: str) -> DocumentMember | None:
        """The member ``name`` names, or absent when the shape does not declare it."""
        for member in self.members:
            if member.name == name:
                return member
        return None


@dataclass(frozen=True, slots=True)
class Present:
    """A member that holds ``value``: a leaf's ``NeutralValue``, or an occurrence's
    own document."""

    value: object


@dataclass(frozen=True, slots=True)
class ExplicitNull:
    """A member written as JSON null, distinct from an absent one."""


@dataclass(frozen=True, slots=True)
class Missing:
    """A member whose key the document does not carry."""


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
    """The document shape of one accepted Value Object occurrence's own composite.

    The Metadata counterpart of :func:`shape_of_declaration`: a compiled occurrence
    names its leaves and nested occurrences through identities rather than plain
    names, and this is the one place that difference is unwound.
    """
    leaves: tuple[DocumentMember, ...] = tuple(
        Leaf(name=attribute.identity.name, type=attribute.type, nullable=attribute.nullable)
        for attribute in container.attributes
    )
    return DocumentShape(members=leaves + tuple(map(_compiled_occurrence, container.value_objects)))


def _compiled_occurrence(nested: NestedValueObjectMetadata) -> Occurrence:
    return Occurrence(
        name=nested.identity.path[-1],
        multiplicity=nested.multiplicity,
        nullable=nested.nullable,
        shape=occurrence_shape(nested),
    )


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
