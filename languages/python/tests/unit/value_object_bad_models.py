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
