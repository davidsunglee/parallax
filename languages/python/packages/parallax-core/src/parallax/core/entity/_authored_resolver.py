from __future__ import annotations

from typing import assert_never

from parallax.core.base import ManagedValue
from parallax.core.entity._declaration import shape_of, wire_names_of
from parallax.core.entity._expressions import (
    AuthoredAnd,
    AuthoredConstant,
    AuthoredGroup,
    AuthoredNarrow,
    AuthoredNot,
    AuthoredOr,
    AuthoredPredicate,
    AuthoredQuantifier,
    AuthoredSemiJoin,
    PreparedOperation,
    UnfinishedOperation,
    managed_literal,
)
from parallax.core.entity._model import ClassIndex
from parallax.core.metamodel import AttributeMetadata, EntityMetadata, Metamodel, OccurrenceMetadata
from parallax.core.predicate import PositionScope, PredicateInterpretation, QueryDefinitionError
from parallax.core.predicate._interpretation import (
    AttributeSubject,
    OperationSubject,
    PathSubject,
)
from parallax.core.predicate._resolved import (
    ResolvedAnd,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedNot,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPredicateMember,
    ResolvedQuantifier,
)
from parallax.core.predicate.validate import (
    adopted_operands,
    illegal_element_predicate,
    narrowed,
    relationship_semi_join,
    require_single_scalar,
    resolve_element_operation,
    resolve_operation,
    value_object_scope,
)

__all__ = ["typed_interpretation"]


def typed_interpretation(
    predicate: AuthoredPredicate, model: Metamodel, classes: ClassIndex | None
) -> PredicateInterpretation:
    """The Typed adapter: ``predicate`` resolved against the adopted ``model``.

    Prepared operations adopt their managed operands where the resolved member
    declares exactly the type they were prepared under. Unfinished operations
    resolve their Python member names through the Entity Classes ``classes``
    indexes and prepare their native operands once under the resolved type; a
    model indexing no classes refuses them. Applicability and every other
    semantic rule are the shared portable judgment canonical input meets.
    """
    resolver = _Resolver(model, classes)

    def interpret(root: EntityMetadata, position: PositionScope, /) -> ResolvedPredicate:
        del root
        return resolver.walk(predicate, position)

    return interpret


class _Resolver:
    __slots__ = ("_classes", "_model")

    def __init__(self, model: Metamodel, classes: ClassIndex | None) -> None:
        self._model = model
        self._classes = classes

    def walk(self, authored: AuthoredPredicate, scope: PositionScope) -> ResolvedPredicate:
        match authored:
            case PreparedOperation(subject, operator, operands, prepared_type):
                return resolve_operation(
                    subject,
                    operator,
                    operands,
                    adopted_operands(prepared_type),
                    model=self._model,
                    scope=scope,
                )
            case UnfinishedOperation(operator=operator, operands=operands):
                return resolve_operation(
                    self._subject(authored),
                    operator,
                    operands,
                    _native_operands,
                    model=self._model,
                    scope=scope,
                )
            case AuthoredAnd(operands=children):
                return ResolvedAnd(tuple(self.walk(child, scope) for child in children))
            case AuthoredOr(operands=children):
                return ResolvedOr(tuple(self.walk(child, scope) for child in children))
            case AuthoredNot(operand=child):
                return ResolvedNot(self.walk(child, scope))
            case AuthoredGroup(operand=child):
                return ResolvedGroup(self.walk(child, scope))
            case _:
                return self._scope(authored, scope)

    def _scope(
        self,
        authored: AuthoredConstant | AuthoredNarrow | AuthoredQuantifier | AuthoredSemiJoin,
        scope: PositionScope,
    ) -> ResolvedPredicate:
        model = self._model
        match authored:
            case AuthoredConstant(truth=truth):
                return ResolvedConstant(truth)
            case AuthoredNarrow(to=to, operand=operand):
                return narrowed(to, scope, model, lambda inner: self.walk(operand, inner))
            case AuthoredQuantifier(kind=kind, path=path, where=where):
                container = value_object_scope(path, model)
                return ResolvedQuantifier(
                    kind, container, None if where is None else self._element(where, container)
                )
            case AuthoredSemiJoin(relationship=relationship, negated=negated, where=where):
                return relationship_semi_join(
                    relationship,
                    negated=negated,
                    model=model,
                    interior=None if where is None else lambda hop: self.walk(where, hop),
                )
            case _:  # pragma: no cover - exhaustiveness guard
                assert_never(authored)

    def _element(
        self, authored: AuthoredPredicate, container: OccurrenceMetadata
    ) -> ResolvedPredicate:
        match authored:
            case PreparedOperation(PathSubject(path=path), operator, operands, prepared_type):
                return resolve_element_operation(
                    path, operator, operands, adopted_operands(prepared_type), container
                )
            case AuthoredAnd(operands=children):
                return ResolvedAnd(tuple(self._element(child, container) for child in children))
            case AuthoredOr(operands=children):
                return ResolvedOr(tuple(self._element(child, container) for child in children))
            case AuthoredNot(operand=child):
                return ResolvedNot(self._element(child, container))
            case AuthoredGroup(operand=child):
                return ResolvedGroup(self._element(child, container))
            case _:
                raise illegal_element_predicate(authored)

    def _subject(self, operation: UnfinishedOperation) -> OperationSubject:
        """The canonical subject ``operation``'s Python member names denote, read
        through the serving model's own class for its anchor."""
        anchor, names = operation.anchor, operation.names
        described = ".".join((anchor.canonical, *names))
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
        cls = classes.class_of(anchor)
        if cls is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{described}: the serving model composes no Entity Class for {anchor}",
            )
        correspondences = wire_names_of(cls)
        head, *rest = names
        member = correspondences.members.get(head)
        if member is None:
            relationship = head in correspondences.relationship_identities
            raise QueryDefinitionError(
                code="query-path-invalid",
                message=(
                    f"{described}: {head!r} is a relationship, which a scalar operation does not "
                    "traverse"
                    if relationship
                    else f"{described}: {cls.__name__} declares no member {head!r}"
                ),
            )
        canonical = [correspondences.py_to_name[head]]
        if isinstance(member, AttributeMetadata):
            if rest:
                raise QueryDefinitionError(
                    code="query-path-invalid",
                    message=f"{described}: {head!r} is a scalar attribute but the path continues",
                )
            return AttributeSubject(f"{anchor.canonical}.{canonical[0]}")
        occurrence = correspondences.vo_classes[head]
        for index, name in enumerate(rest):
            shape = shape_of(occurrence)
            segment = shape.py_to_name.get(name)
            if segment is None:
                raise QueryDefinitionError(
                    code="query-path-invalid",
                    message=f"{described}: {occurrence.__name__} declares no member {name!r}",
                )
            canonical.append(segment)
            nested = shape.nested_classes.get(name)
            if nested is None:
                if index != len(rest) - 1:
                    raise QueryDefinitionError(
                        code="query-path-invalid",
                        message=f"{described}: {name!r} is a scalar leaf but the path continues",
                    )
                break
            occurrence = nested
        return PathSubject(".".join((anchor.canonical, *canonical)))


def _native_operands(
    subject: str, member: ResolvedPredicateMember, values: tuple[object, ...]
) -> tuple[ManagedValue, ...]:
    """Native operands prepared once under the resolved member's declared type
    by the Typed developer-input policy."""
    require_single_scalar(subject, member)
    return tuple(managed_literal(subject, member.type, value) for value in values)
