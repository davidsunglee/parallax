"""Object Query serde and canonicalization (m-object-query).

The Predicate half of the encoding is pinned by ``test_predicate.py``; what
belongs here is the flat query the clauses live on — its round-trip fixed point
over every query the corpus authors, the canonicalization of its two
order-insensitive carriers, the optional-member absences it must preserve, and
the malformed shapes it refuses.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from _support.corpus import case_document
from parallax.conformance import case_format
from parallax.core import object_query as oq
from parallax.core.metamodel import EntityIdentity
from parallax.core.predicate import All, OperationError, QueryDefinitionError

_ORDER = "parallax.compatibility.Order"


def _authored_queries() -> list[tuple[str, dict[str, Any]]]:
    """Every Object Query the corpus authors — reads and read steps alike."""
    found: list[tuple[str, dict[str, Any]]] = []
    for case in case_format.load_cases():
        when: Any = case_document(case).get("when") or {}
        query: Any = when.get("objectQuery")
        if isinstance(query, dict):
            found.append((case.case_id, cast("dict[str, Any]", query)))
        for key in ("scenario", "coherence"):
            steps: Any = when.get(key)
            if not isinstance(steps, list):
                continue
            for index, step in enumerate(cast("list[Any]", steps)):
                if not isinstance(step, dict):
                    continue
                inner: Any = cast("dict[str, Any]", step).get("objectQuery")
                if isinstance(inner, dict):
                    found.append((f"{case.case_id}/{key}/{index}", cast("dict[str, Any]", inner)))
    return found


_AUTHORED = _authored_queries()


@pytest.mark.parametrize("case_id, doc", _AUTHORED, ids=[c for c, _ in _AUTHORED])
def test_an_authored_query_round_trips_as_a_fixed_point(case_id: str, doc: dict[str, Any]) -> None:
    assert oq.serialize(oq.deserialize(doc)) == doc


def _round_trips(doc: dict[str, Any]) -> None:
    assert oq.serialize(oq.deserialize(doc)) == doc


@pytest.mark.parametrize(
    "doc",
    [
        {"target": _ORDER, "predicate": {"all": {}}},
        {
            "target": _ORDER,
            "predicate": {"eq": {"attr": f"{_ORDER}.id", "value": 1}},
            "narrowTo": ["parallax.compatibility.PriorityOrder"],
        },
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        },
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {
                "transaction-time": {"asOf": "2024-01-01T00:00:00+00:00"},
                "valid-time": {
                    "asOfRange": {
                        "start": "2024-01-01T00:00:00+00:00",
                        "end": "2024-06-01T00:00:00+00:00",
                    }
                },
            },
        },
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {"valid-time": {"history": {}}},
        },
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "orderBy": [{"attr": f"{_ORDER}.sku", "direction": "desc", "nulls": "first"}],
            "limit": 2,
        },
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "includes": [
                {
                    "appliesTo": ["parallax.compatibility.PriorityOrder"],
                    "segments": [
                        {"rel": f"{_ORDER}.items"},
                        {
                            "rel": "parallax.compatibility.OrderItem.statuses",
                            "narrowTo": ["parallax.compatibility.ShippedStatus"],
                        },
                    ],
                }
            ],
        },
    ],
    ids=[
        "minimal",
        "narrowTo",
        "one-dimension",
        "both-dimensions",
        "history",
        "shaping",
        "includes",
    ],
)
def test_a_canonical_query_round_trips_as_a_fixed_point(doc: dict[str, Any]) -> None:
    _round_trips(doc)


def test_the_target_keeps_its_authored_entity_spelling() -> None:
    # A query names no model, so the queried position is split structurally and
    # comes back exactly as authored — a bare spelling stays bare.
    assert oq.deserialize({"target": "Order", "predicate": {"all": {}}}).target == EntityIdentity(
        None, "Order"
    )
    assert oq.deserialize({"target": _ORDER, "predicate": {"all": {}}}).target == EntityIdentity(
        "parallax.compatibility", "Order"
    )


def test_an_omitted_clause_round_trips_omitted() -> None:
    # Every optional clause is absent rather than defaulted, so serialization
    # never manufactures one a caller did not author.
    node = oq.deserialize({"target": _ORDER, "predicate": {"all": {}}})
    assert node.narrow_to is None
    assert node.temporal == {}
    assert node.order_by == ()
    assert node.limit is None
    assert node.includes == ()
    assert oq.serialize(node) == {"target": _ORDER, "predicate": {"all": {}}}


def test_a_sort_keys_optional_members_stay_distinct_from_their_defaults() -> None:
    # Omission and an explicit value denote the same order but are distinct
    # authorings, exactly as they were as Predicate nodes.
    omitted = oq.deserialize(
        {"target": _ORDER, "predicate": {"all": {}}, "orderBy": [{"attr": f"{_ORDER}.sku"}]}
    )
    assert omitted.order_by[0].direction is None
    assert omitted.order_by[0].nulls is None
    _round_trips(
        {"target": _ORDER, "predicate": {"all": {}}, "orderBy": [{"attr": f"{_ORDER}.sku"}]}
    )
    _round_trips(
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "orderBy": [{"attr": f"{_ORDER}.sku", "direction": "asc", "nulls": "last"}],
        }
    )


def test_a_sort_keys_null_placement_is_single_shot() -> None:
    key = oq.OrderKey(attr=f"{_ORDER}.sku", direction="desc")
    assert key.nulls_first().nulls == "first"
    with pytest.raises(QueryDefinitionError, match="single-shot") as caught:
        key.nulls_first().nulls_last()
    assert caught.value.code == "query-expression-invalid"


def test_the_temporal_map_serializes_in_canonical_dimension_order() -> None:
    # Key order carries no meaning on the wire, so a document authored the other
    # way round canonicalizes to one form.
    authored: dict[str, Any] = {
        "target": _ORDER,
        "predicate": {"all": {}},
        "temporal": {"valid-time": {"history": {}}, "transaction-time": {"asOf": "latest"}},
    }
    assert list(oq.serialize(oq.deserialize(authored))["temporal"]) == [  # pyright: ignore[reportArgumentType]
        "transaction-time",
        "valid-time",
    ]


def test_a_subtype_selection_canonicalizes_in_every_position_it_occupies() -> None:
    node = oq.deserialize(
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "narrowTo": ["b.Second", "a.First"],
            "includes": [
                {
                    "appliesTo": ["b.Second", "a.First"],
                    "segments": [{"rel": f"{_ORDER}.items", "narrowTo": ["b.Second", "a.First"]}],
                }
            ],
        }
    )
    assert node.narrow_to == ("a.First", "b.Second")
    assert node.includes[0].applies_to == ("a.First", "b.Second")
    assert node.includes[0].segments[0].narrow_to == ("a.First", "b.Second")


def test_deserialize_canonicalizes_the_include_set_before_serialization() -> None:
    short: dict[str, Any] = {"segments": [{"rel": "Order.items"}]}
    maximal: dict[str, Any] = {"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}
    statuses: dict[str, Any] = {"segments": [{"rel": "Order.statuses"}]}
    doc: dict[str, Any] = {
        "target": "Order",
        "predicate": {"all": {}},
        "includes": [statuses, short, maximal, maximal],
    }
    assert oq.serialize(oq.deserialize(doc)) == {
        "target": "Order",
        "predicate": {"all": {}},
        "includes": [maximal, statuses],
    }


def test_serialize_canonicalizes_a_directly_constructed_include_set() -> None:
    short = oq.IncludePath(segments=(oq.IncludeSegment(rel="Order.items"),))
    maximal = oq.IncludePath(
        segments=(
            oq.IncludeSegment(rel="Order.items"),
            oq.IncludeSegment(rel="OrderItem.statuses"),
        )
    )
    statuses = oq.IncludePath(segments=(oq.IncludeSegment(rel="Order.statuses"),))
    node = oq.ObjectQueryNode(
        target=EntityIdentity(None, "Order"),
        predicate=All(),
        includes=(statuses, short, maximal, maximal),
    )
    assert oq.serialize(node)["includes"] == [
        {"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]},
        {"segments": [{"rel": "Order.statuses"}]},
    ]


_MALFORMED: list[tuple[Any, str]] = [
    ("not-a-mapping", "objectQuery must be a mapping"),
    ({"predicate": {"all": {}}}, r"missing required clause `target`"),
    ({"target": _ORDER}, r"missing required clause `predicate`"),
    ({"target": _ORDER, "predicate": {"all": {}}, "x": 1}, r"unexpected key\(s\) \['x'\]"),
    ({"target": "bad name", "predicate": {"all": {}}}, "is not a valid entity name"),
    ({"target": _ORDER, "predicate": {"all": {}}, "limit": 0}, "positive integer"),
    ({"target": _ORDER, "predicate": {"all": {}}, "narrowTo": []}, "non-empty list"),
    ({"target": _ORDER, "predicate": {"all": {}}, "orderBy": []}, "non-empty list"),
    (
        {"target": _ORDER, "predicate": {"all": {}}, "orderBy": [{"attr": "bad attr"}]},
        "not a valid attribute reference",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "orderBy": [{"attr": f"{_ORDER}.sku", "direction": "sideways"}],
        },
        r"`direction` must be 'asc' or 'desc'",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "orderBy": [{"attr": f"{_ORDER}.sku", "nulls": "middle"}],
        },
        r"`nulls` must be 'first' or 'last'",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "orderBy": [{"attr": f"{_ORDER}.sku", "x": 1}],
        },
        r"orderBy key: unexpected key\(s\) \['x'\]",
    ),
    ({"target": _ORDER, "predicate": {"all": {}}, "includes": []}, "non-empty list"),
    (
        {"target": _ORDER, "predicate": {"all": {}}, "includes": [{"segments": []}]},
        "`segments` must be a non-empty list",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "includes": [{"segments": [{"rel": "bad rel"}]}],
        },
        "not a valid relationship reference",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "includes": [{"segments": [{"rel": f"{_ORDER}.items", "x": 1}]}],
        },
        r"include segment: unexpected key\(s\) \['x'\]",
    ),
    (
        {"target": _ORDER, "predicate": {"all": {}}, "temporal": {}},
        "names at least one dimension",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {"decision-time": {"history": {}}},
        },
        r"temporal: unexpected key\(s\) \['decision-time'\]",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {"valid-time": {"mystery": {}}},
        },
        "unknown Temporal Selection",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {"valid-time": {"asOf": "now"}},
        },
        "must be a canonical coordinate",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {"valid-time": {"asOf": 20240101}},
        },
        "must be a non-empty temporal value",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {
                "valid-time": {"asOfRange": {"start": "latest", "end": "2024-01-01T00:00:00Z"}}
            },
        },
        "must be a finite canonical coordinate",
    ),
    (
        {
            "target": _ORDER,
            "predicate": {"all": {}},
            "temporal": {"valid-time": {"asOf": "latest", "history": {}}},
        },
        "a Temporal Selection has exactly one key",
    ),
]


@pytest.mark.parametrize(("doc", "message"), _MALFORMED, ids=lambda value: None)
def test_deserialize_rejects_a_malformed_query(doc: object, message: str) -> None:
    with pytest.raises(OperationError, match=message):
        oq.deserialize(doc)


def test_a_malformed_predicate_reports_through_the_shared_error_family() -> None:
    # A query carries a predicate, so "this document is malformed" is one
    # question with one answer class whichever half is wrong.
    with pytest.raises(OperationError, match="unknown predicate node"):
        oq.deserialize({"target": _ORDER, "predicate": {"mystery": {}}})
