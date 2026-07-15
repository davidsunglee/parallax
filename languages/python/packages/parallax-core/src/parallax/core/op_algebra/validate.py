"""Model-aware operation validation (m-op-algebra, m-navigate, m-value-object).

A schema-valid operation can still be **structurally invalid** against a
specific metamodel: a `narrow` that broadens past the polymorphic position in
scope, a predicate that reaches a concrete-subtype attribute nobody in the
active position declares, a navigation / deep-fetch path aimed at a value
object rather than a relationship, or a `find()` rooted at a value object
rather than a queryable entity. `m-case-format`'s `rejected` case shape proves
these refusals happen **before any SQL is emitted** (resolved Q7); this module
is the single validator the corpus-facing conformance engine calls for the
`when.operation` rejected lane (COR-3 Phase 7 increment 1) and the one a
future idiomatic statement frontend calls at build time, so the two paths can
never drift into different refusal behavior.

Rule provenance:

- `narrow-outside-position` / `narrow-empty-effective-set` /
  `subtype-attribute-outside-narrow-scope` — `m-op-algebra` "Subtype narrowing"
  / "The four-step validation rule": a `narrow` node's resolved concrete set is
  clamped (intersected) against the **active polymorphic position** threaded
  through the read (the queried `targetEntity`, re-narrowed by every enclosing
  `narrow`), and a predicate referencing a concrete-subtype-declared attribute
  needs the active position narrowed to a compatible subtype.
- `narrow-outside-relationship-target` — `m-navigate` "Polymorphic navigation":
  a `narrow` inside a navigation filter's `op` (or a deep-fetch path segment's
  hop narrow) does **not** clamp; its `entity` MUST name the relationship
  target exactly, and its resolved `to` set MUST be a subset of the target's
  effective concrete set.
- `nested-path-first-segment-not-value-object` / `nested-path-unknown-member` /
  `nested-literal-type-mismatch` — `m-op-algebra` "Nested value-object
  predicates": a dotted `Class.valueObject(.valueObject)*.attribute` path MUST
  resolve against the entity's **declared** value-object structure, and a
  comparison/membership literal MUST match the leaf's declared neutral type.
- `deep-fetch-value-object-segment` / `navigate-value-object-target` /
  `find-root-value-object` — `m-value-object` "Materialization and navigation
  contract" (points 4 and 5): a value object carries no correlation columns
  and is never a navigation, deep-fetch, or `find()` root — it is reached only
  by value, through its owner.

DAG note: `m-op-algebra` depends only on `m-descriptor` and `m-inheritance`
(`modules.md`); it may **not** import `m-value-object` (the same constraint
`m-sql`'s `sql_gen/compile.py` already documents), so the value-object
structural checks below resolve paths directly against the raw
`parallax.core.descriptor` records rather than reusing
`parallax.core.value_object`'s helpers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import assert_never

from parallax.core.descriptor import (
    Entity,
    Metamodel,
    NestedValueObject,
    Relationship,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.core.inheritance import effective_concrete_subtypes
from parallax.core.op_algebra.nodes import (
    All,
    And,
    AsOf,
    AsOfRange,
    Between,
    Comparison,
    DeepFetch,
    Distinct,
    Exists,
    Group,
    History,
    Limit,
    Membership,
    Narrow,
    Navigate,
    NestedComparison,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    Operation,
    Or,
    OrderBy,
    PathSegment,
    Scalar,
    StringMatch,
)

__all__ = ["OperationRejectedError", "validate_operation"]


class OperationRejectedError(ValueError):
    """A schema-valid operation violates a model-aware rule and MUST be refused
    pre-SQL (`m-case-format` `rejected` cases). ``rule`` is the exact
    `then.rejectedRule` classification the closed vocabulary names.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


@dataclass(frozen=True, slots=True)
class _PositionScope:
    """The threaded polymorphic-position state (`m-op-algebra` four-step rule).

    ``effective`` is the active position's effective concrete-subtype set.
    ``relationship_target`` is set only while validating inside a navigation
    filter's `op` (`m-navigate`): a `narrow` encountered there does not clamp
    like a same-position narrow — its `entity` must equal this name exactly.
    """

    effective: frozenset[str]
    relationship_target: str | None = None


def validate_operation(target: str, op: Operation, meta: Metamodel) -> None:
    """Validate ``op`` against ``meta``, raising :class:`OperationRejectedError`.

    ``target`` is the read's queried root position — the `targetEntity` a
    normal read case authors (or, for a `when.operation` `rejected` case that
    carries none, the model-aware default `m-op-algebra` fixes: the
    inheritance family root, or the model's own single entity when it declares
    no inheritance family at all). It seeds the initial active position for
    the narrow / subtype-attribute checks; the value-object structural checks
    below resolve their own entity from each node's own `Class.member`
    reference and do not otherwise depend on ``target``.
    """
    scope = _PositionScope(effective=frozenset(effective_concrete_subtypes(meta, target)))
    _walk(op, meta, scope)


