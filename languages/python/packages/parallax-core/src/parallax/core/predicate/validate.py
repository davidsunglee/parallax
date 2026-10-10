from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import assert_never, cast

from parallax.core import inheritance
from parallax.core.base import ManagedValue, NeutralType, String
from parallax.core.metamodel import (
    AttributeMetadata,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    OccurrenceMetadata,
    RelationshipDeclaration,
    RelationshipIdentity,
    RelationshipJoin,
    ReverseRelationshipDeclaration,
    ValueObjectAttributeMetadata,
    entity_by_name,
    split_reference,
)
from parallax.core.metamodel._states import ambiguous_entity_spellings
from parallax.core.predicate._interpretation import (
    BETWEEN,
    COMPARE,
    MEMBER_OF,
    NULL_TEST,
    AttributeSubject,
    Compare,
    InRange,
    Match,
    MemberOf,
    NullTest,
    OperandAdmission,
    OperationSubject,
    PathSubject,
    PredicateInterpretation,
    ScalarOperator,
)
from parallax.core.predicate._nodes import (
    All,
    And,
    Between,
    Comparison,
    ComparisonOp,
    Exists,
    Group,
    Membership,
    MembershipOp,
    Narrow,
    Navigate,
    NestedComparison,
    NestedComparisonOp,
    NestedExists,
    NestedMembership,
    NestedMembershipOp,
    NestedNotExists,
    NestedNullCheck,
    NestedNullOp,
    NestedRange,
    NestedStringMatch,
    NestedStringOp,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    NullOp,
    Or,
    PredicateNode,
    QueryDefinitionError,
    StringMatch,
    StringOp,
)
from parallax.core.predicate._resolved import (
    ResolvedAnd,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPredicateMember,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedSemiJoin,
    ResolvedStringMatch,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_wire

__all__ = [
    "ModelRejectedError",
    "PositionScope",
    "adopted_operands",
    "canonical_interpretation",
    "check_attribute_reference",
    "effective_set",
    "illegal_element_predicate",
    "narrowed",
    "relationship_semi_join",
    "relationship_target",
    "require_single_scalar",
    "resolve_element_operation",
    "resolve_operation",
    "resolve_subtype_selection",
    "root_position",
    "validate_narrow",
    "validate_predicate",
    "value_object_scope",
]

_NESTED_COMPARISONS: dict[NestedComparisonOp, ComparisonOp] = {
    "nestedEq": "eq",
    "nestedNotEq": "notEq",
    "nestedGt": "greaterThan",
    "nestedGte": "greaterThanEquals",
    "nestedLt": "lessThan",
    "nestedLte": "lessThanEquals",
}
_NESTED_MEMBERSHIPS: dict[NestedMembershipOp, MembershipOp] = {
    "nestedIn": "in",
    "nestedNotIn": "notIn",
}
_NESTED_STRING_MATCHES: dict[NestedStringOp, StringOp] = {
    "nestedLike": "like",
    "nestedNotLike": "notLike",
    "nestedStartsWith": "startsWith",
    "nestedEndsWith": "endsWith",
    "nestedContains": "contains",
}
_NESTED_NULL_CHECKS: dict[NestedNullOp, NullOp] = {
    "nestedIsNull": "isNull",
    "nestedIsNotNull": "isNotNull",
}


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
) -> ResolvedPredicate:
    """Validate and resolve ``op`` against ``model`` before planning or lowering."""
    scope = (
        position if position is not None else PositionScope(effective=effective_set(model, root))
    )
    return _walk(op, model, scope)


def canonical_interpretation(op: PredicateNode, model: Metamodel) -> PredicateInterpretation:
    """The Wire adapter: ``op`` validated against ``model`` at the position it is given."""

    def interpret(root: EntityMetadata, position: PositionScope, /) -> ResolvedPredicate:
        return validate_predicate(root, op, model, position=position)

    return interpret


def root_position(model: Metamodel, root: EntityMetadata) -> PositionScope:
    """The active position a read starts from: ``root``'s effective concrete set."""
    return PositionScope(effective=effective_set(model, root))


