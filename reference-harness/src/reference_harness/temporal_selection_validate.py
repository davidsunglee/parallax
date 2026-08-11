"""Model-aware checks and authoring normalization for temporal read selections."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .inheritance import Family
from .temporality import temporal_axes

__all__ = ["normalize_authored_temporal_selections", "validate_temporal_selections"]


def validate_temporal_selections(operation: Any, target: Any, family: Family | None) -> list[str]:
    """Return exact per-dimension selection problems for one canonical read."""
    if not isinstance(target, str) or family is None or target not in family.defs:
        return []
    root = family.root_of(target)
    if root is None:
        return []
    declared = {axis.dimension for axis in temporal_axes(family.defs[root])}
    selected = Counter(_root_temporal_dimensions(operation))
    problems: list[str] = []
    missing = sorted(dimension for dimension in declared if selected[dimension] == 0)
    duplicate = sorted(dimension for dimension in declared if selected[dimension] > 1)
    undeclared = sorted(dimension for dimension in selected if dimension not in declared)
    if missing:
        problems.append(f"temporal read of {target} is missing selections for {missing}")
    if duplicate:
        problems.append(f"temporal read of {target} repeats selections for {duplicate}")
    if undeclared:
        problems.append(f"temporal read of {target} selects undeclared dimensions {undeclared}")
    return [
        f"{problem}; canonical operations name exactly one selection per declared dimension"
        for problem in problems
    ]


def normalize_authored_temporal_selections(
    operation: Any, target: Any, family: Family | None
) -> Any:
    """Normalize an authored Transaction-Time omission to explicit Latest."""
    if not isinstance(target, str) or family is None or target not in family.defs:
        return operation
    root = family.root_of(target)
    if root is None:
        return operation
    declared = {axis.dimension for axis in temporal_axes(family.defs[root])}
    selected = _root_temporal_dimensions(operation)
    if "transaction-time" not in declared or "transaction-time" in selected:
        return operation
    return _insert_transaction_time_latest(operation)


def _insert_transaction_time_latest(operation: Any) -> Any:
    if not isinstance(operation, dict) or len(operation) != 1:
        return {
            "asOf": {
                "operand": operation,
                "dimension": "transaction-time",
                "coordinate": "latest",
            }
        }
    tag = next(iter(operation))
    body = operation[tag]
    if tag in ("orderBy", "limit", "deepFetch", "asOf", "asOfRange", "history") and isinstance(
        body, dict
    ):
        operand = body.get("operand")
        if isinstance(operand, dict):
            return {tag: {**body, "operand": _insert_transaction_time_latest(operand)}}
    return {
        "asOf": {
            "operand": operation,
            "dimension": "transaction-time",
            "coordinate": "latest",
        }
    }


def _root_temporal_dimensions(operation: Any) -> list[str]:
    selected: list[str] = []
    node = operation
    while isinstance(node, dict) and len(node) == 1:
        tag = next(iter(node))
        body = node[tag]
        if tag in ("orderBy", "limit", "deepFetch") and isinstance(body, dict):
            node = body.get("operand")
            continue
        if tag in ("asOf", "asOfRange", "history") and isinstance(body, dict):
            dimension = body.get("dimension")
            if isinstance(dimension, str):
                selected.append(dimension)
            node = body.get("operand")
            continue
        break
    return selected
