from __future__ import annotations

from typing import Literal

from parallax.core.metamodel import TemporalDimension

type ExecutionValueSource = (
    tuple[Literal["predicate"], int]
    | tuple[Literal["temporal"], TemporalDimension, Literal["coordinate", "start", "end"]]
    | tuple[Literal["paging"], int]
    | tuple[Literal["limit"]]
    | tuple[Literal["keys"]]
)
"""Where a template obtains one execution value when it renders.

An authored predicate operand by its canonical ordinal, a temporal selection's
bound, a continuation carrier by its term position, a page's cap, or a child
read's gathered parent keys.
"""

_CATEGORY_ORDER: dict[str, int] = {
    "predicate": 0,
    "temporal": 1,
    "paging": 2,
    "limit": 3,
    "keys": 4,
}


def source_order(source: ExecutionValueSource) -> tuple[object, ...]:
    """The canonical sort key of ``source``: its category, then its position
    within that category."""
    category, *rest = source
    return (
        _CATEGORY_ORDER[category],
        *(part.value if isinstance(part, TemporalDimension) else part for part in rest),
    )
