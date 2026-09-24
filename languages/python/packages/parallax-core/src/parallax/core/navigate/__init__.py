from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from parallax.core.base import ManagedValue
from parallax.core.metamodel import EntityMetadata, Metamodel, TemporalDimension
from parallax.core.predicate import (
    And,
    Exists,
    Group,
    Narrow,
    Navigate,
    Not,
    NotExists,
    Or,
    PredicateNode,
)
from parallax.core.predicate._validated import (
    ValidatedPredicate,
)
from parallax.core.predicate._validated import (
    conjunction as _validated_conjunction,
)
from parallax.core.predicate._validated import derive_predicate as _derive_predicate
from parallax.core.temporal_read import validated_hop_as_of_terms

__all__ = ["canonicalize_validated"]

_EMPTY_MANAGED_PINS: Mapping[TemporalDimension, ManagedValue] = MappingProxyType({})


def canonicalize_validated(
    op: ValidatedPredicate,
    model: Metamodel,
    entity: EntityMetadata,
    root_pins: Mapping[TemporalDimension, ManagedValue] = _EMPTY_MANAGED_PINS,
) -> ValidatedPredicate:
    """Propagate hop terms while preserving every already-elaborated occurrence."""
    if not _contains_navigation(op.authored):
        return op
    return _walk_validated(op, model, entity, root_pins)


def _walk_validated(
    product: ValidatedPredicate,
    model: Metamodel,
    entity: EntityMetadata,
    root_pins: Mapping[TemporalDimension, ManagedValue],
) -> ValidatedPredicate:
    op = product.authored
    match op:
        case Navigate(rel=rel) | Exists(rel=rel) | NotExists(rel=rel):
            target = product.relationship_target
            if target is None:  # pragma: no cover - elaboration resolves every hop
                raise ValueError(f"{rel!r}: validated navigation carries no target")
            inner = (
                None
                if not product.children
                else _walk_validated(product.only_child(), model, target, root_pins)
            )
            terms = validated_hop_as_of_terms(target, model, root_pins)
            combined = (
                None
                if inner is None and not terms
                else terms[0]
                if inner is None and len(terms) == 1
                else _validated_conjunction(*terms)
                if inner is None
                else inner
                if not terms
                else _validated_conjunction(inner, *terms)
            )
            rebuilt: PredicateNode
            if isinstance(op, Navigate):
                rebuilt = Navigate(rel=rel, op=None if combined is None else combined.authored)
            elif isinstance(op, Exists):
                rebuilt = Exists(rel=rel, op=None if combined is None else combined.authored)
            else:
                rebuilt = NotExists(rel=rel, op=None if combined is None else combined.authored)
            return _derive_predicate(product, rebuilt, () if combined is None else (combined,))
        case And() | Or():
            children = tuple(
                _walk_validated(child, model, entity, root_pins) for child in product.children
            )
            rebuilt = (
                And(operands=tuple(child.authored for child in children))
                if isinstance(op, And)
                else Or(operands=tuple(child.authored for child in children))
            )
            return _derive_predicate(product, rebuilt, children)
        case Not() | Group() | Narrow():
            child = _walk_validated(product.only_child(), model, entity, root_pins)
            if isinstance(op, Not):
                rebuilt = Not(operand=child.authored)
            elif isinstance(op, Group):
                rebuilt = Group(operand=child.authored)
            else:
                rebuilt = Narrow(to=op.to, operand=child.authored)
            return _derive_predicate(product, rebuilt, (child,))
        case _:
            return product


def _contains_navigation(op: PredicateNode) -> bool:
    match op:
        case Navigate() | Exists() | NotExists():
            return True
        case And(operands=operands) | Or(operands=operands):
            return any(_contains_navigation(operand) for operand in operands)
        case Not(operand=operand) | Group(operand=operand) | Narrow(operand=operand):
            return _contains_navigation(operand)
        case _:
            # Every remaining leaf (All/NoneOp/Comparison/Between/NullCheck/
            # StringMatch/Membership/NestedComparison/NestedMembership/
            # NestedNullCheck/NestedExists/NestedNotExists) carries no navigation.
            return False
