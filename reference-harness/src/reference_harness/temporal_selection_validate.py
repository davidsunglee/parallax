"""Model-aware checks and authoring normalization for temporal read selections."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .inheritance import Family
from .temporality import temporal_axes

__all__ = ["normalize_authored_temporal_selections", "validate_temporal_selections"]

_RESULT_WRAPPER_TAGS = frozenset({"orderBy", "limit", "deepFetch"})
_TEMPORAL_WRAPPER_TAGS = frozenset({"asOf", "asOfRange", "history"})
_ROOT_WRAPPER_TAGS = _RESULT_WRAPPER_TAGS | _TEMPORAL_WRAPPER_TAGS | {"narrow"}


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
    wrappers: list[tuple[str, dict[str, Any]]] = []
    narrows: list[tuple[str, dict[str, Any]]] = []
    node = operation
    while isinstance(node, dict) and len(node) == 1:
        tag = next(iter(node))
        body = node[tag]
        if tag not in _ROOT_WRAPPER_TAGS or not isinstance(body, dict):
            break
        operand = body.get("operand")
        if not isinstance(operand, dict):
            break
        wrapper = (tag, body)
        if tag == "narrow":
            narrows.append(wrapper)
        else:
            wrappers.append(wrapper)
        node = operand

    last_temporal = max(
        (index for index, (tag, _) in enumerate(wrappers) if tag in _TEMPORAL_WRAPPER_TAGS),
        default=len(wrappers) - 1,
    )
    wrappers.insert(
        last_temporal + 1,
        (
            "asOf",
            {"dimension": "transaction-time", "coordinate": "latest"},
        ),
    )
    wrappers.extend(narrows)

    result = node
    for tag, body in reversed(wrappers):
        result = {tag: {**body, "operand": result}}
    return result


def _root_temporal_dimensions(operation: Any) -> list[str]:
    selected: list[str] = []
    node = operation
    while isinstance(node, dict) and len(node) == 1:
        tag = next(iter(node))
        body = node[tag]
        if tag in _TEMPORAL_WRAPPER_TAGS and isinstance(body, dict):
            dimension = body.get("dimension")
            if isinstance(dimension, str):
                selected.append(dimension)
            node = body.get("operand")
            continue
        if tag in _RESULT_WRAPPER_TAGS or tag == "narrow":
            if isinstance(body, dict):
                node = body.get("operand")
                continue
        break
    return selected
