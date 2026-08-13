"""Model-aware Predicate validation (m-predicate, m-navigate, m-value-object).

A schema-valid predicate can still be **structurally invalid** against a
specific metamodel: a `narrow` that broadens past the polymorphic position in
scope, a predicate that reaches a concrete-subtype attribute nobody in the
active position declares, a navigation aimed at a value object rather than a
relationship, or a predicate rooted at a value object rather than a queryable
entity. It can also be invalid on its own authored terms, needing no model at
all: a range predicate whose two bounds are inverted. `m-case-format`'s
`rejected` case shape requires these refusals to happen **before any SQL is
emitted**. The query-wide clauses that carry a predicate — result narrowing,
ordering, Includes, Temporal Selection — are validated by ``m-object-query``,
which threads the position it resolves into this walk.

Rule provenance:

- `between-bounds-inverted` — `m-predicate` "Bound-ordering rule": a range
  predicate whose `lower` bound is strictly greater than its `upper` names an
  empty range, and is refused rather than lowered into a predicate that
  silently matches nothing. Bounds are compared by literal kind (two numbers or
  two strings), so the top-level `between` needs no model resolution at all. The
  two nested ranges share the identical rule, but resolve their subject and
  type-check both bounds FIRST, so a mistyped bound is named as a type mismatch
  rather than ordered as a raw literal.
- `narrow-outside-position` / `narrow-empty-effective-set` /
  `subtype-attribute-outside-narrow-scope` / `attribute-outside-active-position`
  — `m-predicate` "Subtype narrowing" / "The four-step validation rule": a
  `narrow` node's resolved concrete set is clamped (intersected) against the
  **active polymorphic position** threaded into it (the query's own `target`,
  narrowed by its `narrowTo` clause and by every enclosing `narrow`), and an
  attribute reference must be applicable to every concrete in that position. The
  two attribute rules partition one condition by whether the reference's Entity
  and the position share an inheritance family: inside one, narrowing is the
  remedy; outside it, nothing is.
- `reference-ambiguous-entity-name` — `m-predicate` "Entity spellings in a
  reference position": every reference position — an `attr`, a `rel`, a nested
  path's root, a `narrow`'s `to` entries — spells its Entity either canonically or BARE, and a
  bare local name two namespaces of the model declare names no single Entity and
  resolves nowhere. The canonical spelling of either of those two names one of them
  and resolves. It is the resolution half of the positional rules above, which
  presuppose a reference that resolved: those fire when a reference resolves to an
  Entity outside the position, this one when it resolves to more than one and
  therefore to none.
- `narrow-outside-relationship-target` — `m-navigate` "Polymorphic navigation":
  a `narrow` inside a navigation filter's `op` resolves its Subtype Selection
  inside the relationship target's effective concrete set.
- `nested-path-first-segment-not-value-object` / `nested-path-unknown-member` /
  `nested-literal-type-mismatch` — `m-predicate` "Nested value-object
  predicates": a dotted `Class.valueObject(.valueObject)*.attribute` path MUST
  resolve against the entity's **declared** value-object structure, and a
  comparison / range-bound / membership literal MUST match the leaf's declared
  neutral type.
- `nested-string-predicate-non-string-member` — `m-predicate` "Non-string-member
  rule": a nested string predicate reads text, so its resolved leaf MUST be a
  `String` member. It is a rule of its own, checked ahead of the typed-literal one,
  because the portable literal vocabulary carries a `Date` / `Time` / `Timestamp` /
  `Uuid` / `Bytes` value as a `str` — the literal rule alone would accept the very
  case this one exists to name.
- `navigate-value-object-target` / `find-root-value-object` — `m-value-object`
  "Materialization and navigation contract" (points 4 and 5): a value object
  carries no correlation columns and is never a navigation or query root — it is
  reached only by value, through its owner.

The active position's effective concrete-subtype sets come from the Inheritance
Facet; value-object paths resolve through the accepted Metadata's own O(1)
nested lookups (`entity.value_object(name)`, then `scope.attribute` /
`scope.value_object` per segment), classifying each miss at the call site.
Relationship targets come from the queried Entity's own identity-resolved
declarations — a defining declaration's join target, or a reverse declaration's
peer source — so this validator needs no relationship facet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import assert_never

from parallax.core import inheritance
from parallax.core.base import Boolean, Float32, Float64, Int32, Int64, NeutralType, String
from parallax.core.base import Decimal as DecimalType
from parallax.core.metamodel import (
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    NestedValueObjectMetadata,
    RelationshipDeclaration,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
    entity_by_name,
    split_reference,
)
from parallax.core.metamodel._states import ambiguous_entity_spellings
from parallax.core.predicate._nodes import (
    All,
    And,
    Between,
    Comparison,
    Exists,
    Group,
    Membership,
    Narrow,
    Navigate,
    NestedComparison,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    NestedRange,
    NestedStringMatch,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    Or,
    PredicateNode,
    Scalar,
    StringMatch,
)

__all__ = [
    "ModelRejectedError",
    "PositionScope",
    "check_attribute_reference",
    "effective_set",
    "referenced_entities",
    "relationship_target",
    "resolve_subtype_selection",
    "root_position",
    "validate_narrow",
    "validate_predicate",
]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata


def referenced_entities(op: PredicateNode) -> frozenset[str]:
    """The Entity spellings ``op`` names anywhere, exactly as authored — the Entity
    prefix of every attribute / nested-path / relationship reference, plus every
    ``narrow`` subtype alternative. A spelling may be bare or canonical; this
    resolves neither.

    A caller assembling a coherent model to validate ``op`` against needs every
    Entity the predicate reaches, not only the query's own root: a navigation
    names a target the root's family does not otherwise reach."""
    names: set[str] = set()
    _collect_entities(op, names)
    return frozenset(names)


