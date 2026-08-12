"""Model-aware checks and authoring normalization for Temporal Selections."""

from __future__ import annotations

from typing import Any

from .inheritance import Family
from .temporality import temporal_axes

__all__ = ["normalize_authored_temporal_selections", "validate_temporal_selections"]


def _declared_dimensions(target: Any, family: Family | None) -> set[str] | None:
    """The dimensions ``target``'s family root declares, or ``None`` when unknown."""
    if not isinstance(target, str) or family is None or target not in family.defs:
        return None
    root = family.root_of(target)
    if root is None:
        return None
    return {axis.dimension for axis in temporal_axes(family.defs[root])}


def validate_temporal_selections(query: Any, family: Family | None) -> list[str]:
    """Return exact per-dimension selection problems for one canonical query.

    The Temporal Selection clause is keyed by dimension, so "exactly one
    selection per dimension" reduces to a set comparison: the map's shape already
    forbids a repeated dimension.
    """
    if not isinstance(query, dict):
        return []
    target = query.get("target")
    declared = _declared_dimensions(target, family)
    if declared is None:
        return []
    temporal = query.get("temporal")
    selected = set(temporal) if isinstance(temporal, dict) else set()
    problems: list[str] = []
    missing = sorted(declared - selected)
    undeclared = sorted(selected - declared)
    if missing:
        problems.append(f"temporal read of {target} is missing selections for {missing}")
    if undeclared:
        problems.append(f"temporal read of {target} selects undeclared dimensions {undeclared}")
    return [
        f"{problem}; a canonical Object Query names exactly one selection per declared dimension"
        for problem in problems
    ]


def normalize_authored_temporal_selections(query: Any, family: Family | None) -> Any:
    """Normalize an authored Transaction-Time omission to explicit Latest."""
    if not isinstance(query, dict):
        return query
    declared = _declared_dimensions(query.get("target"), family)
    if declared is None or "transaction-time" not in declared:
        return query
    temporal = query.get("temporal")
    selected = temporal if isinstance(temporal, dict) else {}
    if "transaction-time" in selected:
        return query
    return {**query, "temporal": {**selected, "transaction-time": {"asOf": "latest"}}}