def _walk(op: Operation, meta: Metamodel, scope: _PositionScope) -> None:
    match op:
        case All() | NoneOp():
            return
        case (
            Comparison(attr=attr)
            | Between(attr=attr)
            | NullCheck(attr=attr)
            | StringMatch(attr=attr)
            | Membership(attr=attr)
        ):
            _check_attr_ref(attr, meta, scope)
        case NestedComparison():
            _check_nested_comparison(op, meta)
        case NestedMembership():
            _check_nested_membership(op, meta)
        case NestedNullCheck():
            _check_nested_null_check(op, meta)
        case NestedExists(path=path) | NestedNotExists(path=path):
            # The path is value-object-TERMINATED (ends at the object itself, not a
            # leaf). The optional `where` is element-relative (no `Class` prefix) —
            # a different addressing scheme the narrow/attribute position tracking
            # above does not apply to — so it is not walked here.
            _check_nested_vo_terminated(path, meta)
        case And(operands=operands) | Or(operands=operands):
            for operand in operands:
                _walk(operand, meta, scope)
        case (
            Not(operand=operand)
            | Group(operand=operand)
            | OrderBy(operand=operand)
            | Limit(operand=operand)
            | Distinct(operand=operand)
            | AsOf(operand=operand)
            | AsOfRange(operand=operand)
            | History(operand=operand)
        ):
            _walk(operand, meta, scope)
        case Narrow(entity=entity, to=to, operand=operand):
            new_scope = _validate_narrow(entity, to, scope, meta)
            _walk(operand, meta, new_scope)
        case Navigate(rel=rel, op=inner) | Exists(rel=rel, op=inner) | NotExists(rel=rel, op=inner):
            relationship = _resolve_relationship(
                rel, meta, wrong_kind_rule="navigate-value-object-target"
            )
            hop_scope = _PositionScope(
                effective=frozenset(effective_concrete_subtypes(meta, relationship.related_entity)),
                relationship_target=relationship.related_entity,
            )
            if inner is not None:
                _walk(inner, meta, hop_scope)
        case DeepFetch(operand=operand, paths=paths):
            _walk(operand, meta, scope)
            for path in paths:
                _check_deep_fetch_path(path, meta)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


# --------------------------------------------------------------------------- #
# Narrow / subtype-attribute position tracking (m-op-algebra x m-inheritance,  #
# m-navigate relationship scope).                                             #
# --------------------------------------------------------------------------- #
def _resolve_to_set(to: Sequence[str], meta: Metamodel) -> frozenset[str]:
    resolved: set[str] = set()
    for name in to:
        resolved.update(effective_concrete_subtypes(meta, name))
    return frozenset(resolved)


def _validate_narrow(
    entity: str, to: tuple[str, ...], scope: _PositionScope, meta: Metamodel
) -> _PositionScope:
    """The four-step validation rule (`m-op-algebra`), plus its relationship-scope
    carve-out (`m-navigate`, resolved Q10)."""
    if scope.relationship_target is not None:
        # Relationship scope does NOT clamp: `entity` MUST name the relationship
        # target exactly, never a broader or other position.
        if entity != scope.relationship_target:
            raise OperationRejectedError(
                "narrow-outside-relationship-target",
                f"a relationship-scope narrow's `entity` ({entity!r}) must name the "
                f"relationship target {scope.relationship_target!r} exactly (m-navigate); "
                "subtypes are reached only through `to`, never by naming a broader or "
                "other position",
            )
        resolved = _resolve_to_set(to, meta)
        if not resolved or not resolved <= scope.effective:
            raise OperationRejectedError(
                "narrow-outside-relationship-target",
                f"narrow.to {list(to)} resolves to {sorted(resolved)}, which is not a "
                f"non-empty subset of the relationship target's effective concrete set "
                f"{sorted(scope.effective)}",
            )
        return _PositionScope(effective=resolved)

    # Step 1: resolve `entity` and CLAMP (intersect) it with the active position —
    # a narrow can only ever constrain the active position, never broaden it.
    entity_resolved = frozenset(effective_concrete_subtypes(meta, entity))
    effective_position = entity_resolved & scope.effective
    # Steps 2-3: resolve each `to` entry, union, and deduplicate.
    resolved = _resolve_to_set(to, meta)
    # Step 4: accept iff the resolved set is non-empty AND a subset of the
    # effective position; it becomes the active position for `operand`.
    if not resolved:
        raise OperationRejectedError(
            "narrow-empty-effective-set",
            f"narrow.to {list(to)} resolves to the empty concrete-subtype set",
        )
    if not resolved <= effective_position:
        raise OperationRejectedError(
            "narrow-outside-position",
            f"narrow.to {sorted(resolved)} is not a subset of the active position "
            f"{sorted(effective_position)} (narrow.entity {entity!r} clamped against the "
            "position threaded into this node)",
        )
    return _PositionScope(effective=resolved)


