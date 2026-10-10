from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from parallax.core.base import ManagedValue
from parallax.core.metamodel import EntityIdentity, Metamodel, TemporalDimension
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
from parallax.core.temporal_read import resolved_hop_as_of_terms

__all__ = ["propagate_hop_terms"]

_EMPTY_MANAGED_PINS: Mapping[TemporalDimension, ManagedValue] = MappingProxyType({})


def propagate_hop_terms(
    predicate: ResolvedPredicate,
    model: Metamodel,
    root_pins: Mapping[TemporalDimension, ManagedValue] = _EMPTY_MANAGED_PINS,
) -> ResolvedPredicate:
    """Give each relationship the predicate reaches the temporal terms its
    candidates are visible under, retaining every other resolved term as it is."""
    if not _reaches_relationship(predicate):
        return predicate
    return _Propagation(model, root_pins).predicate(predicate)


class _Propagation:
    __slots__ = ("_model", "_pins", "_terms")

    def __init__(self, model: Metamodel, pins: Mapping[TemporalDimension, ManagedValue]) -> None:
        self._model = model
        self._pins = pins
        self._terms: dict[EntityIdentity, tuple[ResolvedPredicate, ...]] = {}

    def predicate(self, predicate: ResolvedPredicate) -> ResolvedPredicate:  # noqa: C901 - exhaustive dispatcher
        """``predicate`` with its relationships' terms filled in — the very
        object wherever nothing in it changed."""
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
            case ResolvedPresence(target=target, position=position):
                reached = (
                    self._relationship(target)
                    if isinstance(target, ResolvedRelationship)
                    else target
                )
                at = self._position(position)
                if reached is target and at is position:
                    return predicate
                return replace(predicate, target=reached, position=at)
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
        source = self._position(position.source)
        relationship = self._relationship(position.relationship)
        if source is position.source and relationship is position.relationship:
            return position
        return RelatedObject(source, relationship)

    def _relationship(self, relationship: ResolvedRelationship) -> ResolvedRelationship:
        identity = relationship.target.identity
        terms = self._terms.get(identity)
        if terms is None:
            terms = resolved_hop_as_of_terms(relationship.target, self._model, self._pins)
            self._terms[identity] = terms
        return relationship if not terms else replace(relationship, visibility=terms)


def _unchanged(
    children: tuple[ResolvedPredicate, ...], operands: tuple[ResolvedPredicate, ...]
) -> bool:
    return all(child is operand for child, operand in zip(children, operands, strict=True))


def _reaches_relationship(predicate: ResolvedPredicate) -> bool:
    match predicate:
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            return any(_reaches_relationship(operand) for operand in operands)
        case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
            return _reaches_relationship(operand)
        case (
            ResolvedComparison()
            | ResolvedRange()
            | ResolvedMembership()
            | ResolvedStringMatch()
            | ResolvedNullCheck()
        ):
            return isinstance(predicate.position, RelatedObject)
        case ResolvedQuantifier(collection=collection, where=where, position=position):
            return (
                isinstance(collection, ResolvedRelationship)
                or isinstance(position, RelatedObject)
                or (where is not None and _reaches_relationship(where))
            )
        case ResolvedPresence(target=target, position=position):
            return isinstance(target, ResolvedRelationship) or isinstance(position, RelatedObject)
        case ResolvedNarrow(operand=operand, target=target):
            return isinstance(target, RelatedObject) or (
                operand is not None and _reaches_relationship(operand)
            )
        case ResolvedConstant():
            return False
