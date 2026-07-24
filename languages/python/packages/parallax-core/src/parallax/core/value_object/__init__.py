"""``parallax.core.value_object`` enforcement scope (m-value-object).

The recursive embedded-composite model: a top-level value object and all its
nested value objects (to arbitrary depth) map to one ``json`` document column.
This scope owns the shape invariants a declared composite must satisfy, resolves
a dotted access path against the declared structure, reports the leaf's neutral
type for literal typing, and answers whether a path crosses a
``multiplicity: many`` member — the fact that decides core's flat **any-element**
vs terminated **same-element** semantics. ``m-value-object`` depends on
``m-descriptor``, ``m-metamodel``, and ``m-model-formation``.

It contributes a Rule Set and no compiler: accepted occurrences are expanded
into path-identified Metadata by the mandatory Metadata Compiler, so there is no
Value Object facet to view. Path resolution walks that expanded Metadata through
its own nested lookups, so this scope keeps no second index of a composite's
members.
"""

from __future__ import annotations

from collections.abc import Sequence

from parallax.core.base import NeutralType
from parallax.core.metamodel import (
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
)
from parallax.core.value_object._rules import (
    CONTAINMENT_CYCLE,
    EMPTY,
    ISSUE_CODES,
    MANY_NULLABLE,
    RULE_SET,
    VALUE_OBJECT_MODULE,
    ValueObjectRuleSet,
    validate_value_objects,
)

__all__ = [
    "CONTAINMENT_CYCLE",
    "EMPTY",
    "ISSUE_CODES",
    "MANY_NULLABLE",
    "RULE_SET",
    "VALUE_OBJECT_MODULE",
    "Container",
    "ValueObjectError",
    "ValueObjectRuleSet",
    "crosses_many",
    "document_column",
    "leaf_type",
    "member",
    "resolve",
    "validate_value_objects",
]

# A value-object container: the top-level occurrence or any nested one. Both
# expose the same member lookups, so a walk never branches on which it holds.
Container = ValueObjectMetadata | NestedValueObjectMetadata


class ValueObjectError(ValueError):
    """A value-object access path does not resolve against the declared structure."""


def document_column(vo: ValueObjectMetadata) -> str:
    """The single structured-document column the whole composite is stored in."""
    return vo.storage.name


def member(
    container: Container, name: str
) -> ValueObjectAttributeMetadata | NestedValueObjectMetadata | None:
    """The direct child of ``container`` named ``name`` (attribute or nested VO).

    A scalar leaf and a nested occurrence never share a name inside one
    container, so the scalar lookup answering first is a shortcut rather than a
    precedence rule.
    """
    attribute = container.attribute(name)
    if attribute is not None:
        return attribute
    return container.value_object(name)


def resolve(vo: ValueObjectMetadata, path: Sequence[str]) -> ValueObjectAttributeMetadata:
    """Resolve a dotted access ``path`` (element-relative) to its leaf attribute.

    Every non-final segment must name a nested value object; the final segment
    must name a scalar attribute. Raises :class:`ValueObjectError` on an unknown
    segment or a path that stops on a nested value object rather than a leaf.
    """
    owner = vo.identity.path[-1]
    if not path:
        raise ValueObjectError(f"{owner}: empty value-object access path")
    container: Container = vo
    for index, segment in enumerate(path):
        is_last = index == len(path) - 1
        leaf = container.attribute(segment)
        if leaf is not None:
            if not is_last:
                raise ValueObjectError(
                    f"{owner}: {segment!r} is a scalar attribute but the path continues past it"
                )
            return leaf
        nested = container.value_object(segment)
        if nested is None:
            raise ValueObjectError(f"{owner}: unknown value-object segment {segment!r}")
        if is_last:
            raise ValueObjectError(
                f"{owner}: path ends on nested value object {segment!r}, not a scalar leaf"
            )
        container = nested
    raise ValueObjectError(f"{owner}: value-object path did not resolve")  # pragma: no cover


def leaf_type(vo: ValueObjectMetadata, path: Sequence[str]) -> NeutralType:
    """The neutral type of the leaf attribute reached by ``path``."""
    return resolve(vo, path).type


def crosses_many(vo: ValueObjectMetadata, path: Sequence[str]) -> bool:
    """Whether ``path`` traverses any ``multiplicity: many`` member.

    A flat predicate over such a path keeps core's **any-element** semantics
    (each predicate may be satisfied by a different element); a path confined to
    ``multiplicity: one`` members addresses a single embedded document.
    """
    if vo.multiplicity is Multiplicity.MANY:
        return True
    container: Container = vo
    for segment in path:
        found = container.value_object(segment)
        if found is None:
            break
        if found.multiplicity is Multiplicity.MANY:
            return True
        container = found
    return False
