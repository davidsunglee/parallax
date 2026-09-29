from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, Self

from parallax.core.metamodel import (
    DocumentMember,
    Leaf,
    MemberShape,
    Occurrence,
    OccurrenceMetadata,
)

__all__ = [
    "MISSING",
    "NULL",
    "DocumentMember",
    "ExplicitNull",
    "Leaf",
    "MemberShape",
    "Missing",
    "Occurrence",
    "Presence",
    "Present",
    "occurrence_shape",
    "resolve",
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


def occurrence_shape(container: OccurrenceMetadata) -> MemberShape:
    """The document shape held by one accepted Value Object occurrence."""
    return container.document_shape


def resolve(shape: MemberShape, path: Sequence[str]) -> DocumentMember:
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


def _named(shape: MemberShape, path: Sequence[str], name: str) -> DocumentMember:
    member = shape.member(name)
    if member is None:
        raise KeyError(f"{'.'.join(path)!r}: {name!r} names no member of the shape")
    return member
