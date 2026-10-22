from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Never

from parallax.core import inheritance
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.object_query._resolved import ResolvedTemporalSelection
from parallax.core.predicate._resolved import (
    CurrentObject,
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
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedRelationship,
    ResolvedStringMatch,
    ScalarElement,
    SubjectPosition,
)
from parallax.core.temporal_read import (
    inject_resolved_as_of,
    propagated_selections,
    resolve_perspective,
)

__all__ = [
    "NoRootSelections",
    "PropagatedRootSelections",
    "RootSelections",
    "TemporalResolution",
    "TemporallyResolvedPredicate",
    "resolve_temporal_visibility",
]


@dataclass(frozen=True, slots=True)
class RootSelections:
    """Restrict the root to its own resolved selections, and see each reached
    target at the finite coordinates they select."""

    selections: tuple[ResolvedTemporalSelection, ...]


@dataclass(frozen=True, slots=True)
class PropagatedRootSelections:
    """Restrict an Include child to the selections the original root's
    selections propagate to it, and see each reached target at the perspective
    the original root's selections propagate."""

    selections: tuple[ResolvedTemporalSelection, ...]


@dataclass(frozen=True, slots=True)
class NoRootSelections:
    """State no root conditions, and see each reached target at Latest."""


type TemporalResolution = RootSelections | PropagatedRootSelections | NoRootSelections


@dataclass(frozen=True, slots=True, init=False)
class TemporallyResolvedPredicate:
    """A predicate whose every reached relationship carries its temporal
    visibility, with the root restriction its resolution established injected.

    Only :func:`resolve_temporal_visibility` constructs one.
    """

    predicate: ResolvedPredicate

    def __init__(self, _unconstructible: Never) -> None:
        raise TypeError("a TemporallyResolvedPredicate is obtained only by resolving")


def resolve_temporal_visibility(
    predicate: ResolvedPredicate,
    *,
    target: EntityMetadata,
    model: Metamodel,
    resolution: TemporalResolution,
) -> TemporallyResolvedPredicate:
    """``predicate`` over ``target`` with temporal visibility established as
    ``resolution`` directs.

    Every relationship the predicate reaches is seen at the perspective the
    resolution's selections propagate, or at Latest without any; nodes that
    reach none are retained as they are. Root restrictions follow, so the
    terms they add are never traversed.
    """
    match resolution:
        case RootSelections(selections=selections):
            resolved = _Resolution(model, selections).predicate(predicate)
            return _closed(inject_resolved_as_of(resolved, selections, _family_root(target, model)))
        case PropagatedRootSelections(selections=selections):
            resolved = _Resolution(model, selections).predicate(predicate)
            propagated = propagated_selections(target, model=model, root_selections=selections)
            return _closed(inject_resolved_as_of(resolved, propagated, _family_root(target, model)))
        case NoRootSelections():
            return _closed(_Resolution(model, ()).predicate(predicate))


def _family_root(target: EntityMetadata, model: Metamodel) -> EntityMetadata:
    return inheritance.root_metadata(inheritance.view(model), model, target.identity)


def _closed(predicate: ResolvedPredicate) -> TemporallyResolvedPredicate:
    closed = object.__new__(TemporallyResolvedPredicate)
    object.__setattr__(closed, "predicate", predicate)
    return closed


class _Resolution:
    __slots__ = ("_model", "_selections")

    def __init__(self, model: Metamodel, selections: tuple[ResolvedTemporalSelection, ...]) -> None:
        self._model = model
        self._selections = selections

    def predicate(self, predicate: ResolvedPredicate) -> ResolvedPredicate:  # noqa: C901 - exhaustive dispatcher
        """``predicate`` with its relationships' visibility established — the
        very object wherever nothing in it changed."""
        match predicate:
            case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
                children = tuple(self.predicate(operand) for operand in operands)
                if _unchanged(children, operands):
                    return predicate
                return (
                    ResolvedAnd(children)
                    if isinstance(predicate, ResolvedAnd)
                    else (ResolvedOr(children))
                )
            case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
                child = self.predicate(operand)
                if child is operand:
                    return predicate
                return (
                    ResolvedNot(child)
                    if isinstance(predicate, ResolvedNot)
                    else (ResolvedGroup(child))
                )
            case (
                ResolvedComparison()
                | ResolvedRange()
                | ResolvedMembership()
                | ResolvedStringMatch()
                | ResolvedNullCheck()
            ):
                position = self._subject_position(predicate.position)
                return (
                    predicate
                    if position is predicate.position
                    else replace(predicate, position=position)
                )
            case ResolvedQuantifier(collection=collection, where=where, position=position):
                reached = (
                    self._relationship(collection)
                    if isinstance(collection, ResolvedRelationship)
                    else collection
                )
                inner = None if where is None else self.predicate(where)
                at = self._position(position)
                if reached is collection and inner is where and at is position:
                    return predicate
                return replace(predicate, collection=reached, where=inner, position=at)
            case ResolvedPresence(target=target, position=position, where=where):
                reached = (
                    self._relationship(target)
                    if isinstance(target, ResolvedRelationship)
                    else target
                )
                inner = None if where is None else self.predicate(where)
                at = self._position(position)
                if reached is target and inner is where and at is position:
                    return predicate
                return replace(predicate, target=reached, position=at, where=inner)
            case ResolvedNarrow(operand=operand, target=target):
                inner = None if operand is None else self.predicate(operand)
                at = self._position(target)
                if inner is operand and at is target:
                    return predicate
                return replace(predicate, operand=inner, target=at)
            case ResolvedConstant():
                return predicate

    def _subject_position(self, position: SubjectPosition) -> SubjectPosition:
        if isinstance(position, ScalarElement):
            return position
        return self._position(position)

    def _position(self, position: ObjectPosition) -> ObjectPosition:
        if isinstance(position, CurrentObject):
            return position
        return RelatedObject(
            self._position(position.source), self._relationship(position.relationship)
        )

    def _relationship(self, relationship: ResolvedRelationship) -> ResolvedRelationship:
        perspective = resolve_perspective(
            relationship.target, model=self._model, root_selections=self._selections
        )
        return replace(relationship, temporal_visibility=perspective)


def _unchanged(
    children: tuple[ResolvedPredicate, ...], operands: tuple[ResolvedPredicate, ...]
) -> bool:
    return all(child is operand for child, operand in zip(children, operands, strict=True))