def _walk(op: PredicateNode, model: Metamodel, scope: PositionScope) -> ResolvedPredicate:
    match op:
        case All() | NoneOp():
            return ResolvedConstant(isinstance(op, All))
        case Comparison() | StringMatch() | Membership() | NullCheck() | Between():
            return resolve_operation(
                *_attribute_operation(op), _decoded_operands, model=model, scope=scope
            )
        case (
            NestedComparison()
            | NestedRange()
            | NestedMembership()
            | NestedStringMatch()
            | NestedNullCheck()
        ):
            return resolve_operation(
                PathSubject(op.path),
                *_nested_operation(op),
                _decoded_operands,
                model=model,
                scope=scope,
            )
        case NestedExists(path=path, where=where) | NestedNotExists(path=path, where=where):
            container = value_object_scope(path, model)
            return ResolvedQuantifier(
                "none" if isinstance(op, NestedNotExists) else "any",
                container,
                None if where is None else _elaborate_element_predicate(where, container),
            )
        case And(operands=operands) | Or(operands=operands):
            children = tuple(_walk(operand, model, scope) for operand in operands)
            return ResolvedAnd(children) if isinstance(op, And) else ResolvedOr(children)
        case Not(operand=operand) | Group(operand=operand):
            child = _walk(operand, model, scope)
            return ResolvedNot(child) if isinstance(op, Not) else ResolvedGroup(child)
        case Narrow(to=to, operand=operand):
            return narrowed(to, scope, model, lambda inner: _walk(operand, model, inner))
        case (
            Navigate(rel=rel, op=interior)
            | Exists(rel=rel, op=interior)
            | NotExists(rel=rel, op=interior)
        ):
            return relationship_semi_join(
                rel,
                negated=isinstance(op, NotExists),
                model=model,
                interior=None if interior is None else lambda hop: _walk(interior, model, hop),
            )
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def _attribute_operation(
    op: Comparison | StringMatch | Membership | NullCheck | Between,
) -> tuple[AttributeSubject, ScalarOperator, tuple[object, ...]]:
    match op:
        case Comparison(op=tag, attr=attr, value=value):
            return AttributeSubject(attr), COMPARE[tag], (value,)
        case StringMatch(op=tag, attr=attr, value=value, case_insensitive=folded):
            return AttributeSubject(attr), Match(tag, bool(folded)), (value,)
        case Membership(op=tag, attr=attr, values=values):
            return AttributeSubject(attr), MEMBER_OF[tag], values
        case NullCheck(op=tag, attr=attr):
            return AttributeSubject(attr), NULL_TEST[tag], ()
        case Between(attr=attr, lower=lower, upper=upper):
            return AttributeSubject(attr), BETWEEN, (lower, upper)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def _nested_operation(
    op: NestedComparison | NestedRange | NestedMembership | NestedStringMatch | NestedNullCheck,
) -> tuple[ScalarOperator, tuple[object, ...]]:
    match op:
        case NestedComparison(op=tag, value=value):
            return COMPARE[_NESTED_COMPARISONS[tag]], (value,)
        case NestedRange(lower=lower, upper=upper):
            return BETWEEN, (lower, upper)
        case NestedMembership(op=tag, values=values):
            return MEMBER_OF[_NESTED_MEMBERSHIPS[tag]], values
        case NestedStringMatch(op=tag, value=value, case_insensitive=folded):
            return Match(_NESTED_STRING_MATCHES[tag], bool(folded)), (value,)
        case NestedNullCheck(op=tag):
            return NULL_TEST[_NESTED_NULL_CHECKS[tag]], ()
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def resolve_operation(
    subject: OperationSubject,
    operator: ScalarOperator,
    operands: tuple[object, ...],
    admit: OperandAdmission,
    *,
    model: Metamodel,
    scope: PositionScope,
) -> ResolvedPredicate:
    """One scalar operation at an Entity position, its subject resolved against
    ``model`` and its operands made managed by ``admit``.

    An Attribute must be applicable at ``scope``. A Value Object leaf path is
    read from the Entity through its occurrences; through a ``many`` occurrence
    the operation means some element satisfies it, so it binds the first such
    element the path crosses.
    """
    if isinstance(subject, AttributeSubject):
        member = _require_attribute(subject.reference, model, scope)
        return _judged(subject.reference, member, operator, operands, admit, nested=False)
    leaf, crossed = _resolve_nested_leaf(subject.path, model)
    operation = _judged(subject.path, leaf, operator, operands, admit, nested=True)
    return operation if crossed is None else ResolvedQuantifier("any", crossed, operation)