def _class_of(reference: str) -> str:
    entity, _ = split_reference(reference)
    if entity is None:  # pragma: no cover - every position collected here bears an Entity
        raise ValueError(f"{reference!r} carries no Entity spelling")
    return entity


def _collect_entities(op: PredicateNode, names: set[str]) -> None:
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
            names.add(_class_of(attr))
        case (
            NestedComparison(path=path)
            | NestedRange(path=path)
            | NestedMembership(path=path)
            | NestedStringMatch(path=path)
            | NestedNullCheck(path=path)
        ):
            names.add(_class_of(path))
        case NestedExists(path=path) | NestedNotExists(path=path):
            names.add(_class_of(path))
        case And(operands=operands) | Or(operands=operands):
            for operand in operands:
                _collect_entities(operand, names)
        case Not(operand=operand) | Group(operand=operand):
            _collect_entities(operand, names)
        case Narrow(to=to, operand=operand):
            names.update(to)
            _collect_entities(operand, names)
        case Navigate(rel=rel, op=inner) | Exists(rel=rel, op=inner) | NotExists(rel=rel, op=inner):
            names.add(_class_of(rel))
            if inner is not None:
                _collect_entities(inner, names)


class ModelRejectedError(ValueError):
    """A schema-valid predicate or Object Query violates a model-aware rule and
    MUST be refused pre-SQL (`m-case-format` `rejected` cases). ``rule`` is the
    exact `then.rejectedRule` classification the closed vocabulary names.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


@dataclass(frozen=True, slots=True)
class PositionScope:
    """The threaded polymorphic-position state (`m-predicate` four-step rule).

    ``effective`` is the active position's effective concrete-subtype set, whose
    members are CANONICAL Entity spellings, so two
    Entities sharing a local name across namespaces stay distinct members of every
    subset test taken over it. ``relationship_target`` is the canonical name of the
    relationship target, set only while validating inside a navigation filter's
    `op` (`m-navigate`): a `narrow` encountered there does not clamp like a
    same-position narrow by selecting the relationship-target rejection rule.
    """

    effective: frozenset[str]
    relationship_target: str | None = None


def validate_predicate(
    root: EntityMetadata,
    op: PredicateNode,
    model: Metamodel,
    *,
    position: PositionScope | None = None,
) -> None:
    """Validate ``op`` against ``model``, raising :class:`ModelRejectedError`.

    ``root`` is the queried root position, already resolved to accepted Metadata
    by the caller — the ``target`` an Object Query names. It seeds the initial
    active position for the narrow checks and the positional attribute checks,
    which measure every attribute reference — an unrelated standalone Entity's as
    much as a subtype's — against that position; the value-object structural
    checks below resolve their own entity from each node's own `Class.member`
    reference and do not otherwise depend on ``root``.

    ``position`` overrides that seed with a position the caller has already
    resolved, which is how an Object Query threads its own result narrowing into
    the predicate it carries: whole-result narrowing is a query clause rather
    than an enclosing node, so nothing inside the predicate could derive it.
    """
    scope = (
        position if position is not None else PositionScope(effective=effective_set(model, root))
    )
    _walk(op, model, scope)


def root_position(model: Metamodel, root: EntityMetadata) -> PositionScope:
    """The active position a read starts from: ``root``'s effective concrete set."""
    return PositionScope(effective=effective_set(model, root))


