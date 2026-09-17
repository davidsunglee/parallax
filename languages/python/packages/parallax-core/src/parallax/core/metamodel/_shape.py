"""Member-shape vocabulary derived from accepted Metadata (m-metamodel)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


class _OccurrenceSource(Protocol):
    @property
    def identity(self) -> _PathIdentity: ...
    @property
    def multiplicity(self) -> Multiplicity: ...
    @property
    def nullable(self) -> bool: ...
    @property
    def document_shape(self) -> MemberShape: ...


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
class MemberShape:
    """The applicable members of one document, in canonical emission order."""

    members: tuple[DocumentMember, ...]
    by_name: Mapping[str, DocumentMember] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        by_name: dict[str, DocumentMember] = {}
        for member in self.members:
            by_name.setdefault(member.name, member)
        object.__setattr__(
            self,
            "by_name",
            MappingProxyType(by_name),
        )

    @classmethod
    def of(
        cls,
        attributes: Sequence[_LeafSource],
        value_objects: Sequence[_OccurrenceSource],
    ) -> Self:
        """Compose leaves before occurrences, reusing each occurrence's held shape."""
        leaves: tuple[DocumentMember, ...] = tuple(
            Leaf(name=attribute.identity.name, type=attribute.type, nullable=attribute.nullable)
            for attribute in attributes
        )
        occurrences = tuple(
            Occurrence(
                name=value_object.identity.path[-1],
                multiplicity=value_object.multiplicity,
                nullable=value_object.nullable,
                shape=value_object.document_shape,
            )
            for value_object in value_objects
        )
        return cls(members=leaves + occurrences)

    def member(self, name: str) -> DocumentMember | None:
        """The member ``name`` names, or absent when the shape does not declare it."""
        return self.by_name.get(name)
