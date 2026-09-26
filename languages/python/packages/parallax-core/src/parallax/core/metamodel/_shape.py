from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import islice
from types import MappingProxyType
from typing import Protocol, Self, cast, overload

from parallax.core.base import NeutralType
from parallax.core.metamodel._values import Multiplicity

__all__ = ["BoundShape", "DocumentMember", "Leaf", "MemberShape", "Occurrence"]


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


@dataclass(frozen=True, slots=True)
class _BindingRange[T](Sequence[T]):
    bindings: tuple[object, ...]
    start: int
    stop: int

    def __len__(self) -> int:
        return self.stop - self.start

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...

    def __getitem__(self, index: int | slice) -> T | Sequence[T]:
        if isinstance(index, slice):
            return cast("Sequence[T]", self.bindings[self.start : self.stop][index])
        position = index if index >= 0 else len(self) + index
        if position < 0 or position >= len(self):
            raise IndexError(index)
        return cast("T", self.bindings[self.start + position])

    def __iter__(self) -> Iterator[T]:
        # The Sequence mixin would index every element through Python-level
        # `__getitem__`; each case below walks the shared tuple in C without
        # copying the window.
        if self.start == self.stop:
            return iter(())
        bindings = cast("tuple[T, ...]", self.bindings)
        if self.start == 0 and self.stop == len(bindings):
            return iter(bindings)
        return islice(bindings, self.start, self.stop)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence):
            return False
        compared = cast("Sequence[object]", other)
        return len(self) == len(compared) and all(
            left == right for left, right in zip(self, compared, strict=True)
        )

    def __hash__(self) -> int:
        return hash(tuple(self))


@dataclass(frozen=True, slots=True)
class BoundShape[L, O]:
    """A document shape with one binding aligned to each of its members.

    Leaves precede occurrences, so ``leaf_count`` splits ``bindings`` into the
    ``leaves`` and ``occurrences`` windows. Each window shares the bindings
    tuple without copying it and compares equal to any sequence holding the
    same bindings in the same order.
    """

    shape: MemberShape
    bindings: tuple[L | O, ...]
    leaf_count: int
    leaves: Sequence[L] = field(init=False, repr=False, compare=False)
    occurrences: Sequence[O] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.shape.members) != len(self.bindings):
            raise ValueError("a bound shape aligns every shape member to one binding")
        if not 0 <= self.leaf_count <= len(self.bindings):
            raise ValueError("a bound shape counts its leaves within its bindings")
        object.__setattr__(self, "leaves", _BindingRange(self.bindings, 0, self.leaf_count))
        object.__setattr__(
            self, "occurrences", _BindingRange(self.bindings, self.leaf_count, len(self.bindings))
        )

    def binding(self, name: str) -> L | O | None:
        """The binding aligned to the member ``name`` names, or absence on a miss."""
        position = self.shape.position(name)
        return None if position is None else self.bindings[position]

    def leaf(self, name: str) -> L | None:
        """The binding aligned to the leaf ``name`` names, absent for an occurrence."""
        position = self.shape.position(name)
        if position is None or not isinstance(self.shape.members[position], Leaf):
            return None
        return cast("L", self.bindings[position])

    def occurrence(self, name: str) -> O | None:
        """The binding aligned to the occurrence ``name`` names, absent for a leaf."""
        position = self.shape.position(name)
        if position is None or not isinstance(self.shape.members[position], Occurrence):
            return None
        return cast("O", self.bindings[position])