def resolve_element_operation(
    path: str,
    operator: ScalarOperator,
    operands: tuple[object, ...],
    admit: OperandAdmission,
    element: OccurrenceMetadata,
) -> ResolvedPredicate:
    """One scalar operation over the leaf ``path`` names relative to the bound
    ``element`` of an enclosing Value Object scope."""
    leaf = _resolve_element_leaf(element, path)
    return _judged(path, leaf, operator, operands, admit, nested=True)


def _judged(
    subject: str,
    member: ResolvedPredicateMember,
    operator: ScalarOperator,
    operands: tuple[object, ...],
    admit: OperandAdmission,
    *,
    nested: bool,
) -> ResolvedPredicate:
    match operator:
        case Compare(op=tag):
            (managed,) = admit(subject, member, operands)
            return ResolvedComparison(tag, member, managed)
        case InRange():
            return _resolved_range(subject, member, admit(subject, member, operands))
        case MemberOf(op=tag):
            return ResolvedMembership(tag, member, admit(subject, member, operands))
        case Match(op=tag, case_insensitive=folded):
            if nested:
                _check_string_member(subject, member)
            elif not isinstance(member.type, String):
                raise ModelRejectedError(
                    "string-predicate-non-string-member",
                    f"{subject!r}: a string predicate requires a string member",
                )
            require_single_scalar(subject, member)
            (pattern,) = operands
            return ResolvedStringMatch(tag, member, cast("str", pattern), folded)
        case NullTest(op=tag):
            _require_nullable_null_check(subject, member.nullable)
            return ResolvedNullCheck(tag, member)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(operator)


def adopted_operands(prepared_type: NeutralType) -> OperandAdmission:
    """Admission of operands already managed under ``prepared_type``: adopted
    as they are where the resolved member declares exactly that type.

    Matching member identity, or a value that also fits another type's value
    space, is not enough: preparation may already have rounded a value to the
    precision, scale, or width it was prepared under.
    """

    def admit(
        subject: str, member: ResolvedPredicateMember, values: tuple[object, ...]
    ) -> tuple[ManagedValue, ...]:
        require_single_scalar(subject, member)
        if member.type != prepared_type:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=(
                    f"{subject}: its operands were prepared for NeutralType {prepared_type!r}, "
                    f"but the serving model declares {member.type!r}"
                ),
            )
        return cast("tuple[ManagedValue, ...]", values)

    return admit


def illegal_element_predicate(described: object) -> ValueError:
    """The refusal of ``described`` inside a Value Object element scope, which
    admits only element-relative leaf operations and their Boolean composition."""
    return ValueError(
        f"{described!r} is not a legal nestedExists/nestedNotExists element predicate "
        "(m-predicate elementPredicate)"
    )


def narrowed(
    to: Sequence[str],
    scope: PositionScope,
    model: Metamodel,
    operand: Callable[[PositionScope], ResolvedPredicate],
) -> ResolvedNarrow:
    """The narrowing of ``scope`` to the Subtype Selection ``to``, its ``operand``
    resolved at the narrowed position."""
    new_scope = validate_narrow(tuple(to), scope, model)
    return ResolvedNarrow(_position_identities(model, new_scope), operand(new_scope))


