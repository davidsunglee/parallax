"""Member-shape vocabulary derived from accepted Metadata (m-metamodel)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, Self

from parallax.core.base import NeutralType
from parallax.core.metamodel._values import Multiplicity

__all__ = ["DocumentMember", "Leaf", "MemberShape", "Occurrence"]


class _NamedIdentity(Protocol):
    @property
    def name(self) -> str: ...


class _PathIdentity(Protocol):
    @property
    def path(self) -> Sequence[str]: ...


class _LeafSource(Protocol):
    @property
    def identity(self) -> _NamedIdentity: ...
    @property
    def type(self) -> NeutralType: ...
    @property
    def nullable(self) -> bool: ...
    @property
    def definition(self) -> Leaf: ...


class _OccurrenceSource(Protocol):
    @property
    def identity(self) -> _PathIdentity: ...
    @property
    def multiplicity(self) -> Multiplicity: ...
    @property
    def nullable(self) -> bool: ...
    @property
    def document_shape(self) -> MemberShape: ...
    @property
    def definition(self) -> Occurrence: ...


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
    shape: MemberShape


type DocumentMember = Leaf | Occurrence
"""A scalar :class:`Leaf` or nested :class:`Occurrence`; this union is closed."""


@dataclass(frozen=True, slots=True)
class _MembersByName(Mapping[str, DocumentMember]):
    members: tuple[DocumentMember, ...]
    positions: Mapping[str, int]

    def __getitem__(self, name: str) -> DocumentMember:
        return self.members[self.positions[name]]

    def __iter__(self) -> Iterator[str]:
        return iter(self.positions)

    def __len__(self) -> int:
        return len(self.positions)


@dataclass(frozen=True, slots=True)
class MemberShape:
    """The applicable members of one document, in canonical emission order."""

    members: tuple[DocumentMember, ...]
    _position_by_name: Mapping[str, int] = field(init=False, compare=False, repr=False)
    by_name: Mapping[str, DocumentMember] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        positions: dict[str, int] = {}
        for position, member in enumerate(self.members):
            positions.setdefault(member.name, position)
        position_by_name = MappingProxyType(positions)
        object.__setattr__(self, "_position_by_name", position_by_name)
        object.__setattr__(self, "by_name", _MembersByName(self.members, position_by_name))

    @classmethod
    def of(
        cls,
        attributes: Sequence[_LeafSource],
        value_objects: Sequence[_OccurrenceSource],
    ) -> Self:
        """Compose leaves before occurrences, reusing each occurrence's held shape."""
        leaves: tuple[DocumentMember, ...] = tuple(attribute.definition for attribute in attributes)
        occurrences = tuple(value_object.definition for value_object in value_objects)
        return cls(members=leaves + occurrences)

    def position(self, name: str) -> int | None:
        """The canonical position ``name`` occupies, or absence on a miss."""
        return self._position_by_name.get(name)

    def member(self, name: str) -> DocumentMember | None:
        """The member ``name`` names, or absent when the shape does not declare it."""
        position = self.position(name)
        return None if position is None else self.members[position]
