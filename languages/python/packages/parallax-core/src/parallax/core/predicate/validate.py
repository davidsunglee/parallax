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
from typing import assert_never, cast

from parallax.core import inheritance, relationship
from parallax.core.base import ManagedValue, NeutralType, String
from parallax.core.metamodel import (
    AttributeMetadata,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    NestedValueObjectMetadata,
    RelationshipDeclaration,
    RelationshipIdentity,
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
    StringMatch,
)
from parallax.core.predicate._validated import (
    ResolvedPredicateMember,
    ValidatedOperands,
    ValidatedPredicate,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_wire

__all__ = [
    "ModelRejectedError",
    "PositionScope",
    "check_attribute_reference",
    "effective_set",
    "elaborate_predicate",
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
    """A schema-valid predicate or Object Query violates a model-aware rule."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


@dataclass(frozen=True, slots=True)
class PositionScope:
    """The threaded polymorphic-position state."""

    effective: frozenset[str]
    relationship_target: str | None = None


def validate_predicate(
    root: EntityMetadata,
    op: PredicateNode,
    model: Metamodel,
    *,
    position: PositionScope | None = None,
) -> ValidatedPredicate:
    """Validate and resolve ``op`` against ``model`` before planning or lowering."""
    scope = (
        position if position is not None else PositionScope(effective=effective_set(model, root))
    )
    return _walk(op, model, scope)


def elaborate_predicate(
    root: EntityMetadata,
    op: PredicateNode,
    model: Metamodel,
    *,
    position: PositionScope | None = None,
) -> ValidatedPredicate:
    """Elaborate one authored predicate into its mandatory semantic product."""
    return validate_predicate(root, op, model, position=position)


def root_position(model: Metamodel, root: EntityMetadata) -> PositionScope:
    """The active position a read starts from: ``root``'s effective concrete set."""
    return PositionScope(effective=effective_set(model, root))


def _walk(op: PredicateNode, model: Metamodel, scope: PositionScope) -> ValidatedPredicate:
    match op:
        case All() | NoneOp():
            return ValidatedPredicate(op)
        case Comparison(attr=attr, value=value):
            member = _require_attribute(attr, model, scope)
            return _validated_leaf(op, member, (value,))
        case StringMatch(attr=attr, value=value):
            member = _require_attribute(attr, model, scope)
            if not isinstance(member.type, String):
                raise ModelRejectedError(
                    "string-predicate-non-string-member",
                    f"{attr!r}: a string predicate requires a string member",
                )
            return _validated_leaf(op, member, (value,))
        case Membership(attr=attr, values=values):
            member = _require_attribute(attr, model, scope)
            return _validated_leaf(op, member, values)
        case NullCheck(attr=attr):
            member = resolve_attribute_reference(attr, model, scope)
            _check_attribute_null_check(attr, model)
            return ValidatedPredicate(op, member=member)
        case Between(attr=attr, lower=lower, upper=upper):
            member = _require_attribute(attr, model, scope)
            product = _validated_leaf(op, member, (lower, upper))
            _check_managed_bound_ordering(attr, product.operands)
            return product
        case NestedComparison(path=path, value=value):
            leaf = _resolve_nested_leaf(path, model)
            return _validated_leaf(op, leaf, (value,))
        case NestedRange(path=path, lower=lower, upper=upper):
            leaf = _resolve_nested_leaf(path, model)
            product = _validated_leaf(op, leaf, (lower, upper))
            _check_managed_bound_ordering(path, product.operands)
            return product
        case NestedMembership(path=path, values=values):
            leaf = _resolve_nested_leaf(path, model)
            return _validated_leaf(op, leaf, values)
        case NestedStringMatch(path=path, value=value):
            leaf = _resolve_nested_leaf(path, model)
            _check_string_member(path, leaf)
            return _validated_leaf(op, leaf, (value,))
        case NestedNullCheck():
            leaf = _resolve_nested_leaf(op.path, model)
            _require_nullable_null_check(op.path, leaf.nullable)
            return ValidatedPredicate(op, member=leaf)
        case NestedExists(path=path, where=where) | NestedNotExists(path=path, where=where):
            container = _check_nested_vo_terminated(path, model)
            children = () if where is None else (_elaborate_element_predicate(where, container),)
            return ValidatedPredicate(op, children=children, container=container)
        case And(operands=operands) | Or(operands=operands):
            return ValidatedPredicate(
                op, children=tuple(_walk(operand, model, scope) for operand in operands)
            )
        case Not(operand=operand) | Group(operand=operand):
            return ValidatedPredicate(op, children=(_walk(operand, model, scope),))
        case Narrow(to=to, operand=operand):
            new_scope = validate_narrow(to, scope, model)
            return ValidatedPredicate(
                op,
                children=(_walk(operand, model, new_scope),),
                position=_position_identities(model, new_scope),
            )
        case Navigate(rel=rel, op=inner) | Exists(rel=rel, op=inner) | NotExists(rel=rel, op=inner):
            target = relationship_target(rel, model, wrong_kind_rule="navigate-value-object-target")
            direction = _resolved_relationship(rel, model)
            resolved = relationship.view(model).relationship(direction)
            if resolved is None:  # pragma: no cover - accepted models compile every direction
                raise ValueError(f"{rel!r} names no resolved relationship direction")
            source_view = inheritance.view(model).entity(resolved.join.source.entity)
            target_view = inheritance.view(model).entity(resolved.join.target.entity)
            source = (
                None
                if source_view is None
                else source_view.applicable_attribute(resolved.join.source.name)
            )
            member = (
                None
                if target_view is None
                else target_view.applicable_attribute(resolved.join.target.name)
            )
            if source is None or member is None:  # pragma: no cover - formation validates joins
                raise ValueError(f"{rel!r} has unresolved relationship join members")
            hop_scope = PositionScope(
                effective=effective_set(model, target),
                relationship_target=target.identity.canonical,
            )
            children = () if inner is None else (_walk(inner, model, hop_scope),)
            return ValidatedPredicate(
                op,
                children=children,
                relationship_target=target,
                relationship=direction,
                relationship_source=source,
                relationship_member=member,
            )
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def _position_identities(model: Metamodel, position: PositionScope) -> tuple[EntityIdentity, ...]:
    return tuple(
        entity.identity
        for entity in model.entities
        if entity.identity.canonical in position.effective
    )


def _resolved_relationship(rel: str, model: Metamodel) -> RelationshipIdentity:
    class_name, dot, member_name = rel.rpartition(".")
    declaring = entity_by_name(model, class_name) if dot else None
    if declaring is None:
        raise ValueError(f"{rel!r} names no resolved relationship direction")
    return RelationshipIdentity(declaring.identity, member_name)


def _decode_operand(subject: str, value: object, neutral_type: NeutralType) -> ManagedValue:
    try:
        managed = decode_wire(neutral_type, cast("WireValue", value))
    except WireDecodingError as error:
        raise ModelRejectedError(
            f"neutral-literal-{error.reason}",
            f"{subject!r}: {error}",
        ) from error
    return managed


def _validated_leaf(
    authored: PredicateNode,
    member: ResolvedPredicateMember,
    values: Sequence[object],
) -> ValidatedPredicate:
    return ValidatedPredicate(
        authored,
        operands=ValidatedOperands(
            tuple(_decode_operand(_subject_of(authored), value, member.type) for value in values),
            member.type,
        ),
        member=member,
    )


def _subject_of(op: PredicateNode) -> str:
    return getattr(op, "attr", getattr(op, "path", type(op).__name__))


def _check_managed_bound_ordering(subject: str, operands: ValidatedOperands | None) -> None:
    if operands is None:
        raise AssertionError("a validated range carries its managed bounds")
    lower, upper = operands.values
    try:
        inverted = cast("object", lower) > cast("object", upper)  # type: ignore[operator]
    except TypeError:  # pragma: no cover - one declared type yields comparable managed members
        inverted = False
    if inverted:
        raise ModelRejectedError(
            "between-bounds-inverted",
            f"{subject!r}: decoded lower bound {lower!r} is greater than decoded upper "
            f"bound {upper!r}, so the range is empty",
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


def resolve_attribute_reference(
    attr_ref: str, model: Metamodel, scope: PositionScope
) -> AttributeMetadata | None:
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
    position = inheritance.view(model).entity(entity.identity)
    attribute = (
        None if position is None else position.applicable_attribute(_attr_name)
    ) or entity.attribute(_attr_name)
    return attribute


def check_attribute_reference(
    attr_ref: str, model: Metamodel, scope: PositionScope
) -> AttributeMetadata | None:
    return resolve_attribute_reference(attr_ref, model, scope)


def _require_attribute(attr_ref: str, model: Metamodel, scope: PositionScope) -> AttributeMetadata:
    attribute = resolve_attribute_reference(attr_ref, model, scope)
    if attribute is None:
        class_name, _, _member = attr_ref.rpartition(".")
        raise ValueError(f"{attr_ref!r} names no declared attribute on {class_name}")
    return attribute


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


def _check_string_member(path: str, leaf: ValueObjectAttributeMetadata) -> None:
    """Reject a string predicate whose resolved leaf is not a ``String`` member.

    Shared by both nested scopes. This is distinct from literal decoding because
    several non-string neutral types also use a string wire carrier.
    """
    if not isinstance(leaf.type, String):
        raise ModelRejectedError(
            "nested-string-predicate-non-string-member",
            f"{path!r}: a string predicate reads text, but the member's declared type is "
            f"{leaf.type!r} (m-predicate non-string-member rule)",
        )


def _elaborate_element_predicate(op: PredicateNode, container: _VoContainer) -> ValidatedPredicate:
    match op:
        case NestedComparison(path=path, value=value):
            leaf = _resolve_element_leaf(container, path)
            return _validated_leaf(op, leaf, (value,))
        case NestedRange(path=path, lower=lower, upper=upper):
            leaf = _resolve_element_leaf(container, path)
            product = _validated_leaf(op, leaf, (lower, upper))
            _check_managed_bound_ordering(path, product.operands)
            return product
        case NestedMembership(path=path, values=values):
            leaf = _resolve_element_leaf(container, path)
            return _validated_leaf(op, leaf, values)
        case NestedStringMatch(path=path, value=value):
            leaf = _resolve_element_leaf(container, path)
            _check_string_member(path, leaf)
            return _validated_leaf(op, leaf, (value,))
        case NestedNullCheck(path=path):
            leaf = _resolve_element_leaf(container, path)
            _require_nullable_null_check(path, leaf.nullable)
            return ValidatedPredicate(op, member=leaf)
        case And(operands=operands) | Or(operands=operands):
            return ValidatedPredicate(
                op,
                children=tuple(
                    _elaborate_element_predicate(operand, container) for operand in operands
                ),
            )
        case Not(operand=operand) | Group(operand=operand):
            return ValidatedPredicate(
                op, children=(_elaborate_element_predicate(operand, container),)
            )
        case _:
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
