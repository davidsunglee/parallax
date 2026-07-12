"""Typed class-level access carriers (``Attr[T]`` / ``Rel[T]``).

The static-typing carrier is the annotation itself: an entity field declared
``Attr[T]`` is backed by a descriptor whose overloaded ``__get__`` returns a
reference object for **class** access (the seed of an operation predicate) and
the plain ``T`` for **instance** access, so strict Pyright sees both sides
without a plugin (the SQLAlchemy ``Mapped[T]`` pattern). ``Attr`` / ``Rel`` are
non-data descriptors, so a materialized instance's own ``__dict__`` value takes
precedence and instance access returns the stored value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import overload

__all__ = ["Attr", "AttributeRef", "Rel", "RelationshipRef"]


@dataclass(frozen=True, slots=True)
class AttributeRef:
    """A class-level reference to an entity attribute (``Entity.attribute``)."""

    entity: str
    attribute: str

    def __str__(self) -> str:
        return f"{self.entity}.{self.attribute}"


@dataclass(frozen=True, slots=True)
class RelationshipRef:
    """A class-level reference to an entity relationship (``Entity.relationship``)."""

    entity: str
    relationship: str

    def __str__(self) -> str:
        return f"{self.entity}.{self.relationship}"


class Attr[T]:
    """Typed attribute descriptor: class access → ``AttributeRef``, instance → ``T``."""

    __slots__ = ("_py_name", "_ref")

    def __init__(self, ref: AttributeRef, py_name: str) -> None:
        self._ref = ref
        self._py_name = py_name

    @overload
    def __get__(self, obj: None, _owner: type, /) -> AttributeRef: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> AttributeRef | T:
        if obj is None:
            return self._ref
        value: T = obj.__dict__[self._py_name]
        return value


class Rel[T]:
    """Typed relationship descriptor: class access → ``RelationshipRef``, instance → ``T``."""

    __slots__ = ("_py_name", "_ref")

    def __init__(self, ref: RelationshipRef, py_name: str) -> None:
        self._ref = ref
        self._py_name = py_name

    @overload
    def __get__(self, obj: None, _owner: type, /) -> RelationshipRef: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> RelationshipRef | T:
        if obj is None:
            return self._ref
        value: T = obj.__dict__[self._py_name]
        return value
