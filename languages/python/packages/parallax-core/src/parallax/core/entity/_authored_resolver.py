from __future__ import annotations

from collections.abc import Callable
from typing import Any, assert_never, cast

from parallax.core.base import ManagedValue, NeutralType
from parallax.core.entity._declaration import shape_of, wire_names_of
from parallax.core.entity._expressions import (
    AuthoredAnd,
    AuthoredConstant,
    AuthoredGroup,
    AuthoredNarrow,
    AuthoredNot,
    AuthoredOr,
    AuthoredPath,
    AuthoredPredicate,
    AuthoredPresence,
    AuthoredQuantifier,
    AuthoredQuery,
    AuthoredSubject,
    PreparedOperation,
    UnfinishedOperation,
    ValueObjectReceiver,
    managed_literal,
)
from parallax.core.entity._model import ClassIndex, DomainModel, class_index, model_of
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.core.object_query import (
    InterpretedQuery,
    ObjectQueryNode,
    object_query,
    validate_object_query,
)
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.predicate import (
    CURRENT_SCALAR_ELEMENT,
    And,
    Comparison,
    FalseNode,
    FieldSubject,
    Group,
    Membership,
    ModelRejectedError,
    Narrow,
    Not,
    NullCheck,
    Or,
    PositionScope,
    PredicateInterpretation,
    PredicateNode,
    Presence,
    Quantifier,
    QueryDefinitionError,
    Range,
    ScalarLiteral,
    ScalarSubject,
    StringMatch,
    TrueNode,
    relationship_target,
)
from parallax.core.predicate._resolved import (
    ResolvedAnd,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNot,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPredicateMember,
    ResolvedRange,
    ResolvedStringMatch,
)
from parallax.core.predicate.validate import (
    EntityFrame,
    ObjectElementFrame,
    PredicateFrame,
    ScalarElementFrame,
    adopted_operands,
    check_receiver,
    resolve_narrow,
    resolve_operation,
    resolve_presence,
    resolve_quantifier,
    root_frame,
)
from parallax.core.wire import encode_wire

__all__ = ["object_query_node", "typed_interpretation"]


def typed_interpretation(
    predicate: AuthoredPredicate, model: Metamodel, classes: ClassIndex | None
) -> PredicateInterpretation:
    """The Typed adapter: ``predicate`` resolved against the adopted ``model``.

    Every subject binds against the current scope alone: a class-scoped path
    against the Entity or element position it is read in, a collection element
    against the quantifier over its own collection. Prepared operations adopt
    their managed operands where the resolved member declares exactly the type
    they were prepared under. Unfinished paths resolve their Python member names
    through the Entity Classes ``classes`` indexes and prepare their native
    operands once under the resolved type; a model indexing no classes refuses
    them. Applicability and every other semantic rule are the shared portable
    judgment canonical input meets.
    """
    resolver = _Resolver(model, classes)

    def interpret(root: EntityMetadata, position: PositionScope, /) -> ResolvedPredicate:
        return resolver.walk(predicate, root_frame(root, position))

    return interpret


def object_query_node(query: ObjectQuery[Any, Any], model: DomainModel) -> ObjectQueryNode:
    """``query``'s canonical Object Query under the serving ``model``, exported on
    demand and memoized nowhere; a read never consumes this export.

    Every clause is judged exactly as a Typed read under ``model`` judges it, and
    each predicate path is spelled the way that judgment binds it —
    Entity-qualified at the queried position, relative wherever a scope binds its
    receiver — so the document admits what the Typed query admits and means what
    it means.
    """
    return _canonical_query(typed_read_query(query), model_of(model), class_index(model))


def _canonical_query(
    query: AuthoredQuery, model: Metamodel, classes: ClassIndex | None
) -> ObjectQueryNode:
    root = model.entity(query.target)
    if root is None:
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message=f"{query.target.canonical}: the serving model declares no such Entity",
        )
    resolver = _Resolver(model, classes)
    exported: list[PredicateNode] = []

    def interpret(root: EntityMetadata, position: PositionScope, /) -> ResolvedPredicate:
        exported.append(resolver.export(query.predicate, root_frame(root, position)))
        return ResolvedConstant(True)

    validate_object_query(root, InterpretedQuery(query, interpret), model)
    (predicate,) = exported
    return object_query(
        query.target,
        predicate,
        narrow_to=query.narrow_to,
        temporal=query.temporal,
        order_by=query.order_by,
        limit=query.limit,
        includes=query.includes,
    )