def _walk(op: PredicateNode, model: Metamodel, scope: PositionScope) -> None:
    match op:
        case All() | NoneOp():
            return
        case Comparison(attr=attr) | StringMatch(attr=attr) | Membership(attr=attr):
            check_attribute_reference(attr, model, scope)
        case NullCheck(attr=attr):
            check_attribute_reference(attr, model, scope)
            _check_attribute_null_check(attr, model)
        case Between(attr=attr, lower=lower, upper=upper):
            check_attribute_reference(attr, model, scope)
            _check_bound_ordering(attr, lower, upper)
        case NestedComparison():
            _check_nested_comparison(op, model)
        case NestedRange():
            _check_nested_range(op, model)
        case NestedMembership():
            _check_nested_membership(op, model)
        case NestedStringMatch():
            _check_nested_string(op, model)
        case NestedNullCheck():
            _check_nested_null_check(op, model)
        case NestedExists(path=path, where=where) | NestedNotExists(path=path, where=where):
            # The path is value-object-TERMINATED (ends at the object itself, not a
            # leaf). The optional `where` is element-relative (no `Class` prefix) —
            # a different addressing scheme the narrow/attribute position tracking
            # above does not apply to — so it is validated against the TERMINAL
            # value-object descriptor `path` resolves to, not walked by `_walk`.
            container = _check_nested_vo_terminated(path, model)
            if where is not None:
                _check_element_predicate(where, container)
        case And(operands=operands) | Or(operands=operands):
            for operand in operands:
                _walk(operand, model, scope)
        case Not(operand=operand) | Group(operand=operand):
            _walk(operand, model, scope)
        case Narrow(to=to, operand=operand):
            new_scope = validate_narrow(to, scope, model)
            _walk(operand, model, new_scope)
        case Navigate(rel=rel, op=inner) | Exists(rel=rel, op=inner) | NotExists(rel=rel, op=inner):
            target = relationship_target(rel, model, wrong_kind_rule="navigate-value-object-target")
            hop_scope = PositionScope(
                effective=effective_set(model, target),
                relationship_target=target.identity.canonical,
            )
            if inner is not None:
                _walk(inner, model, hop_scope)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


# --------------------------------------------------------------------------- #
# Range bound ordering (m-predicate "Bound-ordering rule").                  #
# --------------------------------------------------------------------------- #
def _bounds_inverted(lower: Scalar, upper: Scalar) -> bool:
    """Whether a range's ``lower`` bound is strictly greater than its ``upper``.

    Bounds are compared by LITERAL KIND rather than by the subject's resolved
    type: only two numbers or two strings are ordered against each other, and a
    differing pair or a ``null`` bound is skipped rather than guessed. A ``bool``
    is its own literal kind — never a number — even though Python's ``bool``
    subclasses ``int``. Equal bounds name the single-value range and are never
    inverted.
    """
    if isinstance(lower, bool) or isinstance(upper, bool):
        return False
    if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
        return lower > upper
    if isinstance(lower, str) and isinstance(upper, str):
        return lower > upper
    return False


def _check_bound_ordering(subject: str, lower: Scalar, upper: Scalar) -> None:
    """Reject a range predicate over ``subject`` whose two bounds are inverted."""
    if _bounds_inverted(lower, upper):
        raise ModelRejectedError(
            "between-bounds-inverted",
            f"{subject!r}: lower bound {lower!r} is greater than upper bound {upper!r}, "
            "so the range is empty and no row can satisfy it (m-predicate bound ordering)",
        )


# --------------------------------------------------------------------------- #
# Entity / position resolution.                                               #
# --------------------------------------------------------------------------- #
def _lookup_entity(model: Metamodel, name: str) -> EntityMetadata | None:
    """The accepted Metadata a bare-or-canonical Entity spelling names, or
    absence, over the authored `Class` prefix of a predicate reference —
    :func:`~parallax.core.metamodel.entity_by_name`'s ambiguity-rejecting rule,
    so an ambiguous bare name is a miss rather than a silent first match."""
    return entity_by_name(model, name)


