"""The free-standing statement surface (support scope, statement half).

``Entity.where(*predicates)`` builds a side-effect-free :class:`Statement` — the
big-AND of its filter criteria (zero arguments is find-all). ``.order_by`` /
``.limit`` / ``.distinct`` layer the result-shaping directives. ``operation()``
lowers a statement to a canonical ``m-op-algebra`` node and ``serialize()`` to the
canonical document, so the API Conformance Suite can prove an idiomatic statement
serializes to the same operation the corpus authors (the operation no-drift guard).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from parallax.core.entity.expressions import Predicate, and_terms
from parallax.core.op_algebra import (
    All,
    And,
    Distinct,
    Limit,
    Operation,
    OrderBy,
    OrderKey,
    serialize,
)

__all__ = ["Statement"]


@dataclass(frozen=True, slots=True)
class Statement:
    """A free-standing, side-effect-free query statement over one target entity."""

    target: str
    predicate: Operation
    order_keys: tuple[OrderKey, ...] = ()
    limit_count: int | None = None
    is_distinct: bool = False

    def order_by(self, *keys: OrderKey) -> Statement:
        """Order the result by one or more keys (``Attr.asc()`` / ``Attr.desc()``)."""
        if not keys:
            raise ValueError("order_by requires at least one key")
        return replace(self, order_keys=self.order_keys + tuple(keys))

    def limit(self, count: int) -> Statement:
        """Cap the result row count (a positive integer)."""
        if count < 1:
            raise ValueError("limit requires a positive count")
        return replace(self, limit_count=count)

    def distinct(self) -> Statement:
        """Deduplicate the result rows."""
        return replace(self, is_distinct=True)

    def operation(self) -> Operation:
        """The canonical ``m-op-algebra`` operation for this statement."""
        op = self.predicate
        if self.is_distinct:
            op = Distinct(operand=op)
        if self.order_keys:
            op = OrderBy(operand=op, keys=self.order_keys)
        if self.limit_count is not None:
            op = Limit(operand=op, count=self.limit_count)
        return op

    def serialize(self) -> dict[str, object]:
        """The canonical operation document (for the operation no-drift guard)."""
        return serialize(self.operation())


def build_statement(target: str, predicates: tuple[Predicate, ...]) -> Statement:
    """Build a :class:`Statement` conjoining ``predicates`` (empty is find-all)."""
    if not predicates:
        return Statement(target=target, predicate=All())
    if len(predicates) == 1:
        return Statement(target=target, predicate=predicates[0].op)
    operands: list[Operation] = []
    for predicate in predicates:
        operands.extend(and_terms(predicate))
    return Statement(target=target, predicate=And(operands=tuple(operands)))
