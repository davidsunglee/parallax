from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import islice
from types import MappingProxyType
from typing import Protocol, Self, cast, overload

from parallax.core.base import NeutralType
from parallax.core.metamodel._values import Multiplicity

__all__ = [
    "BoundShape",
    "MemberDefinition",
    "MemberShape",
    "OccurrenceDefinition",
    "ScalarDefinition",
]


class _NamedIdentity(Protocol):
    @property
    def name(self) -> str: ...


class _PathIdentity(Protocol):
    @property
    def path(self) -> Sequence[str]: ...


class _ScalarSource(Protocol):
    @property
    def identity(self) -> _NamedIdentity: ...
    @property
    def type(self) -> NeutralType: ...
    @property
    def nullable(self) -> bool: ...
    @property
    def multiplicity(self) -> Multiplicity: ...
    @property
    def definition(self) -> ScalarDefinition: ...


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
    def definition(self) -> OccurrenceDefinition: ...


@dataclass(frozen=True, slots=True)
class ScalarDefinition:
    """One scalar member of a document, spelled by its declared Neutral Type.

    ``type`` is the scalar element type under either multiplicity: a ``MANY``
    scalar holds an ordered, duplicate-preserving sequence of non-null values of
    that type and is itself never null, so a nullable ``MANY`` scalar raises
    :class:`ValueError`.
    """

    name: str
    type: NeutralType
    nullable: bool
    multiplicity: Multiplicity = Multiplicity.ONE

    def __post_init__(self) -> None:
        if self.nullable and self.multiplicity is Multiplicity.MANY:
            raise ValueError(f"{self.name}: a many leaf is never nullable")


@dataclass(frozen=True, slots=True)
class OccurrenceDefinition:
    """One nested Value Object member: an object for ``ONE``, an array for ``MANY``."""

    name: str
    multiplicity: Multiplicity
    nullable: bool
    shape: MemberShape


type MemberDefinition = ScalarDefinition | OccurrenceDefinition
"""A :class:`ScalarDefinition` or nested :class:`OccurrenceDefinition`; this union is closed."""


@dataclass(frozen=True, slots=True)
class _MembersByName(Mapping[str, MemberDefinition]):
    members: tuple[MemberDefinition, ...]
    positions: Mapping[str, int]

    def __getitem__(self, name: str) -> MemberDefinition:
        return self.members[self.positions[name]]

    def __iter__(self) -> Iterator[str]:
        return iter(self.positions)

    def __len__(self) -> int:
        return len(self.positions)


@dataclass(frozen=True, slots=True)
class MemberShape:
    """The applicable members of one document, in canonical emission order."""

    members: tuple[MemberDefinition, ...]
    _position_by_name: Mapping[str, int] = field(init=False, compare=False, repr=False)
    by_name: Mapping[str, MemberDefinition] = field(init=False, compare=False, repr=False)

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
        attributes: Sequence[_ScalarSource],
        value_objects: Sequence[_OccurrenceSource],
    ) -> Self:
        """Compose scalars before occurrences, reusing each occurrence's held shape."""
        scalars: tuple[MemberDefinition, ...] = tuple(
            attribute.definition for attribute in attributes
        )
        occurrences = tuple(value_object.definition for value_object in value_objects)
        return cls(members=scalars + occurrences)

    def position(self, name: str) -> int | None:
        """The canonical position ``name`` occupies, or absence on a miss."""
        return self._position_by_name.get(name)

    def member(self, name: str) -> MemberDefinition | None:
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

    Scalars precede occurrences, so ``scalar_count`` splits ``bindings`` into the
    ``scalars`` and ``occurrences`` windows. Each window shares the bindings
    tuple without copying it and compares equal to any sequence holding the
    same bindings in the same order.
    """

    shape: MemberShape
    bindings: tuple[L | O, ...]
    scalar_count: int
    scalars: Sequence[L] = field(init=False, repr=False, compare=False)
    occurrences: Sequence[O] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.shape.members) != len(self.bindings):
            raise ValueError("a bound shape aligns every shape member to one binding")
        if not 0 <= self.scalar_count <= len(self.bindings):
            raise ValueError("a bound shape counts its leaves within its bindings")
        object.__setattr__(self, "scalars", _BindingRange(self.bindings, 0, self.scalar_count))
        object.__setattr__(
            self,
            "occurrences",
            _BindingRange(self.bindings, self.scalar_count, len(self.bindings)),
        )

    def binding(self, name: str) -> L | O | None:
        """The binding aligned to the member ``name`` names, or absence on a miss."""
        position = self.shape.position(name)
        return None if position is None else self.bindings[position]

    def scalar(self, name: str) -> L | None:
        """The binding aligned to the scalar ``name`` names, absent for an occurrence."""
        position = self.shape.position(name)
        if position is None or not isinstance(self.shape.members[position], ScalarDefinition):
            return None
        return cast("L", self.bindings[position])

    def occurrence(self, name: str) -> O | None:
        """The binding aligned to the occurrence ``name`` names, absent for a scalar."""
        position = self.shape.position(name)
        if position is None or not isinstance(self.shape.members[position], OccurrenceDefinition):
            return None
        return cast("O", self.bindings[position])