def _ambiguous_reference(
    model: Metamodel, reference: str, class_name: str
) -> ModelRejectedError | None:
    """The `reference-ambiguous-entity-name` rejection ``reference`` earns when
    ``class_name`` is a bare local spelling two namespaces of ``model`` share, or
    absence when it names at most one Entity.

    A bare spelling carries no namespace to select by, so a local name two
    namespaces declare names no single Entity:
    :func:`~parallax.core.metamodel.entity_by_name` answers it with a miss rather
    than a silent first match, and the refusal names the canonical spellings that
    would resolve. Both Entities stay declarable and stay reachable — through the
    canonical spelling this refusal reports, or through any position that names
    them unambiguously — so the reference is refused, never the declaration.
    """
    canonical = ambiguous_entity_spellings(model, class_name)
    if not canonical:
        return None
    return ModelRejectedError(
        "reference-ambiguous-entity-name",
        f"{reference!r}: the bare Entity spelling {class_name!r} is shared by {list(canonical)}, "
        "so it names no single Entity in this model and the reference resolves nowhere "
        "(m-predicate reference resolution)",
    )


def _check_reference_entity_name(model: Metamodel, reference: str, class_name: str) -> None:
    """Refuse ``reference`` if its Entity spelling names more than one Entity.

    Used at positions that otherwise tolerate a miss: a `narrow`'s `to` entries
    collapse an unresolved name into the empty set, which the narrow
    rules then classify. Asking here names an ambiguous spelling as the resolution
    failure it is, rather than as the narrow rule its silence would produce.
    """
    ambiguous = _ambiguous_reference(model, reference, class_name)
    if ambiguous is not None:
        raise ambiguous


def _unresolved_reference(model: Metamodel, reference: str, class_name: str) -> ValueError:
    """The error a reference whose Entity spelling resolves to nothing raises.

    Two unrelated failures share that miss: a spelling more than one Entity answers
    to is the classified `reference-ambiguous-entity-name` rejection, while a
    spelling no Entity answers to at all is an authoring error with no rejected-rule
    classification of its own.
    """
    return _ambiguous_reference(model, reference, class_name) or ValueError(
        f"{reference!r} names no declared entity or value object {class_name!r}"
    )


def effective_set(model: Metamodel, entity: EntityMetadata) -> frozenset[str]:
    """``entity``'s effective concrete-subtype set: itself for a standalone Entity,
    else its family view's concrete descendants.

    Members are CANONICAL spellings, so two Entities sharing a local name across
    namespaces stay distinct members of the sets every positional comparison here
    is a subset test over. The authored spelling a reference or a `to` entry uses
    is resolved to its Entity first, so the canonical form is an internal
    normalization rather than a requirement on the wire.
    """
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return frozenset({entity.identity.canonical})
    return frozenset(identity.canonical for identity in view.concrete_subtypes)


def _family_set(model: Metamodel, entity: EntityMetadata) -> frozenset[str]:
    """The effective concrete-subtype set of ``entity``'s whole inheritance family
    — every position a `narrow` could bring ``entity``'s members into scope from.

    A standalone Entity's family is itself, so this equals its effective set and
    the two positional rules stay distinguishable for it.
    """
    view = inheritance.view(model).entity(entity.identity)
    root = None if view is None else model.entity(view.root)
    if root is None:  # pragma: no cover - the facet covers every accepted Entity
        return effective_set(model, entity)
    return effective_set(model, root)


def resolve_subtype_selection(to: Sequence[str], model: Metamodel) -> frozenset[str]:
    """Resolve one Subtype Selection to its effective concrete set and enforce its
    construction contract (no duplicate and no overlapping alternative).

    Exported for the query clauses that carry the same shared value — result
    narrowing and an Include Path's two selections — so all four positions
    resolve one way.
    """
    resolved_alternatives: list[tuple[str, str, frozenset[str]]] = []
    for name in to:
        entity = _lookup_entity(model, name)
        if entity is None:
            _check_reference_entity_name(model, name, name)
            resolved_alternatives.append((name, name, frozenset()))
        else:
            resolved_alternatives.append(
                (name, entity.identity.canonical, effective_set(model, entity))
            )

    seen_identities: set[str] = set()
    for name, identity, _effective in resolved_alternatives:
        if identity in seen_identities:
            raise ModelRejectedError(
                "subtype-selection-duplicate-alternative",
                f"Subtype Selection repeats alternative {name!r}",
            )
        seen_identities.add(identity)

    resolved: set[str] = set()
    alternatives: list[tuple[str, frozenset[str]]] = []
    for name, _identity, effective in resolved_alternatives:
        for previous_name, previous_effective in alternatives:
            overlap = effective & previous_effective
            if overlap:
                raise ModelRejectedError(
                    "subtype-selection-overlapping-alternatives",
                    f"Subtype Selection alternatives {previous_name!r} and {name!r} "
                    f"overlap at {sorted(overlap)}",
                )
        alternatives.append((name, effective))
        resolved.update(effective)
    return frozenset(resolved)


