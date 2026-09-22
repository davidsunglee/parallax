from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.metamodel import entity_by_name
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

CHILD_SHAPE_CASES_WITHOUT_STORIES: Final = frozenset({"m-inheritance-073", "m-inheritance-077"})
CHILD_SHAPE_GRAPH_STORY_RESIDUALS: Final = (
    frozenset(CHILD_LEVEL_GRAPH_SHAPE_RESIDUALS) - CHILD_SHAPE_CASES_WITHOUT_STORIES
)


def _sibling_only_attributes(
    mapping: Mapping[str, object], kinds: CollectionKinds
) -> frozenset[str]:
    variant = mapping.get("familyVariant")
    if not isinstance(variant, str):
        return frozenset()
    concrete = entity_by_name(kinds.model, variant)
    if concrete is None:
        return frozenset()
    facet = inheritance.view(kinds.model)
    concrete_view = facet.entity(concrete.identity)
    if concrete_view is None:
        return frozenset()
    root_view = facet.entity(concrete_view.root)
    if root_view is None:
        return frozenset()
    applicable = {attribute.identity.name for attribute in concrete_view.applicable_attributes}
    return frozenset(
        attribute.identity.name
        for attribute in root_view.superset_attributes
        if attribute.identity.name not in applicable
    )


def _single_concrete_narrowed_view(key: str) -> bool:
    _prefix, separator, suffix = key.partition("[")
    return bool(separator and suffix.endswith("]") and "," not in suffix)


def _normalized(
    value: object,
    residuals: frozenset[str],
    kinds: CollectionKinds,
    *,
    narrowed_child: bool = False,
) -> object:
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [
            _normalized(
                item,
                residuals,
                kinds,
                narrowed_child=narrowed_child,
            )
            for item in items
        ]
    if not isinstance(value, Mapping):
        return value

    mapping = cast("Mapping[str, object]", value)
    sibling_only: frozenset[str] = (
        _sibling_only_attributes(mapping, kinds)
        if SIBLING_NULL_PADDING in residuals
        else frozenset()
    )
    normalized: dict[str, object] = {}
    for key, item in mapping.items():
        if key in sibling_only and item is None:
            continue
        if narrowed_child and NARROWED_CHILD_FAMILY_VARIANT in residuals and key == "familyVariant":
            continue
        normalized[key] = _normalized(
            item,
            residuals,
            kinds,
            narrowed_child=_single_concrete_narrowed_view(key),
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
                normalized_observed = cast(
                    "Mapping[str, object]", _normalized(observed, residuals, kinds)
                )
                normalized_expected = cast(
                    "Mapping[str, object]", _normalized(expected, residuals, kinds)
                )
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