def relationship_semi_join(
    rel: str,
    *,
    negated: bool,
    model: Metamodel,
    interior: Callable[[PositionScope], ResolvedPredicate] | None,
) -> ResolvedSemiJoin:
    """A relationship hop resolved to its direction and join members, its
    ``interior`` resolved from the target's own position."""
    target = relationship_target(rel, model, wrong_kind_rule="navigate-value-object-target")
    direction = _resolved_relationship(rel, model)
    join = _direction_join(direction, model)
    source_view = inheritance.view(model).entity(join.source.entity)
    target_view = inheritance.view(model).entity(join.target.entity)
    source = None if source_view is None else source_view.applicable_attribute(join.source.name)
    member = None if target_view is None else target_view.applicable_attribute(join.target.name)
    if source is None or member is None:  # pragma: no cover - formation validates joins
        raise ValueError(f"{rel!r} has unresolved relationship join members")
    hop_scope = PositionScope(
        effective=effective_set(model, target),
        relationship_target=target.identity.canonical,
    )
    return ResolvedSemiJoin(
        direction,
        target,
        source,
        member,
        negated=negated,
        where=None if interior is None else interior(hop_scope),
    )


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


def _direction_join(direction: RelationshipIdentity, model: Metamodel) -> RelationshipJoin:
    """The exact source-to-target join for one identity-resolved direction."""
    declaring = model.entity(direction.source_entity)
    declaration = None if declaring is None else declaring.relationship(direction.name)
    if isinstance(declaration, DefiningRelationshipDeclaration):
        return declaration.join
    if isinstance(declaration, ReverseRelationshipDeclaration):
        peer_owner = model.entity(declaration.reverse_of.source_entity)
        peer = None if peer_owner is None else peer_owner.relationship(declaration.reverse_of.name)
        if isinstance(peer, DefiningRelationshipDeclaration):
            return RelationshipJoin(source=peer.join.target, target=peer.join.source)
    raise ValueError(f"{direction!r} names no resolved relationship direction")


def _decoded_operands(
    subject: str, member: ResolvedPredicateMember, values: Sequence[object]
) -> tuple[ManagedValue, ...]:
    """``values`` decoded once against ``member``'s declared type."""
    require_single_scalar(subject, member)
    decoded: list[ManagedValue] = []
    for value in values:
        try:
            decoded.append(decode_wire(member.type, cast("WireValue", value)))
        except WireDecodingError as error:
            raise ModelRejectedError(
                f"neutral-literal-{error.reason}",
                f"{subject!r}: {error}",
            ) from error
    return tuple(decoded)


def _resolved_range(
    subject: str, member: ResolvedPredicateMember, bounds: tuple[ManagedValue, ...]
) -> ResolvedRange:
    managed_lower, managed_upper = bounds
    try:
        inverted = cast("object", managed_lower) > cast("object", managed_upper)  # type: ignore[operator]
    except TypeError:  # pragma: no cover - one declared type yields comparable managed members
        inverted = False
    if inverted:
        raise ModelRejectedError(
            "between-bounds-inverted",
            f"{subject!r}: decoded lower bound {managed_lower!r} is greater than decoded upper "
            f"bound {managed_upper!r}, so the range is empty",
        )
    return ResolvedRange(member, managed_lower, managed_upper)


def require_single_scalar(
    subject: str, member: AttributeMetadata | ValueObjectAttributeMetadata
) -> None:
    """Refuse a scalar collection where one scalar value is required.

    A collection is neither compared, matched, ranged, nor ordered as a whole;
    nothing here reaches its elements implicitly.
    """
    if member.multiplicity is Multiplicity.MANY:
        raise ModelRejectedError(
            "scalar-collection-unquantified",
            f"{subject!r} names a scalar collection, which is not one scalar value",
        )


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
    families = inheritance.view(model)
    view = families.entity(entity.identity)
    family = None if view is None else families.entity(view.root)
    if family is None:  # pragma: no cover - the facet covers every accepted Entity
        return effective_set(model, entity)
    return frozenset(identity.canonical for identity in family.concrete_subtypes)


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


