from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from typing import Final, cast

from tests._support.corpus import CollectionKinds, compare_graph

SIBLING_NULL_PADDING: Final = "sibling-null-padding"
NARROWED_CHILD_FAMILY_VARIANT: Final = "narrowed-child-family-variant"
_RESIDUAL_KINDS: Final = (SIBLING_NULL_PADDING, NARROWED_CHILD_FAMILY_VARIANT)

CHILD_LEVEL_GRAPH_SHAPE_RESIDUALS: Final[dict[str, frozenset[str]]] = {
    "m-inheritance-065": frozenset({NARROWED_CHILD_FAMILY_VARIANT}),
    "m-inheritance-066": frozenset({SIBLING_NULL_PADDING}),
    "m-inheritance-067": frozenset({NARROWED_CHILD_FAMILY_VARIANT}),
    "m-inheritance-068": frozenset({SIBLING_NULL_PADDING}),
    "m-inheritance-073": frozenset({SIBLING_NULL_PADDING}),
    "m-inheritance-074": frozenset({SIBLING_NULL_PADDING}),
    "m-inheritance-075": frozenset({SIBLING_NULL_PADDING}),
    "m-inheritance-076": frozenset({SIBLING_NULL_PADDING, NARROWED_CHILD_FAMILY_VARIANT}),
    "m-inheritance-077": frozenset({SIBLING_NULL_PADDING}),
    "m-inheritance-078": frozenset({SIBLING_NULL_PADDING}),
    "m-snapshot-read-012": frozenset({SIBLING_NULL_PADDING, NARROWED_CHILD_FAMILY_VARIANT}),
}

D67_WITHOUT_GRAPH_STORIES: Final = frozenset({"m-inheritance-073", "m-inheritance-077"})
D67_GRAPH_STORY_RESIDUALS: Final = (
    frozenset(CHILD_LEVEL_GRAPH_SHAPE_RESIDUALS) - D67_WITHOUT_GRAPH_STORIES
)


def _normalized(value: object, residuals: frozenset[str], *, entity_depth: int = -1) -> object:
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [
            _normalized(
                item,
                residuals,
                entity_depth=entity_depth + 1 if isinstance(item, Mapping) else entity_depth,
            )
            for item in items
        ]
    if not isinstance(value, Mapping):
        return value

    mapping = cast("Mapping[str, object]", value)
    normalized: dict[str, object] = {}
    for key, item in mapping.items():
        if entity_depth >= 0 and SIBLING_NULL_PADDING in residuals and item is None:
            continue
        if (
            entity_depth >= 1
            and NARROWED_CHILD_FAMILY_VARIANT in residuals
            and key == "familyVariant"
        ):
            continue
        normalized[key] = _normalized(
            item,
            residuals,
            entity_depth=entity_depth + 1 if isinstance(item, Mapping) else entity_depth,
        )
    return normalized


def classify_child_graph_shape_residuals(
    observed: Mapping[str, object],
    expected: Mapping[str, object],
    kinds: CollectionKinds,
) -> frozenset[str]:
    failures: dict[frozenset[str], str] = {}
    matches: list[frozenset[str]] = []
    for size in range(len(_RESIDUAL_KINDS) + 1):
        for candidate in combinations(_RESIDUAL_KINDS, size):
            residuals = frozenset(candidate)
            try:
                normalized_observed = cast("Mapping[str, object]", _normalized(observed, residuals))
                normalized_expected = cast("Mapping[str, object]", _normalized(expected, residuals))
                compare_graph(
                    normalized_observed,
                    normalized_expected,
                    kinds,
                )
            except AssertionError as error:
                failures[residuals] = str(error)
                continue
            matches.append(residuals)
        if matches:
            break
    if len(matches) != 1:
        raise AssertionError(
            "graph mismatch is not uniquely explained by the recorded child-shape "
            f"residuals: {matches!r}; failures: {failures!r}"
        )
    return matches[0]
