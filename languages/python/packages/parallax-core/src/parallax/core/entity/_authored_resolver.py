from __future__ import annotations

from collections.abc import Callable
from typing import Any, assert_never, cast

from parallax.core.base import ManagedValue, NeutralType
from parallax.core.entity._declaration import shape_of, wire_names_of
from parallax.core.entity._expressions import (
    AuthoredAnd,
    AuthoredConstant,
    AuthoredGroup,
    AuthoredIncludePath,
    AuthoredIncludeSegment,
    AuthoredMemberPath,
    AuthoredNarrow,
    AuthoredNot,
    AuthoredOr,
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
    RelationshipIdentity,
    entity_by_name,
)
from parallax.core.object_query import (
    IncludeSegment,
    InterpretedQuery,
    ObjectQueryNode,
    object_query,
    validate_object_query,
)
from parallax.core.object_query._canonical import canonical_includes
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.object_query._nodes import IncludePathNode
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

__all__ = [
    "include_path_node",
    "object_query_node",
    "typed_predicate_interpretation",
    "typed_query_interpretation",
]


def typed_predicate_interpretation(
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


def typed_query_interpretation(
    query: AuthoredQuery, model: Metamodel, classes: ClassIndex | None
) -> InterpretedQuery:
    """The Typed query adapters: ``query``'s predicate and Include paths resolved
    against the adopted ``model`` at their own gate steps.

    The paths are canonicalized here because ordering, deduplication, and prefix
    elimination are facts about resolved spellings, and retained nowhere because
    each operation binds against its own selection.
    """
    resolver = _Resolver(model, classes)

    def includes() -> tuple[IncludePathNode, ...]:
        return canonical_includes(
            tuple(resolver.include_node(path, query.target) for path in query.includes)
        )

    return InterpretedQuery(
        query, typed_predicate_interpretation(query.predicate, model, classes), includes
    )


def include_path_node(
    path: AuthoredIncludePath,
    queried: EntityIdentity,
    model: Metamodel,
    classes: ClassIndex | None,
) -> IncludePathNode:
    """``path`` as the canonical node it means under ``model`` for a read queried at
    ``queried``.

    A path of its root segment alone needs no classes. A continuation reads the
    reached Entity's class, so ``classes`` absent or missing that Entity refuses
    it as ``query-expression-invalid``, and a name that is no relationship of that
    class as ``query-path-invalid``. Every other rule of the hops the node spells
    is ``validate_include_path``'s.
    """
    return _Resolver(model, classes).include_node(path, queried)


def object_query_node(query: ObjectQuery[Any, Any], model: DomainModel) -> ObjectQueryNode:
    """``query``'s canonical Object Query under the serving ``model``, exported on
    demand and memoized nowhere; a read never consumes this export.

    Every clause is judged exactly as a Typed read under ``model`` judges it, and
    each predicate path is spelled the way that judgment binds it —
    Entity-qualified at the queried position, relative wherever a scope binds its
    receiver — and each Include path is spelled by the resolver a read binds it
    through, so the document admits what the Typed query admits and means what it
    means.
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
    bound: list[IncludePathNode] = []

    def interpret(root: EntityMetadata, position: PositionScope, /) -> ResolvedPredicate:
        exported.append(resolver.export(query.predicate, root_frame(root, position)))
        return ResolvedConstant(True)

    def includes() -> tuple[IncludePathNode, ...]:
        bound.extend(resolver.include_node(path, query.target) for path in query.includes)
        return tuple(bound)

    validate_object_query(root, InterpretedQuery(query, interpret, includes), model)
    (predicate,) = exported
    return object_query(
        query.target,
        predicate,
        narrow_to=query.narrow_to,
        temporal=query.temporal,
        order_by=query.order_by,
        limit=query.limit,
        includes=tuple(bound),
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
            case AuthoredPresence(negated=negated, target=target, where=where):
                return resolve_presence(
                    negated,
                    self._spelled(target, frame),
                    model=model,
                    frame=frame,
                    where=None if where is None else lambda inner: self.walk(where, inner),
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
            case AuthoredPresence(negated=negated, target=target, where=where):
                path = self._spelled(target, frame)
                exported, inner = self._exported_within(where)
                resolve_presence(negated, path, model=model, frame=frame, where=inner)
                return Presence(
                    "notExists" if negated else "exists", path, exported[0] if exported else None
                )
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

    def include_node(self, path: AuthoredIncludePath, queried: EntityIdentity) -> IncludePathNode:
        """``path``'s canonical node for a read queried at ``queried``.

        Each identity names the declaring Entity, so a continuation spells where
        its member was declared rather than the Entity it was reached through.
        """
        described = path.described()
        final = len(path.segments) - 1
        if final:
            self._class_index(described)
        entity = queried
        segments: list[IncludeSegment] = []
        for index, segment in enumerate(path.segments):
            relationship = segment.root_relationship or self._continuation(
                segment, entity, described
            )
            segments.append(IncludeSegment(_relationship_spelling(relationship), segment.narrow_to))
            if index != final:
                entity = self._entity_past(relationship, segment)
        return IncludePathNode(tuple(segments), _source_guard(path.access_source, queried))

    def _continuation(
        self, segment: AuthoredIncludeSegment, entity: EntityIdentity, described: str
    ) -> RelationshipIdentity:
        current = self._class_of(entity, described)
        relationship = segment.relationship_in(wire_names_of(current))
        if relationship is None:
            raise QueryDefinitionError(
                code="query-path-invalid",
                message=(
                    f"{described}: {current.__name__} declares no relationship {segment.py_name!r}"
                ),
            )
        return relationship

    def _entity_past(
        self, relationship: RelationshipIdentity, segment: AuthoredIncludeSegment
    ) -> EntityIdentity:
        """The Entity whose class spells the segment after ``segment``: the sole
        subtype it narrowed to, or else what its relationship points at.

        A narrow naming no Entity of this model continues through that target, so
        ``validate_include_path`` states the narrow's own refusal.
        """
        target = self._relationship_target(relationship, "deep-fetch-value-object-segment")
        if len(segment.narrow_to) != 1:
            return target.identity
        narrowed = entity_by_name(self._model, segment.narrow_to[0])
        return target.identity if narrowed is None else narrowed.identity

    def _class_index(self, described: str) -> ClassIndex:
        classes = self._classes
        if classes is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=(
                    f"{described}: the serving model was built from no Entity Classes, so it "
                    "has no Python member correspondence to resolve these names through; "
                    "author the query canonically through Wire instead"
                ),
            )
        return classes

    def _class_of(self, entity: EntityIdentity, described: str) -> type:
        current = self._class_index(described).class_of(entity)
        if current is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=(
                    f"{described}: the serving model composes no Entity Class for "
                    f"{entity.canonical}"
                ),
            )
        return current

    def _relationship_target(
        self, relationship: RelationshipIdentity, wrong_kind_rule: str
    ) -> EntityMetadata:
        return relationship_target(
            _relationship_spelling(relationship), self._model, wrong_kind_rule=wrong_kind_rule
        )

    def _subject(self, subject: AuthoredSubject, frame: PredicateFrame) -> ScalarSubject:
        if isinstance(subject, AuthoredMemberPath):
            return FieldSubject(self._spelled(subject, frame))
        if not isinstance(frame, ScalarElementFrame):
            raise ModelRejectedError(
                "predicate-subject-outside-scope",
                f"{subject.collection.described()}.element is read only inside a quantifier "
                "over its own collection",
            )
        return CURRENT_SCALAR_ELEMENT

    def _spelled(self, path: AuthoredMemberPath, frame: PredicateFrame) -> str:
        """``path``'s canonical spelling in ``frame``: Entity-qualified at the
        queried position, relative wherever a scope binds the object it is read
        from, and refused wherever its receiver is not the current object."""
        names = self._canonical_names(path) if path.unfinished else path.names
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

    def _canonical_names(self, path: AuthoredMemberPath) -> tuple[str, ...]:  # noqa: C901 - one step per member kind
        """The canonical member names ``path``'s Python names denote, read
        through the serving model's own classes for each Entity they reach."""
        receiver = path.receiver
        described = path.described()
        if not isinstance(
            receiver, EntityIdentity
        ):  # pragma: no cover - deferred paths start at an Entity
            raise QueryDefinitionError(code="query-path-invalid", message=described)
        self._class_index(described)
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
                current = self._class_of(entity, described)
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
            target = self._relationship_target(relationship, "path-target-kind-mismatch")
            entity, current = target.identity, None
        return tuple(canonical)


def _relationship_spelling(relationship: RelationshipIdentity) -> str:
    return f"{relationship.source_entity.canonical}.{relationship.name}"


def _source_guard(source: str | None, queried: EntityIdentity) -> tuple[str, ...] | None:
    """The guard a path reached through the Entity ``source`` authors at ``queried``.

    A guard is what makes a path start from fewer than every queried object, so it
    is the access source measured against the queried position, never against the
    relationship's declaring Entity: ``Dog.doghouse``, declared on ``Dog``, and
    ``Dog.owner``, inherited from ``Animal``, guard an ``Animal`` query identically.
    Reaching the first hop through the queried position itself guards nothing, so
    it authors no selection rather than one resolving to the whole position.
    """
    if source is None or source == queried.canonical:
        return None
    return (source,)


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
