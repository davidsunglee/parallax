"""Group-precedence serde check (M2, DQ13): prefix and fluent surfaces collapse.

The first-class ``group`` node exists so that a *prefix* surface
(``group(a.or(b)).and(c)``) and a *fluent* surface
(``a.or(b).group().and(c)``) — both per-language DX sugar — serialize to one
unambiguous canonical node. This test pins that contract WITHOUT a database: two
authored encodings of the same grouped intent must canonicalize (via the serde
seam) to the byte-identical canonical node carried by the grouped compatibility
case (``0222``). That guarantees an implementation's serde round-trips precedence
faithfully, the property the outline calls "deserialize to the same canonical
node."

Requires no Docker; pure serde.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from reference_harness import serde

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GROUPED_CASE = (
    _REPO_ROOT
    / "core"
    / "compatibility"
    / "cases"
    / "0222-group-precedence-grouped.yaml"
)


def _grouped_case_operation() -> dict:
    with _GROUPED_CASE.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["operation"]


# The canonical grouped intent is `(qty >= 25 OR qty <= 5) AND active = true`.
# Below are two surface re-expressions an implementation might emit. They differ
# only in *authoring shape* (key order, operand order is identity-significant and
# kept the same); both MUST canonicalize to the case's canonical node.

# "Prefix" surface: group(...) wrapping the disjunction, written keys-first.
_PREFIX_ENCODING = {
    "and": {
        "operands": [
            {
                "group": {
                    "operand": {
                        "or": {
                            "operands": [
                                {"greaterThanEquals": {"attr": "Order.qty", "value": 25}},
                                {"lessThanEquals": {"attr": "Order.qty", "value": 5}},
                            ]
                        }
                    }
                }
            },
            {"eq": {"value": True, "attr": "Order.active"}},
        ]
    }
}

# "Fluent" surface: identical tree, authored with object keys in a different
# order (value-before-attr, operand-before-or-key). Canonicalization sorts keys,
# so this must collapse to the same node as the prefix encoding.
_FLUENT_ENCODING = {
    "and": {
        "operands": [
            {
                "group": {
                    "operand": {
                        "or": {
                            "operands": [
                                {"greaterThanEquals": {"value": 25, "attr": "Order.qty"}},
                                {"lessThanEquals": {"value": 5, "attr": "Order.qty"}},
                            ]
                        }
                    }
                }
            },
            {"eq": {"attr": "Order.active", "value": True}},
        ]
    }
}


def test_prefix_and_fluent_collapse_to_the_same_canonical_node() -> None:
    prefix = serde.canonical(_PREFIX_ENCODING)
    fluent = serde.canonical(_FLUENT_ENCODING)
    assert prefix == fluent


def test_both_surfaces_match_the_grouped_case_operation() -> None:
    canonical_case = serde.canonical(_grouped_case_operation())
    assert serde.canonical(_PREFIX_ENCODING) == canonical_case
    assert serde.canonical(_FLUENT_ENCODING) == canonical_case


def test_grouped_and_ungrouped_are_distinct_nodes() -> None:
    # Sanity: an explicit `group` node makes the grouped form genuinely different
    # from the ungrouped one, so precedence is carried (not erased) by the node.
    ungrouped = {
        "or": {
            "operands": [
                {"greaterThanEquals": {"attr": "Order.qty", "value": 25}},
                {
                    "and": {
                        "operands": [
                            {"lessThanEquals": {"attr": "Order.qty", "value": 5}},
                            {"eq": {"attr": "Order.active", "value": True}},
                        ]
                    }
                },
            ]
        }
    }
    assert serde.canonical(_grouped_case_operation()) != serde.canonical(ungrouped)