# --------------------------------------------------------------------------- #
# Narrow / subtype-attribute position tracking (m-predicate x m-inheritance,  #
# m-navigate relationship scope).                                             #
# --------------------------------------------------------------------------- #
def validate_narrow(to: tuple[str, ...], scope: PositionScope, model: Metamodel) -> PositionScope:
    """Resolve a Subtype Selection inside the position supplied by context, and
    answer the narrowed position.

    Exported so an Object Query's own ``narrowTo`` clause resolves by the same
    rule the Predicate-scoped node does — the only difference being which
    position each is measured against.
    """
    resolved = resolve_subtype_selection(to, model)
    if not resolved:
        raise ModelRejectedError(
            "narrow-empty-effective-set",
            f"narrow.to {list(to)} resolves to the empty concrete-subtype set",
        )
    if scope.relationship_target is not None:
        if not resolved <= scope.effective:
            raise ModelRejectedError(
                "narrow-outside-relationship-target",
                f"narrow.to {list(to)} resolves to {sorted(resolved)}, which is not a "
                f"subset of the relationship target's effective concrete set "
                f"{sorted(scope.effective)}",
            )
        return PositionScope(effective=resolved)

    if not resolved <= scope.effective:
        raise ModelRejectedError(
            "narrow-outside-position",
            f"narrow.to {sorted(resolved)} is not a subset of the active position "
            f"{sorted(scope.effective)} threaded into this node",
        )
    return PositionScope(effective=resolved)


def check_attribute_reference(attr_ref: str, model: Metamodel, scope: PositionScope) -> None:
    """Resolve one ``Class.attribute`` reference and check it against ``scope``.

    Exported so a query clause that addresses an attribute outside any predicate
    — a Sort Key over the result position — meets the same rule the predicate's
    own references do, rather than a second copy of it.
    """
    class_name, _, _attr_name = attr_ref.rpartition(".")
    entity = _lookup_entity(model, class_name)
    if entity is None:
        if _is_value_object_name_anywhere(model, class_name):
            raise ModelRejectedError(
                "find-root-value-object",
                f"{attr_ref!r} is rooted at the value object {class_name!r}, not a "
                "queryable entity; a value object has no identity or table and is "
                "queried only through its owner (m-value-object contract 5)",
            )
        raise _unresolved_reference(model, attr_ref, class_name)
    _check_attribute_position(model, entity, scope)


def _check_attribute_null_check(attr_ref: str, model: Metamodel) -> None:
    class_name, _, attr_name = attr_ref.rpartition(".")
    entity = _lookup_entity(model, class_name)
    if entity is None:  # pragma: no cover - check_attribute_reference resolves this first
        raise AssertionError("a null-checked attribute reference has no resolved Entity")
    position = inheritance.view(model).entity(entity.identity)
    attribute = (
        None if position is None else position.applicable_attribute(attr_name)
    ) or entity.attribute(attr_name)
    if attribute is not None and not attribute.nullable:
        raise ModelRejectedError(
            "null-check-non-nullable-member",
            f"{attr_ref!r}: isNull/isNotNull is invalid for a non-nullable member "
            "(m-predicate null-check validity)",
        )


def _check_attribute_position(
    model: Metamodel, entity: EntityMetadata, scope: PositionScope
) -> None:
    """The positional rule: an attribute reference MUST be applicable to every
    concrete in the active position.

    The subset test is the whole rule and generalizes to a standalone Entity,
    whose effective set is itself. Only the classification splits, on whether a
    `narrow` could ever be the remedy: within the reference's own inheritance
    family it can, and outside it nothing can.
    """
    own_effective = effective_set(model, entity)
    if scope.effective <= own_effective:
        return
    if scope.effective <= _family_set(model, entity):
        raise ModelRejectedError(
            "subtype-attribute-outside-narrow-scope",
            f"{entity.identity.canonical} is not available to every concrete in the active "
            f"position {sorted(scope.effective)}; narrow to {sorted(own_effective)} first",
        )
    raise ModelRejectedError(
        "attribute-outside-active-position",
        f"{entity.identity.canonical} shares no inheritance family with the active position "
        f"{sorted(scope.effective)}, so no narrow makes its attributes addressable here",
    )