def check_attribute_reference(
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


def _require_attribute(attr_ref: str, model: Metamodel, scope: PositionScope) -> AttributeMetadata:
    attribute = check_attribute_reference(attr_ref, model, scope)
    if attribute is None:
        class_name, _, _member = attr_ref.rpartition(".")
        raise ValueError(f"{attr_ref!r} names no declared attribute on {class_name}")
    return attribute


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


def _is_value_object_name_anywhere(model: Metamodel, name: str) -> bool:
    return any(entity.value_object(name) is not None for entity in model.entities)


def _resolve_leaf(
    path: str, container: OccurrenceMetadata, segments: Sequence[str]
) -> tuple[ValueObjectAttributeMetadata, OccurrenceMetadata | None]:
    """Walk dotted ``segments`` (non-empty) against ``container`` to a scalar leaf,
    classifying the three ways a path fails: an undeclared segment, a scalar the
    path continues past, and a nested object the path ends on.

    Also answers the first `many` occurrence the walk enters, ``container``
    itself included, or ``None`` when it enters none."""
    scope: OccurrenceMetadata = container
    crossed = container if container.multiplicity is Multiplicity.MANY else None
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        attribute = scope.attribute(segment)
        if attribute is not None:
            if not is_last:
                raise ModelRejectedError(
                    "nested-path-unknown-member",
                    f"{path!r}: {segment!r} is a scalar attribute but the path continues",
                )
            return attribute, crossed
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
        if crossed is None and nested.multiplicity is Multiplicity.MANY:
            crossed = nested
        scope = nested
    raise AssertionError("_resolve_leaf: `segments` must be non-empty")  # pragma: no cover


def _resolve_nested_leaf(
    path: str, model: Metamodel
) -> tuple[ValueObjectAttributeMetadata, OccurrenceMetadata | None]:
    """Resolve an `<Entity>.valueObject(.valueObject)*.attribute` path to its
    leaf and the first `many` occurrence it crosses."""
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


def _resolve_element_leaf(container: OccurrenceMetadata, path: str) -> ValueObjectAttributeMetadata:
    """Resolve an element-relative path (`type`, `geo.country`) to its leaf.

    ``container`` is the TERMINAL value-object descriptor a `nestedExists`/
    `nestedNotExists` `path` resolves to (:func:`value_object_scope`); the
    scoped `where`'s own paths are relative to that SAME element (`m-value-object`
    same-element semantics), never re-prefixed with `Class.valueObject`.
    """
    leaf, _crossed = _resolve_leaf(path, container, path.split("."))
    return leaf


def value_object_scope(path: str, model: Metamodel) -> OccurrenceMetadata:
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
    container: OccurrenceMetadata = vo
    for segment in segments:
        member = container.value_object(segment)
        if member is None:
            raise ModelRejectedError(
                "nested-path-unknown-member",
                f"{path!r}: {segment!r} does not name a nested value object",
            )
        container = member
    return container


def _check_string_member(path: str, leaf: ResolvedPredicateMember) -> None:
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


def _elaborate_element_predicate(
    op: PredicateNode, container: OccurrenceMetadata
) -> ResolvedPredicate:
    match op:
        case (
            NestedComparison()
            | NestedRange()
            | NestedMembership()
            | NestedStringMatch()
            | NestedNullCheck()
        ):
            return resolve_element_operation(
                op.path, *_nested_operation(op), _decoded_operands, container
            )
        case And(operands=operands) | Or(operands=operands):
            children = tuple(
                _elaborate_element_predicate(operand, container) for operand in operands
            )
            return ResolvedAnd(children) if isinstance(op, And) else ResolvedOr(children)
        case Not(operand=operand) | Group(operand=operand):
            child = _elaborate_element_predicate(operand, container)
            return ResolvedNot(child) if isinstance(op, Not) else ResolvedGroup(child)
        case _:
            raise illegal_element_predicate(op)


def _require_nullable_null_check(path: str, nullable: bool) -> None:
    if not nullable:
        raise ModelRejectedError(
            "null-check-non-nullable-member",
            f"{path!r}: isNull/isNotNull is invalid for a non-nullable member "
            "(m-predicate null-check validity)",
        )
