"""Immutable model-bound Object Query product."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from parallax.core.metamodel import AttributeMetadata, EntityIdentity, EntityMetadata
from parallax.core.object_query._nodes import (
    IncludePath,
    ObjectQueryNode,
    OrderKey,
    TemporalDimension,
    TemporalSelection,
)
from parallax.core.predicate import PredicateNode
from parallax.core.predicate._validated import ValidatedPredicate


@dataclass(frozen=True, slots=True)
class ValidatedOrderTerm:
    authored: OrderKey
    member: AttributeMetadata


@dataclass(frozen=True, slots=True)
class ValidatedObjectQuery:
    """An accepted authored query and every resolved clause SQL planning needs."""

    authored: ObjectQueryNode
    root: EntityMetadata
    validated_predicate: ValidatedPredicate
    result_position: tuple[EntityIdentity, ...]
    order_terms: tuple[ValidatedOrderTerm, ...]

    @property
    def target(self) -> EntityIdentity:
        return self.authored.target

    @property
    def predicate(self) -> PredicateNode:
        return self.validated_predicate.authored

    @property
    def narrow_to(self) -> tuple[str, ...] | None:
        return self.authored.narrow_to

    @property
    def temporal(self) -> Mapping[TemporalDimension, TemporalSelection]:
        return self.authored.temporal

    @property
    def order_by(self) -> tuple[OrderKey, ...]:
        return self.authored.order_by

    @property
    def limit(self) -> int | None:
        return self.authored.limit

    @property
    def includes(self) -> tuple[IncludePath, ...]:
        return self.authored.includes