# --------------------------------------------------------------------------- #
# Navigation / deep-fetch relationship targets (m-value-object contract 4).    #
# --------------------------------------------------------------------------- #
def _declaration_target(declaration: RelationshipDeclaration) -> EntityIdentity:
    """The Entity a declared relationship navigates to: a defining declaration's
    join target, or a reverse declaration's peer source (the reverse direction
    points back at the Entity the peer was declared on)."""
    if isinstance(declaration, DefiningRelationshipDeclaration):
        return declaration.join.target.entity
    return declaration.reverse_of.source_entity


def relationship_target(rel_ref: str, model: Metamodel, *, wrong_kind_rule: str) -> EntityMetadata:
    class_name, _, member_name = rel_ref.rpartition(".")
    entity = _lookup_entity(model, class_name)
    if entity is None:
        raise _unresolved_reference(model, rel_ref, class_name)
    declaration = entity.relationship(member_name)
    if declaration is not None:
        target = model.entity(_declaration_target(declaration))
        if target is None:  # pragma: no cover - a resolved declaration names a declared Entity
            raise ValueError(f"{rel_ref!r} names a relationship whose target is undeclared")
        return target
    if entity.value_object(member_name) is not None:
        raise ModelRejectedError(
            wrong_kind_rule,
            f"{rel_ref!r} names the value object {member_name!r}, not a relationship; a "
            "value object has no identity to correlate and materializes with its owner, "
            "never via a fetch level or semi-join (m-value-object contract 4)",
        )
    raise ValueError(f"{rel_ref!r} names no declared relationship on {entity.identity.name}")


# --------------------------------------------------------------------------- #
# Nested value-object predicates (m-predicate "Nested value-object            #
# predicates"), resolved through the accepted Metadata's own O(1) nested       #
# lookups — the value-object structural checks classify each miss at the call  #
# site, so m-predicate needs no m-value-object dependency.                    #
# --------------------------------------------------------------------------- #
def _is_value_object_name_anywhere(model: Metamodel, name: str) -> bool:
    return any(entity.value_object(name) is not None for entity in model.entities)


def _resolve_leaf(
    path: str, container: _VoContainer, segments: Sequence[str]
) -> ValueObjectAttributeMetadata:
    """Walk dotted ``segments`` (non-empty) against ``container`` to a scalar leaf,
    classifying the three ways a path fails: an undeclared segment, a scalar the
    path continues past, and a nested object the path ends on."""
    scope: _VoContainer = container
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        attribute = scope.attribute(segment)
        if attribute is not None:
            if not is_last:
                raise ModelRejectedError(
                    "nested-path-unknown-member",
                    f"{path!r}: {segment!r} is a scalar attribute but the path continues",
                )
            return attribute
        nested = scope.value_object(segment)
        if nested is None:
            raise ModelRejectedError(
                "nested-path-unknown-member",
                f"{path!r}: {segment!r} names no declared member",
            )
        if is_last:
            raise ModelRejectedError(
                "nested-path-unknown-member",
                f"{path!r} ends on the nested value object {segment!r}, not a scalar leaf",
            )
        scope = nested
    raise AssertionError("_resolve_leaf: `segments` must be non-empty")  # pragma: no cover


def _resolve_nested_leaf(path: str, model: Metamodel) -> ValueObjectAttributeMetadata:
    """Resolve an `<Entity>.valueObject(.valueObject)*.attribute` path to its leaf."""
    class_name, members = split_reference(path)
    if class_name is None or len(members) < 2:
        raise ModelRejectedError(
            "nested-path-unknown-member",
            f"{path!r} needs at least Class.valueObject.attribute",
        )
    vo_name, *segments = members
    entity = _lookup_entity(model, class_name)
    if entity is None:
        raise _unresolved_reference(model, path, class_name)
    position = inheritance.view(model).entity(entity.identity)
    vo = (
        None if position is None else position.applicable_value_object(vo_name)
    ) or entity.value_object(vo_name)
    if vo is None:
        raise ModelRejectedError(
            "nested-path-first-segment-not-value-object",
            f"{class_name}.{vo_name} is not a declared value object on {class_name} "
            "(m-predicate nested-predicate resolver MUST)",
        )
    return _resolve_leaf(path, vo, segments)