def _check_attr_ref(attr_ref: str, meta: Metamodel, scope: _PositionScope) -> None:
    class_name, _, _attr_name = attr_ref.partition(".")
    entity = meta.by_name.get(class_name)
    if entity is None:
        if _is_value_object_name_anywhere(meta, class_name):
            raise OperationRejectedError(
                "find-root-value-object",
                f"{attr_ref!r} is rooted at the value object {class_name!r}, not a "
                "queryable entity; a value object has no identity or table and is "
                "queried only through its owner (m-value-object contract 5)",
            )
        raise ValueError(f"{attr_ref!r} names no declared entity or value object {class_name!r}")
    _check_subtype_attribute_scope(meta, entity, scope)


def _check_subtype_attribute_scope(meta: Metamodel, entity: Entity, scope: _PositionScope) -> None:
    if entity.inheritance is None:
        return
    own_effective = frozenset(effective_concrete_subtypes(meta, entity.name))
    if not scope.effective <= own_effective:
        raise OperationRejectedError(
            "subtype-attribute-outside-narrow-scope",
            f"{entity.name} is not available to every concrete in the active position "
            f"{sorted(scope.effective)}; narrow to {sorted(own_effective)} first",
        )


# --------------------------------------------------------------------------- #
# Navigation / deep-fetch relationship targets (m-value-object contract 4).    #
# --------------------------------------------------------------------------- #
def _resolve_relationship(rel_ref: str, meta: Metamodel, *, wrong_kind_rule: str) -> Relationship:
    class_name, _, member_name = rel_ref.partition(".")
    entity = meta.entity(class_name)
    for relationship in entity.relationships:
        if relationship.name == member_name:
            return relationship
    if _find_value_object(entity, member_name) is not None:
        raise OperationRejectedError(
            wrong_kind_rule,
            f"{rel_ref!r} names the value object {member_name!r}, not a relationship; a "
            "value object has no identity to correlate and materializes with its owner, "
            "never via a fetch level or semi-join (m-value-object contract 4)",
        )
    raise ValueError(f"{rel_ref!r} names no declared relationship on {entity.name}")


def _check_deep_fetch_path(path: tuple[PathSegment, ...], meta: Metamodel) -> None:
    for segment in path:
        relationship = _resolve_relationship(
            segment.rel, meta, wrong_kind_rule="deep-fetch-value-object-segment"
        )
        if segment.narrow:
            # A path narrow carries only `to` — the position is the hop's target,
            # implicitly (m-op-algebra `deepFetch` directive) — so only the subset
            # check applies here; there is no separate `entity` to mismatch.
            target_effective = frozenset(
                effective_concrete_subtypes(meta, relationship.related_entity)
            )
            resolved = _resolve_to_set(segment.narrow, meta)
            if not resolved or not resolved <= target_effective:
                raise OperationRejectedError(
                    "narrow-outside-relationship-target",
                    f"deep-fetch path narrow {list(segment.narrow)} resolves to "
                    f"{sorted(resolved)}, which is not a non-empty subset of "
                    f"{relationship.related_entity}'s effective concrete set "
                    f"{sorted(target_effective)}",
                )


# --------------------------------------------------------------------------- #
# Nested value-object predicates (m-op-algebra "Nested value-object            #
# predicates"; resolved inline against parallax.core.descriptor records — the  #
# DAG forbids m-op-algebra from importing m-value-object).                    #
# --------------------------------------------------------------------------- #
def _find_value_object(entity: Entity, name: str) -> ValueObject | None:
    for vo in entity.value_objects:
        if vo.name == name:
            return vo
    return None


def _is_value_object_name_anywhere(meta: Metamodel, name: str) -> bool:
    return any(_find_value_object(entity, name) is not None for entity in meta.entities)


def _member_of(
    container: ValueObject | NestedValueObject, name: str
) -> ValueObjectAttribute | NestedValueObject | None:
    for attribute in container.attributes:
        if attribute.name == name:
            return attribute
    for nested in container.value_objects:
        if nested.name == name:
            return nested
    return None


