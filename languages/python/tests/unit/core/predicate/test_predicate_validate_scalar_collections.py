"""m-predicate: a scalar collection is never read as one scalar value.

Every operation family that compares, ranges, matches, or orders one value
refuses a collection subject at any scope with ``scalar-collection-unquantified``,
before its literal is decoded, so no element is reached implicitly. A null check
over a collection is refused as one over any non-nullable member. The corpus
carries the comparison, nested comparison, and Sort Key cases; this holds the
remaining families at the validator's own interface.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core.metamodel import EntityMetadata, entity_by_name
from parallax.core.predicate import ModelRejectedError, deserialize, validate_predicate

_MODEL = models.load_model(
    models.default_models_dir() / "scalar-collection-layout-twin-columns.yaml"
)
_FOUND = entity_by_name(_MODEL, "parallax.compatibility.CollectionTwinItem")
assert _FOUND is not None
_ITEM: EntityMetadata = _FOUND
_PREFIX = "parallax.compatibility.CollectionTwinItem"


@pytest.mark.parametrize(
    ("document", "rule"),
    [
        ({"in": {"attr": f"{_PREFIX}.tags", "values": ["a"]}}, "scalar-collection-unquantified"),
        (
            {"between": {"attr": f"{_PREFIX}.counts", "lower": "x", "upper": 2}},
            "scalar-collection-unquantified",
        ),
        ({"contains": {"attr": f"{_PREFIX}.tags", "value": "a"}}, "scalar-collection-unquantified"),
        (
            {"nestedIn": {"path": f"{_PREFIX}.detail.labels", "values": ["a"]}},
            "scalar-collection-unquantified",
        ),
        (
            {
                "nestedExists": {
                    "path": f"{_PREFIX}.parts",
                    "where": {"nestedEq": {"path": "marks", "value": 1}},
                }
            },
            "scalar-collection-unquantified",
        ),
        ({"isNull": {"attr": f"{_PREFIX}.tags"}}, "null-check-non-nullable-member"),
        (
            {"nestedIsNotNull": {"path": f"{_PREFIX}.detail.labels"}},
            "null-check-non-nullable-member",
        ),
    ],
    ids=[
        "membership",
        "range-before-literal",
        "string",
        "nested-membership",
        "element-scope",
        "null-check",
        "nested-null-check",
    ],
)
def test_a_collection_subject_is_refused_before_any_literal(
    document: dict[str, object], rule: str
) -> None:
    with pytest.raises(ModelRejectedError) as caught:
        validate_predicate(_ITEM, deserialize(document), _MODEL)
    assert caught.value.rule == rule