def _resolve_element_leaf(container: _VoContainer, path: str) -> ValueObjectAttributeMetadata:
    """Resolve an element-relative path (`type`, `geo.country`) to its leaf.

    ``container`` is the TERMINAL value-object descriptor a `nestedExists`/
    `nestedNotExists` `path` resolves to (`_check_nested_vo_terminated`); the
    scoped `where`'s own paths are relative to that SAME element (`m-value-object`
    same-element semantics), never re-prefixed with `Class.valueObject`.
    """
    return _resolve_leaf(path, container, path.split("."))


def _check_nested_vo_terminated(path: str, model: Metamodel) -> _VoContainer:
    """Resolve a `nestedExists`/`nestedNotExists` path (ends at a value object),
    returning the TERMINAL value-object descriptor — the same-element scope an
    optional `where` predicate's element-relative members resolve against.
    """
    class_name, members = split_reference(path)
    if class_name is None or not members:
        raise ModelRejectedError(
            "nested-path-unknown-member", f"{path!r} needs at least Class.valueObject"
        )
    vo_name, *segments = members
    entity = _lookup_entity(model, class_name)
    if entity is None:
        raise _unresolved_reference(model, path, class_name)
    position = inheritance.view(model).entity(entity.identity)
    vo = (
        None if position is None else position.applicable_value_object(vo_name)
    ) or entity.value_object(vo_name)
    if vo is None:
        raise ModelRejectedError(
            "nested-path-first-segment-not-value-object",
            f"{class_name}.{vo_name} is not a declared value object on {class_name}",
        )
    container: _VoContainer = vo
    for segment in segments:
        member = container.value_object(segment)
        if member is None:
            raise ModelRejectedError(
                "nested-path-unknown-member",
                f"{path!r}: {segment!r} does not name a nested value object",
            )
        container = member
    return container


