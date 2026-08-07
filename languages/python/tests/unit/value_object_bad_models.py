"""Deliberately mis-declared Value Object classes, built lazily.

This module omits ``from __future__ import annotations`` so the engine reads the
live annotation objects directly; each offending class is built inside a function
so importing the module never raises.
"""

from parallax.core import Attr, ValueObject, attr


def build_non_attr_annotated_value_object() -> type[ValueObject]:
    """A bare Python annotation where ``Attr[T]`` is the only spelling."""

    class BadAnnotation(ValueObject):
        plain: int

    return BadAnnotation


def build_entity_only_option_value_object() -> type[ValueObject]:
    """A Value Object member reaching for an Entity-only option."""

    class BadOption(ValueObject):
        label: Attr[str] = attr(max_length=8)

    return BadOption


def build_header_bearing_value_object() -> type[ValueObject]:
    """A Value Object class statement carrying a class-header keyword."""

    class BadHeader(ValueObject, table="nope"):
        label: Attr[str]

    return BadHeader


def build_framework_slot_shadowing_value_object() -> type[ValueObject]:
    """A method taking the name the framework renders a Value Object through.

    The destructive case: every serialization of a Value Object member reaches
    ``__parallax_document__``, so this body would have a write row and a nested
    predicate carry the author's object in place of the canonical document.
    """

    class BadBinding(ValueObject):
        label: Attr[str]

        def __parallax_document__(self) -> dict[str, object]:
            return {"shadowed": True}

    return BadBinding


def build_framework_slot_annotated_value_object() -> type[ValueObject]:
    """An annotation-only member under the framework's own name prefix.

    Annotated rather than bound, so it reaches the member walk instead of the
    class-body check — both paths answer to the one reservation.
    """

    class BadAnnotatedSlot(ValueObject):
        __parallax_lifecycle__: Attr[str]

    return BadAnnotatedSlot


def build_pydantic_namespace_value_object() -> type[ValueObject]:
    """An unannotated class-body binding in the ``model_*`` namespace."""

    class BadModelBinding(ValueObject):
        label: Attr[str]

        def model_copy(self, *, update: object = None, deep: bool = False) -> "BadModelBinding":
            return self

    return BadModelBinding