class _Resolver:
    __slots__ = ("_classes", "_model")

    def __init__(self, model: Metamodel, classes: ClassIndex | None) -> None:
        self._model = model
        self._classes = classes

    def walk(self, authored: AuthoredPredicate, frame: PredicateFrame) -> ResolvedPredicate:  # noqa: C901 - exhaustive dispatcher
        model = self._model
        match authored:
            case PreparedOperation(subject, operator, operands, prepared_type):
                return resolve_operation(
                    self._subject(subject, frame),
                    operator,
                    operands,
                    adopted_operands(prepared_type),
                    model=model,
                    frame=frame,
                )
            case UnfinishedOperation(subject, operator, operands):
                return resolve_operation(
                    self._subject(subject, frame),
                    operator,
                    operands,
                    _native_operands,
                    model=model,
                    frame=frame,
                )
            case AuthoredAnd(operands=children):
                return ResolvedAnd(tuple(self.walk(child, frame) for child in children))
            case AuthoredOr(operands=children):
                return ResolvedOr(tuple(self.walk(child, frame) for child in children))
            case AuthoredNot(operand=child):
                return ResolvedNot(self.walk(child, frame))
            case AuthoredGroup(operand=child):
                return ResolvedGroup(self.walk(child, frame))
            case AuthoredConstant(truth=truth):
                return ResolvedConstant(truth)
            case AuthoredQuantifier(kind=kind, collection=collection, where=where):
                return resolve_quantifier(
                    kind,
                    self._spelled(collection, frame),
                    model=model,
                    frame=frame,
                    where=None if where is None else lambda inner: self.walk(where, inner),
                )
            case AuthoredPresence(negated=negated, target=target):
                return resolve_presence(
                    negated, self._spelled(target, frame), model=model, frame=frame
                )
            case AuthoredNarrow(to=to, operand=operand, receiver=receiver, target=target):
                if target is None and receiver is not None:
                    check_receiver(receiver, frame, model)
                return resolve_narrow(
                    to,
                    None if target is None else self._spelled(target, frame),
                    model=model,
                    frame=frame,
                    operand=None if operand is None else lambda inner: self.walk(operand, inner),
                )
            case _:  # pragma: no cover - exhaustiveness guard
                assert_never(authored)

    def export(self, authored: AuthoredPredicate, frame: PredicateFrame) -> PredicateNode:  # noqa: C901 - exhaustive dispatcher
        """``authored``'s canonical node in ``frame``, judged as :meth:`walk`
        judges it and encoding the operands that judgment admits."""
        model = self._model
        match authored:
            case PreparedOperation(subject=subject) | UnfinishedOperation(subject=subject):
                return _exported_operation(
                    self._subject(subject, frame), self.walk(authored, frame)
                )
            case AuthoredAnd(operands=children):
                return And(tuple(self.export(child, frame) for child in children))
            case AuthoredOr(operands=children):
                return Or(tuple(self.export(child, frame) for child in children))
            case AuthoredNot(operand=child):
                return Not(self.export(child, frame))
            case AuthoredGroup(operand=child):
                return Group(self.export(child, frame))
            case AuthoredConstant(truth=truth):
                return TrueNode() if truth else FalseNode()
            case AuthoredQuantifier(kind=kind, collection=collection, where=where):
                path = self._spelled(collection, frame)
                exported, inner = self._exported_within(where)
                resolve_quantifier(kind, path, model=model, frame=frame, where=inner)
                return Quantifier(kind, path, exported[0] if exported else None)
            case AuthoredPresence(negated=negated, target=target):
                path = self._spelled(target, frame)
                resolve_presence(negated, path, model=model, frame=frame)
                return Presence("notExists" if negated else "exists", path)
            case AuthoredNarrow(to=to, operand=operand, receiver=receiver, target=target):
                if target is None and receiver is not None:
                    check_receiver(receiver, frame, model)
                path = None if target is None else self._spelled(target, frame)
                exported, inner = self._exported_within(operand)
                resolve_narrow(to, path, model=model, frame=frame, operand=inner)
                return Narrow(to=to, operand=exported[0] if exported else TrueNode(), path=path)
            case _:  # pragma: no cover - exhaustiveness guard
                assert_never(authored)

    def _exported_within(
        self, authored: AuthoredPredicate | None
    ) -> tuple[list[PredicateNode], Callable[[PredicateFrame], ResolvedPredicate] | None]:
        """A scope callback exporting ``authored`` in the frame the scope binds,
        and the list that export lands in."""
        exported: list[PredicateNode] = []
        if authored is None:
            return exported, None
        inner = authored

        def export_in(frame: PredicateFrame) -> ResolvedPredicate:
            exported.append(self.export(inner, frame))
            return ResolvedConstant(True)

        return exported, export_in

    def _subject(self, subject: AuthoredSubject, frame: PredicateFrame) -> ScalarSubject:
        if isinstance(subject, AuthoredPath):
            return FieldSubject(self._spelled(subject, frame))
        if not isinstance(frame, ScalarElementFrame):
            raise ModelRejectedError(
                "predicate-subject-outside-scope",
                f"{subject.collection.described()}.element is read only inside a quantifier "
                "over its own collection",
            )
        return CURRENT_SCALAR_ELEMENT

    def _spelled(self, path: AuthoredPath, frame: PredicateFrame) -> str:
        """``path``'s canonical spelling in ``frame``: Entity-qualified at the
        queried position, relative wherever a scope binds the object it is read
        from, and refused wherever its receiver is not the current object."""
        names = self._canonical(path) if path.unfinished else path.names
        receiver = path.receiver
        if isinstance(receiver, EntityIdentity):
            if isinstance(frame, EntityFrame) and not frame.bound:
                return ".".join((receiver.canonical, *names))
            check_receiver(receiver, frame, self._model)
            return ".".join(names)
        if not isinstance(frame, ObjectElementFrame) or not _same_shape(receiver, frame):
            raise ModelRejectedError(
                "predicate-subject-outside-scope",
                f"{'.'.join(names)} is read from a Value Object element, and the current scope "
                "binds no element of that Value Object",
            )
        return ".".join(names)

    def _canonical(self, path: AuthoredPath) -> tuple[str, ...]:  # noqa: C901 - one step per member kind
        """The canonical member names ``path``'s Python names denote, read
        through the serving model's own classes for each Entity they reach."""
        receiver = path.receiver
        described = path.described()
        if not isinstance(
            receiver, EntityIdentity
        ):  # pragma: no cover - deferred paths start at an Entity
            raise QueryDefinitionError(code="query-path-invalid", message=described)
        classes = self._classes
        if classes is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=(
                    f"{described}: the serving model was built from no Entity Classes, so it "
                    "has no Python member correspondence to resolve these names through; "
                    "author the predicate canonically through Wire instead"
                ),
            )
        entity = receiver
        current: type | None = None
        value_object: type | None = None
        canonical: list[str] = []
        for index, name in enumerate(path.names):
            if value_object is not None:
                shape = shape_of(value_object)
                segment = shape.py_to_name.get(name)
                if segment is None:
                    raise _unresolved_name(described, value_object.__name__, name)
                canonical.append(segment)
                value_object = shape.nested_classes.get(name)
                if value_object is None and index != len(path.names) - 1:
                    raise QueryDefinitionError(
                        code="query-path-invalid",
                        message=f"{described}: {name!r} is a scalar but the path continues",
                    )
                continue
            if current is None:
                current = classes.class_of(entity)
                if current is None:
                    raise QueryDefinitionError(
                        code="query-expression-invalid",
                        message=(
                            f"{described}: the serving model composes no Entity Class for "
                            f"{entity.canonical}"
                        ),
                    )
            correspondences = wire_names_of(current)
            member = correspondences.members.get(name)
            if member is not None:
                canonical.append(correspondences.py_to_name[name])
                if isinstance(member, AttributeMetadata):
                    if index != len(path.names) - 1:
                        raise QueryDefinitionError(
                            code="query-path-invalid",
                            message=f"{described}: {name!r} is a scalar but the path continues",
                        )
                    continue
                value_object = correspondences.vo_classes[name]
                continue
            relationship = correspondences.relationship_identities.get(name)
            if relationship is None:
                raise _unresolved_name(described, current.__name__, name)
            canonical.append(relationship.name)
            target = relationship_target(
                f"{relationship.source_entity.canonical}.{relationship.name}",
                self._model,
                wrong_kind_rule="path-target-kind-mismatch",
            )
            entity, current = target.identity, None
        return tuple(canonical)


