from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
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
    ValueObjectMetadata,
    entity_by_name,
    split_reference,
)
from parallax.core.metamodel._states import ambiguous_entity_spellings
from parallax.core.predicate._interpretation import (
    BETWEEN,
    COMPARE,
    MEMBER_OF,
    NULL_TEST,
    Compare,
    InRange,
    Match,
    MemberOf,
    NullTest,
    OperandAdmission,
    PredicateInterpretation,
    ScalarOperator,
)
from parallax.core.predicate._nodes import (
    And,
    Comparison,
    CurrentScalarElement,
    FalseNode,
    Group,
    Membership,
    Narrow,
    Not,
    NullCheck,
    Or,
    PredicateNode,
    Presence,
    Quantifier,
    QuantifierKind,
    QueryDefinitionError,
    Range,
    ScalarSubject,
    StringMatch,
    TrueNode,
)
from parallax.core.predicate._resolved import (
    CURRENT,
    ELEMENT,
    ObjectPosition,
    RelatedObject,
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
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedRelationship,
    ResolvedStringMatch,
    ScalarCollection,
    SubjectPosition,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_wire

__all__ = [
    "EntityFrame",
    "ModelRejectedError",
    "ObjectElementFrame",
    "PositionScope",
    "PredicateFrame",
    "ScalarElementFrame",
    "adopted_operands",
    "canonical_interpretation",
    "check_attribute_reference",
    "check_receiver",
    "effective_set",
    "relationship_target",
    "require_single_scalar",
    "resolve_narrow",
    "resolve_operation",
    "resolve_presence",
    "resolve_quantifier",
    "resolve_subtype_selection",
    "root_frame",
    "root_position",
    "validate_narrow",
    "validate_predicate",
]


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


@dataclass(frozen=True, slots=True)
class EntityFrame:
    """An Entity position: the queried one, which spells its paths
    Entity-qualified, or one a scope binds, which spells them relative."""

    entity: EntityMetadata
    position: PositionScope
    bound: bool


@dataclass(frozen=True, slots=True)
class ObjectElementFrame:
    """The element a ``many`` Value Object quantifier binds."""

    occurrence: OccurrenceMetadata


@dataclass(frozen=True, slots=True)
class ScalarElementFrame:
    """The scalar a quantifier over the scalar collection ``member`` binds."""

    member: ResolvedPredicateMember


type PredicateFrame = EntityFrame | ObjectElementFrame | ScalarElementFrame
"""The object or scalar an operation's subject is read from."""


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
    return _walk(op, model, root_frame(root, scope))


def canonical_interpretation(op: PredicateNode, model: Metamodel) -> PredicateInterpretation:
    """The Wire adapter: ``op`` validated against ``model`` at the position it is given."""

    def interpret(root: EntityMetadata, position: PositionScope, /) -> ResolvedPredicate:
        return validate_predicate(root, op, model, position=position)

    return interpret


def root_position(model: Metamodel, root: EntityMetadata) -> PositionScope:
    """The active position a read starts from: ``root``'s effective concrete set."""
    return PositionScope(effective=effective_set(model, root))


def root_frame(root: EntityMetadata, position: PositionScope) -> EntityFrame:
    """The frame a predicate starts from: the queried ``root`` at ``position``."""
    return EntityFrame(root, position, bound=False)


def _walk(op: PredicateNode, model: Metamodel, frame: PredicateFrame) -> ResolvedPredicate:
    match op:
        case TrueNode() | FalseNode():
            return ResolvedConstant(isinstance(op, TrueNode))
        case Comparison() | Range() | Membership() | StringMatch() | NullCheck():
            return resolve_operation(*_operation(op), _decoded_operands, model=model, frame=frame)
        case And(operands=operands) | Or(operands=operands):
            children = tuple(_walk(operand, model, frame) for operand in operands)
            return ResolvedAnd(children) if isinstance(op, And) else ResolvedOr(children)
        case Not(operand=operand) | Group(operand=operand):
            child = _walk(operand, model, frame)
            return ResolvedNot(child) if isinstance(op, Not) else ResolvedGroup(child)
        case Quantifier(kind=kind, path=path, where=where):
            return resolve_quantifier(
                kind,
                path,
                model=model,
                frame=frame,
                where=None if where is None else lambda inner: _walk(where, model, inner),
            )
        case Presence(op=tag, path=path):
            return resolve_presence(tag == "notExists", path, model=model, frame=frame)
        case Narrow(to=to, operand=operand, path=path):
            return resolve_narrow(
                to,
                path,
                model=model,
                frame=frame,
                operand=(
                    None
                    if isinstance(operand, TrueNode)
                    else lambda inner: _walk(operand, model, inner)
                ),
            )
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def _operation(
    op: Comparison | Range | Membership | StringMatch | NullCheck,
) -> tuple[ScalarSubject, ScalarOperator, tuple[object, ...]]:
    match op:
        case Comparison(op=tag, subject=subject, value=value):
            return subject, COMPARE[tag], (value,)
        case Range(subject=subject, lower=lower, upper=upper):
            return subject, BETWEEN, (lower, upper)
        case Membership(op=tag, subject=subject, values=values):
            return subject, MEMBER_OF[tag], values
        case StringMatch(op=tag, subject=subject, value=value, case_insensitive=folded):
            return subject, Match(tag, bool(folded)), (value,)
        case NullCheck(op=tag, subject=subject):
            return subject, NULL_TEST[tag], ()
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def resolve_operation(
    subject: ScalarSubject,
    operator: ScalarOperator,
    operands: tuple[object, ...],
    admit: OperandAdmission,
    *,
    model: Metamodel,
    frame: PredicateFrame,
) -> ResolvedPredicate:
    """One scalar operation in ``frame``, its subject resolved against ``model``
    and its operands made managed by ``admit``.

    A field is read through its path from the frame's object; the current
    scalar element only inside the scalar-collection quantifier binding it.
    """
    if isinstance(subject, CurrentScalarElement):
        if not isinstance(frame, ScalarElementFrame):
            raise _outside_scope(
                "an operation without a path reads the element a scalar-collection "
                "quantifier binds, and no such quantifier encloses it"
            )
        member = frame.member
        return _judged(
            f"{_member_spelling(member)} element", member, operator, operands, admit, ELEMENT
        )
    terminal = _resolve_path(subject.path, frame, model)
    if not isinstance(terminal, _ScalarTerminal):
        raise ModelRejectedError(
            "path-target-kind-mismatch",
            f"{subject.path!r} ends on {terminal.kind}, not a scalar field",
        )
    member = terminal.member
    if not isinstance(operator, NullTest):
        require_single_scalar(subject.path, member)
    return _judged(subject.path, member, operator, operands, admit, terminal.position)


def resolve_quantifier(
    kind: QuantifierKind,
    path: str,
    *,
    model: Metamodel,
    frame: PredicateFrame,
    where: Callable[[PredicateFrame], ResolvedPredicate] | None,
) -> ResolvedQuantifier:
    """A quantifier over the collection ``path`` names in ``frame``, its
    ``where`` resolved in the frame of the element it binds."""
    terminal = _resolve_path(path, frame, model)
    inner: PredicateFrame
    match terminal:
        case _ScalarTerminal(member=member) if member.multiplicity is Multiplicity.MANY:
            collection: ScalarCollection | OccurrenceMetadata | ResolvedRelationship = (
                ScalarCollection(member)
            )
            inner = ScalarElementFrame(member)
        case _OccurrenceTerminal(occurrence=occurrence) if (
            occurrence.multiplicity is Multiplicity.MANY
        ):
            collection = occurrence
            inner = ObjectElementFrame(occurrence)
        case _RelationshipTerminal(relationship=relationship, many=True):
            collection = relationship
            target = relationship.target
            inner = EntityFrame(
                target,
                PositionScope(
                    effective=effective_set(model, target),
                    relationship_target=target.identity.canonical,
                ),
                bound=True,
            )
        case _:
            raise ModelRejectedError(
                "path-target-kind-mismatch",
                f"{path!r} names {terminal.kind}, which a quantifier does not range over; "
                "quantify a collection, or test a single object with exists/notExists",
            )
    return ResolvedQuantifier(
        kind, collection, None if where is None else where(inner), terminal.position
    )


def resolve_presence(
    negated: bool, path: str, *, model: Metamodel, frame: PredicateFrame
) -> ResolvedPresence:
    """Whether the single object ``path`` names in ``frame`` is present."""
    terminal = _resolve_path(path, frame, model)
    match terminal:
        case _OccurrenceTerminal(occurrence=occurrence) if (
            occurrence.multiplicity is Multiplicity.ONE
        ):
            return ResolvedPresence(negated, occurrence, terminal.position)
        case _RelationshipTerminal(relationship=relationship, many=False):
            return ResolvedPresence(negated, relationship, terminal.position)
        case _:
            raise ModelRejectedError(
                "path-target-kind-mismatch",
                f"{path!r} names {terminal.kind}, which has no presence of its own; "
                "exists/notExists test a single object, any/none a collection",
            )


def resolve_narrow(
    to: Sequence[str],
    path: str | None,
    *,
    model: Metamodel,
    frame: PredicateFrame,
    operand: Callable[[PredicateFrame], ResolvedPredicate] | None,
) -> ResolvedNarrow:
    """The narrowing of the current Entity, or of the to-one target ``path``
    reaches from it, to the Subtype Selection ``to``; ``operand`` is resolved at
    the narrowed target, and its absence tests membership alone."""
    if path is None:
        if not isinstance(frame, EntityFrame):
            raise _outside_scope("narrow addresses an Entity position, not a bound element")
        scope = validate_narrow(tuple(to), frame.position, model)
        inner = replace(frame, position=scope)
        return ResolvedNarrow(
            _position_identities(model, scope), None if operand is None else operand(inner)
        )
    terminal = _resolve_path(path, frame, model)
    if not isinstance(terminal, _RelationshipTerminal) or terminal.many:
        raise ModelRejectedError(
            "path-target-kind-mismatch",
            f"{path!r} names {terminal.kind}; a path-targeted narrow reaches a single "
            "related Entity",
        )
    relationship = terminal.relationship
    target = relationship.target
    scope = validate_narrow(
        tuple(to),
        PositionScope(
            effective=effective_set(model, target), relationship_target=target.identity.canonical
        ),
        model,
    )
    return ResolvedNarrow(
        _position_identities(model, scope),
        None if operand is None else operand(EntityFrame(target, scope, bound=True)),
        RelatedObject(terminal.position, relationship),
    )


def check_receiver(receiver: EntityIdentity, frame: PredicateFrame, model: Metamodel) -> None:
    """Refuse a class-scoped subject whose receiver Entity is not applicable at
    ``frame``'s Entity position, which is the only position it binds against."""
    if not isinstance(frame, EntityFrame):
        raise _outside_scope(
            f"{receiver.canonical} is an Entity, but the current scope is a bound element"
        )
    entity = model.entity(receiver)
    if entity is None:
        raise ValueError(f"{receiver.canonical} names no declared entity")
    _check_attribute_position(model, entity, frame.position)


def _judged(
    subject: str,
    member: ResolvedPredicateMember,
    operator: ScalarOperator,
    operands: tuple[object, ...],
    admit: OperandAdmission,
    position: SubjectPosition,
) -> ResolvedPredicate:
    match operator:
        case Compare(op=tag):
            (managed,) = admit(subject, member, operands)
            return ResolvedComparison(tag, member, managed, position=position)
        case InRange():
            lower, upper = _ordered_bounds(subject, admit(subject, member, operands))
            return ResolvedRange(member, lower, upper, position)
        case MemberOf(op=tag):
            return ResolvedMembership(tag, member, admit(subject, member, operands), position)
        case Match(op=tag, case_insensitive=folded):
            _check_string_member(subject, member)
            (pattern,) = admit(subject, member, operands)
            return ResolvedStringMatch(tag, member, cast("str", pattern), folded, position)
        case NullTest(op=tag):
            _require_nullable_null_check(subject, member.nullable)
            return ResolvedNullCheck(tag, member, cast("ObjectPosition", position))
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


def _decoded_operands(
    subject: str, member: ResolvedPredicateMember, values: Sequence[object]
) -> tuple[ManagedValue, ...]:
    """``values`` decoded once against ``member``'s declared scalar type."""
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


def _ordered_bounds(
    subject: str, bounds: tuple[ManagedValue, ...]
) -> tuple[ManagedValue, ManagedValue]:
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
    return managed_lower, managed_upper


def require_single_scalar(
    subject: str, member: AttributeMetadata | ValueObjectAttributeMetadata
) -> None:
    """Refuse a scalar collection where one scalar value is required.

    A collection is neither compared, matched, ranged, nor ordered as a whole;
    its elements are reached only through a quantifier over it.
    """
    if member.multiplicity is Multiplicity.MANY:
        raise ModelRejectedError(
            "scalar-collection-unquantified",
            f"{subject!r} names a scalar collection, which is not one scalar value; "
            "quantify it with any/all/none",
        )


def _member_spelling(member: ResolvedPredicateMember) -> str:
    if isinstance(member, AttributeMetadata):
        return f"{member.identity.entity.canonical}.{member.identity.name}"
    identity = member.identity
    return ".".join(
        (identity.value_object.entity.canonical, *identity.value_object.path, identity.name)
    )


def _outside_scope(message: str) -> ModelRejectedError:
    return ModelRejectedError("predicate-subject-outside-scope", message)


@dataclass(frozen=True, slots=True)
class _ScalarTerminal:
    member: ResolvedPredicateMember
    position: ObjectPosition

    @property
    def kind(self) -> str:
        return (
            "a scalar collection"
            if self.member.multiplicity is Multiplicity.MANY
            else ("a scalar field")
        )


@dataclass(frozen=True, slots=True)
class _OccurrenceTerminal:
    occurrence: OccurrenceMetadata
    position: ObjectPosition

    @property
    def kind(self) -> str:
        return (
            "a many Value Object"
            if self.occurrence.multiplicity is Multiplicity.MANY
            else "a single Value Object"
        )


@dataclass(frozen=True, slots=True)
class _RelationshipTerminal:
    relationship: ResolvedRelationship
    many: bool
    position: ObjectPosition

    @property
    def kind(self) -> str:
        return "a to-many relationship" if self.many else "a to-one relationship"


type _Terminal = _ScalarTerminal | _OccurrenceTerminal | _RelationshipTerminal


def _resolve_path(path: str, frame: PredicateFrame, model: Metamodel) -> _Terminal:
    """The member ``path`` names from ``frame``'s object, following single
    Value Objects and to-one relationships and refusing any other crossing."""
    class_name, members = split_reference(path)
    match frame:
        case EntityFrame(entity=entity, position=position, bound=bound):
            if class_name is None:
                if not bound:
                    raise _outside_scope(
                        f"{path!r} is relative, but the queried position spells its paths "
                        "Entity-qualified"
                    )
                return _walk_entity(path, members, entity, position, CURRENT, model)
            if bound:
                raise _outside_scope(
                    f"{path!r} is Entity-qualified, but inside a scope a path is relative to "
                    "the object the scope binds"
                )
            named = _lookup_entity(model, class_name)
            if named is None:
                raise _unresolved_reference(model, path, class_name)
            _check_attribute_position(model, named, position)
            return _walk_entity(path, members, named, None, CURRENT, model)
        case ObjectElementFrame(occurrence=occurrence):
            if class_name is not None:
                raise _outside_scope(
                    f"{path!r} is Entity-qualified, but inside a Value Object quantifier a "
                    "path is relative to the element it binds"
                )
            return _walk_occurrence(path, members, occurrence, CURRENT)
        case ScalarElementFrame():
            raise _outside_scope(
                f"{path!r} names a field, but a scalar-collection quantifier binds a scalar "
                "with no fields; read the element without a path"
            )
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(frame)


def _walk_entity(
    path: str,
    segments: Sequence[str],
    entity: EntityMetadata,
    position: PositionScope | None,
    reached: ObjectPosition,
    model: Metamodel,
) -> _Terminal:
    """``segments`` from ``entity``: its applicable members when ``position`` is
    ``None`` (an Entity-qualified head already checked against its position),
    else any family member applicable at ``position``."""
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        member = (
            _applicable_member(model, entity, segment)
            if position is None
            else _member_at(model, entity, position, segment)
        )
        if member is None:
            raise ModelRejectedError(
                "path-unknown-member",
                f"{path!r}: {segment!r} names no declared member of {entity.identity.canonical}",
            )
        if isinstance(member, AttributeMetadata):
            if not last:
                raise ModelRejectedError(
                    "path-unknown-member",
                    f"{path!r}: {segment!r} is a scalar attribute but the path continues",
                )
            return _ScalarTerminal(member, reached)
        if isinstance(member, _Relationship):
            relationship, many = member.resolved, member.many
            if last:
                return _RelationshipTerminal(relationship, many, reached)
            if many:
                raise _crosses_many(path, segment)
            reached = RelatedObject(reached, relationship)
            entity = relationship.target
            position = PositionScope(effective=effective_set(model, entity))
            continue
        if last:
            return _OccurrenceTerminal(member, reached)
        if member.multiplicity is Multiplicity.MANY:
            raise _crosses_many(path, segment)
        return _walk_occurrence(path, segments[index + 1 :], member, reached)
    raise AssertionError("a predicate path names at least one member")  # pragma: no cover


def _walk_occurrence(
    path: str,
    segments: Sequence[str],
    container: OccurrenceMetadata,
    reached: ObjectPosition,
) -> _Terminal:
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        attribute = container.attribute(segment)
        if attribute is not None:
            if not last:
                raise ModelRejectedError(
                    "path-unknown-member",
                    f"{path!r}: {segment!r} is a scalar attribute but the path continues",
                )
            return _ScalarTerminal(attribute, reached)
        nested = container.value_object(segment)
        if nested is None:
            raise ModelRejectedError(
                "path-unknown-member",
                f"{path!r}: {segment!r} names no declared member",
            )
        if last:
            return _OccurrenceTerminal(nested, reached)
        if nested.multiplicity is Multiplicity.MANY:
            raise _crosses_many(path, segment)
        container = nested
    raise AssertionError("a predicate path names at least one member")  # pragma: no cover


def _crosses_many(path: str, segment: str) -> ModelRejectedError:
    return ModelRejectedError(
        "path-crosses-many",
        f"{path!r}: {segment!r} holds many objects, so a path cannot continue past it; "
        "bind it with any/all/none and continue relative to its element",
    )


@dataclass(frozen=True, slots=True)
class _Relationship:
    resolved: ResolvedRelationship
    many: bool


type _Member = AttributeMetadata | ValueObjectMetadata | _Relationship


def _applicable_member(model: Metamodel, entity: EntityMetadata, name: str) -> _Member | None:
    """The member ``name`` declares on ``entity`` or an ancestor."""
    view = inheritance.view(model).entity(entity.identity)
    attribute = (None if view is None else view.applicable_attribute(name)) or entity.attribute(
        name
    )
    if attribute is not None:
        return attribute
    vo = (None if view is None else view.applicable_value_object(name)) or entity.value_object(name)
    if vo is not None:
        return vo
    declarations = entity.declared_relationships if view is None else view.applicable_relationships
    declaration = next((d for d in declarations if d.identity.name == name), None)
    return None if declaration is None else _relationship(model, declaration)


def _member_at(
    model: Metamodel, entity: EntityMetadata, position: PositionScope, name: str
) -> _Member | None:
    """The member ``name`` declared by the Entity of ``entity``'s family that is
    applicable at ``position``; disjoint siblings may each declare it, so a
    declaration elsewhere in the family is refused only when none applies."""
    applicable = _applicable_ancestor_member(model, position, name)
    if applicable is not None:
        return applicable
    families = inheritance.view(model)
    view = families.entity(entity.identity)
    root = entity.identity if view is None else view.root
    refusal: ModelRejectedError | None = None
    for candidate in model.entities:
        candidate_view = families.entity(candidate.identity)
        candidate_root = candidate.identity if candidate_view is None else candidate_view.root
        if candidate_root != root:
            continue
        local: AttributeMetadata | ValueObjectMetadata | RelationshipDeclaration | None = (
            candidate.attribute(name)
            or candidate.value_object(name)
            or candidate.relationship(name)
        )
        if local is None:
            continue
        try:
            _check_attribute_position(model, candidate, position)
        except ModelRejectedError as inapplicable:
            refusal = refusal or inapplicable
            continue
        if isinstance(local, DefiningRelationshipDeclaration | ReverseRelationshipDeclaration):
            return _relationship(model, local)
        return local
    if refusal is not None:
        raise refusal
    return None


def _applicable_ancestor_member(
    model: Metamodel, position: PositionScope, name: str
) -> _Member | None:
    """The member ``name`` declared by an Entity applicable at ``position``,
    read from one concrete's precomputed applicable members; ``None`` sends the
    caller to its family-wide scan, which owns refusals.

    An applicable Entity's effective set covers every concrete in the position,
    so it lies on any one of those concretes' ancestry, and an ancestry never
    declares one name twice.
    """
    families = inheritance.view(model)
    concrete = next(iter(position.effective), None)
    view = None if concrete is None else families.entity(_identity_of(concrete))
    local: AttributeMetadata | ValueObjectMetadata | RelationshipDeclaration | None = (
        None
        if view is None
        else view.applicable_attribute(name)
        or view.applicable_value_object(name)
        or next((d for d in view.applicable_relationships if d.identity.name == name), None)
    )
    if local is None:
        return None
    owner = families.entity(
        local.identity.source_entity
        if isinstance(local, DefiningRelationshipDeclaration | ReverseRelationshipDeclaration)
        else local.identity.entity
    )
    owner_effective = () if owner is None else owner.concrete_subtypes
    if not position.effective <= {identity.canonical for identity in owner_effective}:
        return None
    if isinstance(local, DefiningRelationshipDeclaration | ReverseRelationshipDeclaration):
        return _relationship(model, local)
    return local


def _identity_of(canonical: str) -> EntityIdentity:
    namespace, separator, name = canonical.rpartition(".")
    return EntityIdentity(namespace if separator else None, name)


def _relationship(model: Metamodel, declaration: RelationshipDeclaration) -> _Relationship:
    """``declaration``'s direction resolved to its target and join endpoints."""
    direction = declaration.identity
    join = _direction_join(direction, model)
    families = inheritance.view(model)
    source_view = families.entity(join.source.entity)
    target_view = families.entity(join.target.entity)
    source = None if source_view is None else source_view.applicable_attribute(join.source.name)
    related = None if target_view is None else target_view.applicable_attribute(join.target.name)
    target = model.entity(_declaration_target(declaration))
    if source is None or related is None or target is None:  # pragma: no cover - formation
        raise ValueError(f"{direction!r} has unresolved relationship join members")
    return _Relationship(
        ResolvedRelationship(direction, target, source, related),
        _target_multiplicity(declaration, model) is Multiplicity.MANY,
    )


def _target_multiplicity(declaration: RelationshipDeclaration, model: Metamodel) -> Multiplicity:
    if isinstance(declaration, DefiningRelationshipDeclaration):
        return declaration.cardinality.target
    peer_owner = model.entity(declaration.reverse_of.source_entity)
    peer = None if peer_owner is None else peer_owner.relationship(declaration.reverse_of.name)
    if isinstance(peer, DefiningRelationshipDeclaration):
        return peer.cardinality.source
    raise ValueError(  # pragma: no cover - formation pairs every reverse with its peer
        f"{declaration.identity!r} names no resolved relationship direction"
    )


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


def _position_identities(model: Metamodel, position: PositionScope) -> tuple[EntityIdentity, ...]:
    return tuple(
        entity.identity
        for entity in model.entities
        if entity.identity.canonical in position.effective
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


def _check_string_member(subject: str, member: ResolvedPredicateMember) -> None:
    """Reject a string predicate whose resolved member is not ``String``.

    This is distinct from literal decoding because several non-string neutral
    types also use a string Wire carrier.
    """
    if not isinstance(member.type, String):
        raise ModelRejectedError(
            "string-predicate-non-string-member",
            f"{subject!r}: a string predicate reads text, but the member's declared type is "
            f"{member.type!r}",
        )


def _require_nullable_null_check(path: str, nullable: bool) -> None:
    if not nullable:
        raise ModelRejectedError(
            "null-check-non-nullable-member",
            f"{path!r}: isNull/isNotNull is invalid for a non-nullable member "
            "(m-predicate null-check validity)",
        )