def _resolve_nested_leaf(path: str, meta: Metamodel) -> ValueObjectAttribute:
    """Resolve a `Class.valueObject(.valueObject)*.attribute` path to its leaf."""
    parts = path.split(".")
    if len(parts) < 3:
        raise OperationRejectedError(
            "nested-path-unknown-member",
            f"{path!r} needs at least Class.valueObject.attribute",
        )
    class_name, vo_name, *segments = parts
    entity = meta.entity(class_name)
    vo = _find_value_object(entity, vo_name)
    if vo is None:
        raise OperationRejectedError(
            "nested-path-first-segment-not-value-object",
            f"{class_name}.{vo_name} is not a declared value object on {class_name} "
            "(m-op-algebra nested-predicate resolver MUST)",
        )
    container: ValueObject | NestedValueObject = vo
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        member = _member_of(container, segment)
        if member is None:
            raise OperationRejectedError(
                "nested-path-unknown-member",
                f"{path!r}: {segment!r} names no declared member of {class_name}.{vo_name}",
            )
        if isinstance(member, ValueObjectAttribute):
            if not is_last:
                raise OperationRejectedError(
                    "nested-path-unknown-member",
                    f"{path!r}: {segment!r} is a scalar attribute but the path continues",
                )
            return member
        if is_last:
            raise OperationRejectedError(
                "nested-path-unknown-member",
                f"{path!r} ends on the nested value object {segment!r}, not a scalar leaf",
            )
        container = member
    raise OperationRejectedError(
        "nested-path-unknown-member", f"{path!r} has no leaf segment"
    )  # pragma: no cover


def _check_nested_vo_terminated(path: str, meta: Metamodel) -> None:
    """Resolve a `nestedExists`/`nestedNotExists` path (ends at a value object)."""
    parts = path.split(".")
    if len(parts) < 2:
        raise OperationRejectedError(
            "nested-path-unknown-member", f"{path!r} needs at least Class.valueObject"
        )
    class_name, vo_name, *segments = parts
    entity = meta.entity(class_name)
    vo = _find_value_object(entity, vo_name)
    if vo is None:
        raise OperationRejectedError(
            "nested-path-first-segment-not-value-object",
            f"{class_name}.{vo_name} is not a declared value object on {class_name}",
        )
    container: ValueObject | NestedValueObject = vo
    for segment in segments:
        member = _member_of(container, segment)
        if not isinstance(member, NestedValueObject):
            raise OperationRejectedError(
                "nested-path-unknown-member",
                f"{path!r}: {segment!r} does not name a nested value object",
            )
        container = member


def _literal_matches_type(value: Scalar, neutral_type: str) -> bool:
    """Whether a polymorphic operation literal matches a leaf's declared neutral type.

    `m-op-algebra`: "each type MUST match the leaf attribute's declared neutral
    type; a resolver MUST reject a type-mismatched literal." The algebra's
    literal vocabulary is `string` / `number` / `boolean` / `null`; every
    m-core neutral type maps onto that portable set.
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return neutral_type == "boolean"
    if neutral_type == "boolean":
        return False
    if neutral_type in ("int32", "int64"):
        return isinstance(value, int)
    if neutral_type in ("float32", "float64") or neutral_type.startswith("decimal"):
        return isinstance(value, (int, float))
    if neutral_type == "string":
        return isinstance(value, str)
    # date / time / timestamp / uuid / bytes / json ride the portable literal as a
    # string (the algebra's typed-literal vocabulary has no dedicated carrier for
    # them); not exercised by the in-slice corpus, so treated permissively here.
    return isinstance(value, str)


def _check_nested_comparison(node: NestedComparison, meta: Metamodel) -> None:
    leaf = _resolve_nested_leaf(node.path, meta)
    if not _literal_matches_type(node.value, leaf.type):
        raise OperationRejectedError(
            "nested-literal-type-mismatch",
            f"{node.path!r}: literal {node.value!r} does not match the leaf's declared "
            f"type {leaf.type!r} (m-op-algebra typed literals)",
        )


def _check_nested_membership(node: NestedMembership, meta: Metamodel) -> None:
    leaf = _resolve_nested_leaf(node.path, meta)
    for value in node.values:
        if not _literal_matches_type(value, leaf.type):
            raise OperationRejectedError(
                "nested-literal-type-mismatch",
                f"{node.path!r}: literal {value!r} does not match the leaf's declared "
                f"type {leaf.type!r} (m-op-algebra typed literals)",
            )


def _check_nested_null_check(node: NestedNullCheck, meta: Metamodel) -> None:
    _resolve_nested_leaf(node.path, meta)
