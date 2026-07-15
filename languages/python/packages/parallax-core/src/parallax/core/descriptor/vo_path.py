"""Shared, error-neutral value-object path resolution (m-descriptor).

`m-op-algebra`'s nested-predicate validator and `m-sql`'s nested-predicate
lowering both walk a dotted `valueObject(.valueObject)*.attribute` path against
the SAME descriptor records (`m-value-object` "Materialization and navigation
contract"), independently, because the module DAG forbids either from
importing `m-value-object`'s own helpers (`m-op-algebra --> m-descriptor`,
`m-sql --> m-op-algebra --> m-descriptor`; neither depends on `m-value-object`).
Both callers, however, already depend on `m-descriptor` directly — so the
shared walk lives HERE rather than staying duplicated.

This module is **error-neutral**: it returns a resolution result or a
:class:`VoPathMiss` describing which segment failed and why, and never raises
for a model-level resolution failure. Each caller classifies a miss into its
own error vocabulary (`OperationRejectedError` naming a `rejectedRule` /
`SqlGenError` naming a lowering failure) and its own message text — this
module owns no message text and no exception type.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from parallax.core.descriptor.records import (
    Entity,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
)

__all__ = ["VoPathMiss", "find_value_object", "find_vo_member", "resolve_vo_leaf"]


def find_value_object(entity: Entity, name: str) -> ValueObject | None:
    """``entity``'s own top-level value object named ``name``, or ``None``."""
    for vo in entity.value_objects:
        if vo.name == name:
            return vo
    return None


def find_vo_member(
    container: ValueObject | NestedValueObject, name: str
) -> ValueObjectAttribute | NestedValueObject | None:
    """The scalar attribute or nested value object named ``name`` on ``container``."""
    for attribute in container.attributes:
        if attribute.name == name:
            return attribute
    for nested in container.value_objects:
        if nested.name == name:
            return nested
    return None


@dataclass(frozen=True, slots=True)
class VoPathMiss:
    """A dotted value-object path segment failed to resolve against a container.

    ``reason`` names which of the three ways a segment walk can fail:

    - ``"unknown-member"`` — ``segment`` names no declared member of the
      container at that point in the walk.
    - ``"scalar-continues"`` — ``segment`` resolved to a scalar attribute, but
      the path has further segments after it.
    - ``"ends-on-nested"`` — the path's last segment resolved to a nested value
      object, not a scalar leaf.
    """

    segment: str
    reason: Literal["unknown-member", "scalar-continues", "ends-on-nested"]


def resolve_vo_leaf(
    container: ValueObject | NestedValueObject, segments: Sequence[str]
) -> ValueObjectAttribute | VoPathMiss:
    """Walk dotted ``segments`` (non-empty) against ``container`` to a scalar leaf.

    ``container`` is any already-resolved starting point — a `Class.valueObject`
    reference's own top-level value object (the flat nested-predicate rules), or
    the TERMINAL value object a `nestedExists`/`nestedNotExists` `path` resolves
    to (the scoped `where` element-relative rules, `m-value-object` same-element
    semantics). Intermediate segments MUST resolve to a nested value object; the
    final segment MUST resolve to a scalar attribute — anything else is a
    :class:`VoPathMiss`, never an exception (this module is error-neutral).
    """
    scope: ValueObject | NestedValueObject = container
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        member = find_vo_member(scope, segment)
        if member is None:
            return VoPathMiss(segment, "unknown-member")
        if isinstance(member, ValueObjectAttribute):
            if not is_last:
                return VoPathMiss(segment, "scalar-continues")
            return member
        if is_last:
            return VoPathMiss(segment, "ends-on-nested")
        scope = member
    raise AssertionError("resolve_vo_leaf: `segments` must be non-empty")  # pragma: no cover