def _exported_operation(subject: ScalarSubject, resolved: ResolvedPredicate) -> PredicateNode:
    """The canonical operation over ``subject`` whose resolution is ``resolved``,
    its operands encoded under the resolved member's declared type."""
    match resolved:
        case ResolvedComparison(op=tag, member=member, value=value):
            return Comparison(tag, subject, _encoded(member.type, value))
        case ResolvedRange(member=member, lower=lower, upper=upper):
            return Range(subject, _encoded(member.type, lower), _encoded(member.type, upper))
        case ResolvedMembership(op=tag, member=member, values=tuple() as values):
            return Membership(tag, subject, tuple(_encoded(member.type, v) for v in values))
        case ResolvedStringMatch(op=tag, pattern=pattern, case_insensitive=folded):
            return StringMatch(tag, subject, pattern, folded or None)
        case ResolvedNullCheck(op=tag) if isinstance(subject, FieldSubject):
            return NullCheck(tag, subject)
        case _:  # pragma: no cover - a Typed operation resolves to one of the above
            raise QueryDefinitionError(
                code="query-expression-invalid", message="an operation with no canonical form"
            )


def _encoded(neutral_type: NeutralType, value: object) -> ScalarLiteral:
    return cast("ScalarLiteral", encode_wire(neutral_type, cast("ManagedValue", value)))


def _same_shape(receiver: ValueObjectReceiver, frame: ObjectElementFrame) -> bool:
    return frame.occurrence.definition.shape == receiver.shape.member_shape


def _unresolved_name(described: str, owner: str, name: str) -> QueryDefinitionError:
    return QueryDefinitionError(
        code="query-path-invalid", message=f"{described}: {owner} declares no member {name!r}"
    )


def _native_operands(
    subject: str, member: ResolvedPredicateMember, values: tuple[object, ...]
) -> tuple[ManagedValue, ...]:
    """Native operands prepared once under the resolved member's declared type
    by the Typed developer-input policy."""
    return tuple(managed_literal(subject, member.type, value) for value in values)