def _literal_matches_type(value: Scalar, neutral_type: NeutralType) -> bool:
    """Whether a polymorphic predicate literal matches a leaf's declared neutral type.

    `m-predicate`: "each type MUST match the leaf attribute's declared neutral
    type; a resolver MUST reject a type-mismatched literal." The algebra's
    literal vocabulary is `string` / `number` / `boolean` / `null`; every
    m-core neutral type maps onto that portable set.
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return isinstance(neutral_type, Boolean)
    if isinstance(neutral_type, Boolean):
        return False
    if isinstance(neutral_type, (Int32, Int64)):
        return isinstance(value, int)
    if isinstance(neutral_type, (Float32, Float64, DecimalType)):
        return isinstance(value, (int, float))
    if isinstance(neutral_type, String):
        return isinstance(value, str)
    # date / time / timestamp / uuid / bytes / json ride the portable literal as a
    # string (the algebra's typed-literal vocabulary has no dedicated carrier for
    # them); not exercised by the in-slice corpus, so treated permissively here.
    return isinstance(value, str)


def _check_typed_literal(path: str, value: Scalar, leaf: ValueObjectAttributeMetadata) -> None:
    """Reject ``value`` if it does not match ``leaf``'s declared neutral type.

    Shared by the flat nested rules and the scoped element-relative rules
    inside a `nestedExists`/`nestedNotExists` `where` — the same
    `nested-literal-type-mismatch` check, only the leaf's resolution differs.
    """
    if not _literal_matches_type(value, leaf.type):
        raise ModelRejectedError(
            "nested-literal-type-mismatch",
            f"{path!r}: literal {value!r} does not match the leaf's declared "
            f"type {leaf.type!r} (m-predicate typed literals)",
        )


def _check_nested_comparison(node: NestedComparison, model: Metamodel) -> None:
    leaf = _resolve_nested_leaf(node.path, model)
    _check_typed_literal(node.path, node.value, leaf)


def _check_range_bounds(node: NestedRange, leaf: ValueObjectAttributeMetadata) -> None:
    """A nested range's bound checks in the order `m-predicate` fixes: both typed
    bounds, then the bound ordering — the path having already resolved ``leaf``.

    Shared by both nested scopes, so the order is stated once. Ordering the bounds
    LAST is what makes a mistyped bound report the type mismatch rather than an
    accidental inversion between two literals of unrelated kinds.
    """
    _check_typed_literal(node.path, node.lower, leaf)
    _check_typed_literal(node.path, node.upper, leaf)
    _check_bound_ordering(node.path, node.lower, node.upper)


def _check_nested_range(node: NestedRange, model: Metamodel) -> None:
    _check_range_bounds(node, _resolve_nested_leaf(node.path, model))


def _check_nested_membership(node: NestedMembership, model: Metamodel) -> None:
    leaf = _resolve_nested_leaf(node.path, model)
    for value in node.values:
        _check_typed_literal(node.path, value, leaf)


def _check_string_member(path: str, leaf: ValueObjectAttributeMetadata) -> None:
    """Reject a string predicate whose resolved leaf is not a ``String`` member.

    Shared by both nested scopes, and deliberately NOT expressed through
    :func:`_literal_matches_type`: that function reads a `Date` / `Time` /
    `Timestamp` / `Uuid` / `Bytes` leaf permissively as a `str`, so the literal rule
    would accept a string predicate against exactly the members this one rejects.
    """
    if not isinstance(leaf.type, String):
        raise ModelRejectedError(
            "nested-string-predicate-non-string-member",
            f"{path!r}: a string predicate reads text, but the member's declared type is "
            f"{leaf.type!r} (m-predicate non-string-member rule)",
        )


def _check_nested_string(node: NestedStringMatch, model: Metamodel) -> None:
    """A nested string predicate's two checks, in the order `m-predicate` fixes:
    the resolved member's own type, then the literal's."""
    leaf = _resolve_nested_leaf(node.path, model)
    _check_string_member(node.path, leaf)
    _check_typed_literal(node.path, node.value, leaf)


def _check_nested_null_check(node: NestedNullCheck, model: Metamodel) -> None:
    leaf = _resolve_nested_leaf(node.path, model)
    _require_nullable_null_check(node.path, leaf.nullable)


# --------------------------------------------------------------------------- #
# Scoped `where` inside nestedExists/nestedNotExists (m-value-object          #
# same-element semantics; the serde's `elementPredicate` grammar admits only  #
# the nested*-family + boolean combinators here, element-relative paths).     #
# --------------------------------------------------------------------------- #
def _check_element_comparison(node: NestedComparison, container: _VoContainer) -> None:
    leaf = _resolve_element_leaf(container, node.path)
    _check_typed_literal(node.path, node.value, leaf)


def _check_element_range(node: NestedRange, container: _VoContainer) -> None:
    _check_range_bounds(node, _resolve_element_leaf(container, node.path))


def _check_element_membership(node: NestedMembership, container: _VoContainer) -> None:
    leaf = _resolve_element_leaf(container, node.path)
    for value in node.values:
        _check_typed_literal(node.path, value, leaf)


def _check_element_string(node: NestedStringMatch, container: _VoContainer) -> None:
    leaf = _resolve_element_leaf(container, node.path)
    _check_string_member(node.path, leaf)
    _check_typed_literal(node.path, node.value, leaf)


def _check_element_predicate(op: PredicateNode, container: _VoContainer) -> None:
    """Validate a `nestedExists`/`nestedNotExists` `where` against ``container``
    — the TERMINAL value-object descriptor its `path` resolves to.

    ``op`` is assumed schema-valid (this module's own precondition): the
    `elementPredicate` grammar (`predicate.schema.json`) admits only the
    nested*-family and boolean combinators here, so this dispatch does not
    need to re-derive that restriction — only resolve each element-relative
    reference and typed literal against the same element (m-value-object).
    """
    match op:
        case NestedComparison():
            _check_element_comparison(op, container)
        case NestedRange():
            _check_element_range(op, container)
        case NestedMembership():
            _check_element_membership(op, container)
        case NestedStringMatch():
            _check_element_string(op, container)
        case NestedNullCheck(path=path):
            leaf = _resolve_element_leaf(container, path)
            _require_nullable_null_check(path, leaf.nullable)
        case And(operands=operands) | Or(operands=operands):
            for operand in operands:
                _check_element_predicate(operand, container)
        case Not(operand=operand) | Group(operand=operand):
            _check_element_predicate(operand, container)
        case _:  # pragma: no cover - the elementPredicate schema admits nothing else here
            raise ValueError(
                f"{op!r} is not a legal nestedExists/nestedNotExists element predicate "
                "(m-predicate elementPredicate)"
            )


def _require_nullable_null_check(path: str, nullable: bool) -> None:
    if not nullable:
        raise ModelRejectedError(
            "null-check-non-nullable-member",
            f"{path!r}: isNull/isNotNull is invalid for a non-nullable member "
            "(m-predicate null-check validity)",
        )
