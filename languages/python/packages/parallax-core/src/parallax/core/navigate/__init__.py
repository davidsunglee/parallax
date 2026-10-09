from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from parallax.core.base import ManagedValue
from parallax.core.metamodel import Metamodel, TemporalDimension
from parallax.core.predicate._resolved import (
    ResolvedAnd,
    ResolvedGroup,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedSemiJoin,
)
from parallax.core.predicate._resolved import conjunction as _conjunction
from parallax.core.temporal_read import resolved_hop_as_of_terms

__all__ = ["propagate_hop_terms"]

_EMPTY_MANAGED_PINS: Mapping[TemporalDimension, ManagedValue] = MappingProxyType({})


def propagate_hop_terms(
    predicate: ResolvedPredicate,
    model: Metamodel,
    root_pins: Mapping[TemporalDimension, ManagedValue] = _EMPTY_MANAGED_PINS,
) -> ResolvedPredicate:
    """Conjoin each relationship hop's temporal terms into its interior,
    retaining every other resolved term as it is."""
    if not _contains_navigation(predicate):
        return predicate
    return _propagated(predicate, model, root_pins)


def _propagated(
    predicate: ResolvedPredicate,
    model: Metamodel,
    root_pins: Mapping[TemporalDimension, ManagedValue],
) -> ResolvedPredicate:
    match predicate:
        case ResolvedSemiJoin(target=target, where=where):
            inner = None if where is None else _propagated(where, model, root_pins)
            terms = resolved_hop_as_of_terms(target, model, root_pins)
            combined = (
                inner
                if not terms
                else _conjunction(*terms)
                if inner is None
                else _conjunction(inner, *terms)
            )
            return predicate if combined is where else replace(predicate, where=combined)
        case ResolvedAnd(operands=operands):
            return ResolvedAnd(
                tuple(_propagated(operand, model, root_pins) for operand in operands)
            )
        case ResolvedOr(operands=operands):
            return ResolvedOr(tuple(_propagated(operand, model, root_pins) for operand in operands))
        case ResolvedNot(operand=operand):
            return ResolvedNot(_propagated(operand, model, root_pins))
        case ResolvedGroup(operand=operand):
            return ResolvedGroup(_propagated(operand, model, root_pins))
        case ResolvedNarrow(operand=operand):
            return replace(predicate, operand=_propagated(operand, model, root_pins))
        case _:
            return predicate


def _contains_navigation(predicate: ResolvedPredicate) -> bool:
    match predicate:
        case ResolvedSemiJoin():
            return True
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            return any(_contains_navigation(operand) for operand in operands)
        case (
            ResolvedNot(operand=operand)
            | ResolvedGroup(operand=operand)
            | ResolvedNarrow(operand=operand)
        ):
            return _contains_navigation(operand)
        case _:
            # Scalar operations, constants, and Value Object quantifiers carry
            # no relationship hop.
            return False
