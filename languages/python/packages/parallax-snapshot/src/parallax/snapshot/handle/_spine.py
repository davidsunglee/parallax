"""``parallax.snapshot.handle._spine`` — the result-wrapper spine walk.

``m-predicate`` composes ``deepFetch`` and the temporal wrappers freely with the
other nodes returning their operand's own rows, so the node that answers a
structural question about a read is rarely the outermost one. The read gate asks
two such questions — which relationship levels a request names, and whether it
combines includes with a scanned temporal axis — and they differ only in the
policy applied to the nodes the walk hands them. The walk itself lives here once
so the two policies cannot drift into recognizing different shapes.

This module reaches nothing but Predicate, which is what lets the
read-preflight seam consume it without widening its own §7 grant.
"""

from __future__ import annotations

from collections.abc import Iterator

from parallax.core.predicate import (
    AsOf,
    AsOfRange,
    DeepFetch,
    History,
    Limit,
    Narrow,
    OrderBy,
    PredicateNode,
)

__all__ = ["SpineNode", "own_row_spine"]

SpineNode = OrderBy | Limit | Narrow | AsOf | AsOfRange | History | DeepFetch
"""A node whose result is its operand's OWN rows, reshaped rather than replaced.

``m-predicate`` names this closed set where it resolves an order key's position
— the result-shaping directives, ``deepFetch`` (which attaches fetched levels to
those rows rather than replacing them), and the three temporal wrappers.
``narrow`` belongs here for the same reason: it selects a subset of its operand's
rows and attaches nothing. The algebra's own ordered-position rule leaves
``narrow`` out of its carrier set because ``narrow`` is the node that rule
searches FOR, not because it re-roots the rows a wrapper below it yields.
"""


def own_row_spine(operation: PredicateNode) -> Iterator[SpineNode]:
    """``operation``'s spine of own-row wrappers, outermost first.

    Descends through :data:`SpineNode` and no other node, stopping at the first
    node returning rows of its own — the predicate core, a navigation, or a
    boolean combinator — and yielding nothing at all when ``operation`` is
    already one of those. Nothing is yielded twice and the walk terminates on
    every operation, because each step descends one edge of a finite tree.

    A member may repeat: an operation nesting one ``deepFetch`` under another, or
    a ``narrow`` under a ``history``, puts both on one spine. A caller deciding
    whether ANY node on the spine satisfies its policy must therefore consume the
    whole iterator rather than stop at the first member of a given kind.
    """
    node: PredicateNode = operation
    while True:
        match node:
            case (
                OrderBy() | Limit() | Narrow() | AsOf() | AsOfRange() | History() | DeepFetch()
            ) as wrapper:
                yield wrapper
                node = wrapper.operand
            case _:
                return
