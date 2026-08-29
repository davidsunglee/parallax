"""Order-insensitive matching under a comparison the caller supplies.

The primitive the runner's row comparison and the read oracle's graph comparison
are each written in terms of, in a module of its own so neither has to reach
through the other for it and neither owns it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any


def multiset_matches(
    left: Sequence[Any], right: Sequence[Any], matches: Callable[[Any, Any], bool]
) -> bool:
    """Whether *left* and *right* hold the same elements under *matches*, in any order.

    *matches* is neither hashable-keyed nor required to be transitive — tolerance-aware
    scalar comparison is neither, and a graph node's comparison depends on the entity it
    is being read as — so this is a greedy match: each left element claims the first
    unclaimed right element it matches, and both sides must be exhausted. The collections
    compared this way are small enough for the O(n^2) match to be free.
    """
    if len(left) != len(right):
        return False
    remaining = list(right)
    for item in left:
        for index, candidate in enumerate(remaining):
            if matches(item, candidate):
                del remaining[index]
                break
        else:
            return False
    return not remaining
