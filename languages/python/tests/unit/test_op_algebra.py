"""Operation-algebra node + serde unit tests (m-op-algebra).

The serde round-trip contract (`serialize(deserialize(x)) == x`) is proven over
every operation the corpus authors — reads and scenario/coherence read steps —
so every node kind in the read algebra (identities, comparisons, string/null/
membership, boolean + group, result-shaping, narrow, the nested value-object
family, navigation, deep fetch, and the temporal wrappers) round-trips through
the canonical single-key encoding. Structural rejection branches are pinned too.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from _support.corpus import case_document
from parallax.conformance import case_format
from parallax.core import op_algebra
from parallax.core.op_algebra import OperationError


def _operations() -> list[tuple[str, dict[str, Any]]]:
    """Every authored operation in the read algebra (aggregation deferred, out of claim)."""
    found: list[tuple[str, dict[str, Any]]] = []
    for case in case_format.load_cases():
        when: Any = case_document(case).get("when") or {}
        operation: Any = when.get("operation")
        if isinstance(operation, dict) and not _has_group_by(operation):
            found.append((case.case_id, cast("dict[str, Any]", operation)))
        for key in ("scenario", "coherence"):
            steps: Any = when.get(key)
            if not isinstance(steps, list):
                continue
            for index, step in enumerate(cast("list[Any]", steps)):
                if not isinstance(step, dict):
                    continue
                inner: Any = cast("dict[str, Any]", step).get("find")
                if isinstance(inner, dict) and not _has_group_by(inner):
                    found.append((f"{case.case_id}/{key}/{index}", cast("dict[str, Any]", inner)))
    return found


def _has_group_by(operation: Any) -> bool:
    """Whether an operation tree uses the deferred aggregation node (out of claim)."""
    return "groupBy" in str(operation)


_OPERATIONS = _operations()


@pytest.mark.parametrize("case_id, doc", _OPERATIONS, ids=[c for c, _ in _OPERATIONS])
def test_operation_serde_round_trip(case_id: str, doc: dict[str, Any]) -> None:
    node = op_algebra.deserialize(doc)
    assert op_algebra.serialize(node) == doc


def test_node_round_trip_from_python() -> None:
    node = op_algebra.And(
        operands=(
            op_algebra.Comparison(op="eq", attr="Order.id", value=42),
            op_algebra.Not(operand=op_algebra.NullCheck(op="isNull", attr="Order.sku")),
        )
    )
    assert op_algebra.deserialize(op_algebra.serialize(node)) == node


def test_string_match_case_insensitive_default_omitted() -> None:
    node = op_algebra.StringMatch(op="like", attr="Order.name", value="ada")
    assert op_algebra.serialize(node) == {"like": {"attr": "Order.name", "value": "ada"}}
    node_ci = op_algebra.StringMatch(
        op="like", attr="Order.name", value="ada", case_insensitive=True
    )
    like_body = cast("dict[str, Any]", op_algebra.serialize(node_ci)["like"])
    assert like_body["caseInsensitive"] is True


def test_string_match_explicit_case_insensitive_round_trips() -> None:
    # An explicitly authored `caseInsensitive` (either `false` or `true`) round-
    # trips verbatim; an explicit `false` is NOT dropped as if omitted (same class
    # as the orderBy direction fix — m-op-algebra serialize(deserialize(op)) == op).
    for flag in (False, True):
        doc: dict[str, Any] = {
            "like": {"attr": "Order.name", "value": "ada", "caseInsensitive": flag}
        }
        node = op_algebra.deserialize(doc)
        assert cast("op_algebra.StringMatch", node).case_insensitive is flag
        assert op_algebra.serialize(node) == doc


def test_string_match_omitted_case_insensitive_round_trips_omitted() -> None:
    # A key that OMITS `caseInsensitive` deserializes to `None` and serializes
    # back omitted (the schema-defaulted minimal form), never gaining `false`.
    doc: dict[str, Any] = {"like": {"attr": "Order.name", "value": "ada"}}
    node = op_algebra.deserialize(doc)
    assert cast("op_algebra.StringMatch", node).case_insensitive is None
    assert op_algebra.serialize(node) == doc


def test_scoped_where_element_predicate_round_trips() -> None:
    # A nestedExists `where` is an element predicate: the nested* family over
    # ELEMENT-relative paths (`type`, `number` — no `Class.valueObject` prefix)
    # composed with boolean combinators. It round-trips through the serde.
    doc: dict[str, Any] = {
        "nestedExists": {
            "path": "Customer.address.phones",
            "where": {
                "and": {
                    "operands": [
                        {"nestedEq": {"path": "type", "value": "home"}},
                        {"nestedEq": {"path": "number", "value": "555-9999"}},
                    ]
                }
            },
        }
    }
    assert op_algebra.serialize(op_algebra.deserialize(doc)) == doc


def test_deep_fetch_path_root_narrow_round_trips() -> None:
    # The path-ROOT guard rides beside `segments` rather than on one, and the two
    # narrow positions coexist on one path: the root's `{entity, to}` and the
    # segment's `{to}` survive the round trip independently.
    doc: dict[str, Any] = {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [
                {
                    "narrow": {"entity": "Animal", "to": ["Pet"]},
                    "segments": [
                        {"rel": "Animal.owner"},
                        {"rel": "Person.pets", "narrow": {"to": ["Dog"]}},
                    ],
                }
            ],
        }
    }
    node = op_algebra.deserialize(doc)
    path = cast("op_algebra.DeepFetch", node).paths[0]
    assert path.narrow == op_algebra.PathRootNarrow(entity="Animal", to=("Pet",))
    assert path.segments[1].narrow == ("Dog",)
    assert op_algebra.serialize(node) == doc


def test_deep_fetch_path_without_a_root_narrow_round_trips_unguarded() -> None:
    # The guard is optional, so an unguarded path must come back with no `narrow`
    # key at all rather than an empty or defaulted one.
    doc: dict[str, Any] = {
        "deepFetch": {"operand": {"all": {}}, "paths": [{"segments": [{"rel": "Order.items"}]}]}
    }
    node = op_algebra.deserialize(doc)
    assert cast("op_algebra.DeepFetch", node).paths[0].narrow is None
    assert op_algebra.serialize(node) == doc


def test_order_key_authored_direction_round_trips() -> None:
    # An explicitly authored `direction` (either `asc` or `desc`) serializes back
    # verbatim (the corpus authors it explicitly on every operation orderBy key).
    for direction in ("asc", "desc"):
        doc: dict[str, Any] = {
            "orderBy": {
                "operand": {"all": {}},
                "keys": [{"attr": "Order.id", "direction": direction}],
            }
        }
        assert op_algebra.serialize(op_algebra.deserialize(doc)) == doc


def test_order_key_defaulted_direction_round_trips() -> None:
    # The schema-defaulted form (a key OMITTING the optional `direction`) must
    # round-trip omitted, not gain a `direction: asc` on the way back out.
    doc: dict[str, Any] = {"orderBy": {"operand": {"all": {}}, "keys": [{"attr": "Order.id"}]}}
    node = op_algebra.deserialize(doc)
    key = cast("op_algebra.OrderBy", node).keys[0]
    assert key.direction is None
    assert op_algebra.serialize(node) == doc


def test_order_key_authored_null_placement_round_trips() -> None:
    # Null Placement round-trips verbatim in both directions and under BOTH
    # placements — including the explicit `last`, which denotes the same order as
    # omission and must still survive as an authored value.
    for direction in ("asc", "desc"):
        for placement in ("first", "last"):
            doc: dict[str, Any] = {
                "orderBy": {
                    "operand": {"all": {}},
                    "keys": [{"attr": "Order.sku", "direction": direction, "nulls": placement}],
                }
            }
            assert op_algebra.serialize(op_algebra.deserialize(doc)) == doc


def test_order_key_omitted_null_placement_stays_distinct_from_explicit_last() -> None:
    # Omission and an explicit `last` mean the same ORDER but are distinct
    # authorings: the omitted form deserializes to `None` and serializes back
    # omitted, so canonical round-trip never manufactures the default.
    omitted: dict[str, Any] = {
        "orderBy": {"operand": {"all": {}}, "keys": [{"attr": "Order.sku", "direction": "desc"}]}
    }
    node = op_algebra.deserialize(omitted)
    key = cast("op_algebra.OrderBy", node).keys[0]
    assert key.nulls is None
    assert op_algebra.serialize(node) == omitted
    assert key.nulls_last().nulls == "last"


def test_order_key_null_placement_is_single_shot() -> None:
    key = op_algebra.OrderKey(attr="Order.sku", direction="desc")
    assert key.nulls_first().nulls == "first"
    with pytest.raises(ValueError, match="single-shot"):
        key.nulls_first().nulls_last()


@pytest.mark.parametrize(
    "doc, message",
    cast(
        "list[tuple[object, str]]",
        [
            (["not-a-mapping"], "must be a mapping"),
            ({"eq": {}, "notEq": {}}, "exactly one key"),
            ({"eq": "not-a-mapping"}, "body must be a mapping"),
            ({"mystery": {}}, "unknown operation node"),
            ({"eq": {"attr": 1, "value": 2}}, "must be a string"),
            ({"in": {"attr": "Order.id", "values": []}}, "non-empty list"),
            ({"and": {"operands": [{"all": {}}]}}, "at least two"),
            ({"limit": {"operand": {"all": {}}, "count": 0}}, "positive integer"),
            ({"orderBy": {"operand": {"all": {}}, "keys": []}}, "non-empty list"),
            ({"narrow": {"entity": "Animal", "to": [], "operand": {"all": {}}}}, "non-empty list"),
            ({"not": {}}, "missing required key"),
            # Closed-shape / required-property / type enforcement (m-op-algebra
            # serde MUST validate every node in operation.schema.json unchanged).
            ({"all": {"junk": 1}}, r"all: unexpected key\(s\) \['junk'\]"),
            ({"eq": {"attr": "Order.id"}}, r"eq: missing required key\(s\) \['value'\]"),
            ({"eq": {"attr": "Order.id", "value": 1, "x": 2}}, r"eq: unexpected key\(s\) \['x'\]"),
            (
                {"like": {"attr": "Order.name", "value": "ada", "caseInsensitive": "yes"}},
                "`caseInsensitive` must be a boolean",
            ),
            (
                {"narrow": {"entity": "Animal", "to": [1, 2], "operand": {"all": {}}}},
                "`to` entries must be strings",
            ),
            (
                {"orderBy": {"operand": {"all": {}}, "keys": [{"attr": "Order.id", "x": 1}]}},
                r"orderBy key: unexpected key\(s\) \['x'\]",
            ),
            (
                {
                    "orderBy": {
                        "operand": {"all": {}},
                        "keys": [{"attr": "Order.sku", "nulls": "l"}],
                    }
                },
                "`nulls` must be 'first' or 'last'",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [{"segments": [{"rel": "Order.items"}], "x": 1}],
                    }
                },
                r"deepFetch path: unexpected key\(s\) \['x'\]",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [[{"rel": "Order.items"}]],
                    }
                },
                "each path must be a mapping",
            ),
            (
                {"deepFetch": {"operand": {"all": {}}, "paths": [{"segments": []}]}},
                "each path `segments` must be a non-empty list",
            ),
            (
                {"deepFetch": {"operand": {"all": {}}, "paths": []}},
                "`paths` must be a non-empty list",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [{"segments": [{"rel": "Order.items", "x": 1}]}],
                    }
                },
                r"deepFetch path segment: unexpected key\(s\) \['x'\]",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [
                            {
                                "segments": [
                                    {"rel": "Order.items", "narrow": {"to": ["Dog"], "x": 1}}
                                ]
                            }
                        ],
                    }
                },
                r"deepFetch path narrow: unexpected key\(s\) \['x'\]",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [
                            {
                                "narrow": {"entity": "Animal", "to": ["Dog"], "x": 1},
                                "segments": [{"rel": "Animal.owner"}],
                            }
                        ],
                    }
                },
                r"deepFetch path root narrow: unexpected key\(s\) \['x'\]",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [
                            {"narrow": ["Dog"], "segments": [{"rel": "Animal.owner"}]},
                        ],
                    }
                },
                "path `narrow` must be a mapping",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [
                            {
                                "narrow": {"entity": "bad name", "to": ["Dog"]},
                                "segments": [{"rel": "Animal.owner"}],
                            }
                        ],
                    }
                },
                "not a valid entity name",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [
                            {
                                "narrow": {"entity": "Animal", "to": []},
                                "segments": [{"rel": "Animal.owner"}],
                            }
                        ],
                    }
                },
                "`to` must be a non-empty list",
            ),
            # Reference-pattern enforcement (operation.schema.json $defs): each
            # reference string must match the schema pattern for its position.
            (
                {"eq": {"attr": "not a ref", "value": 1}},
                "not a valid attribute reference",
            ),
            (
                {"navigate": {"rel": "BadRel"}},
                "not a valid relationship reference",
            ),
            (
                {"narrow": {"entity": "bad name", "to": ["Dog"], "operand": {"all": {}}}},
                "not a valid entity name",
            ),
            (
                {"narrow": {"entity": "Animal", "to": ["dog!"], "operand": {"all": {}}}},
                "not a valid entity name",
            ),
            (
                {"nestedEq": {"path": "notdotted", "value": 1}},
                "not a valid nested reference",
            ),
            (
                {"nestedExists": {"path": "Customer"}},
                "not a valid value-object reference",
            ),
            (
                {"asOf": {"operand": {"all": {}}, "dimension": "bad", "coordinate": "latest"}},
                "must be 'validTime' or 'transactionTime'",
            ),
            # Temporal coordinates are non-empty. ``now`` is not a wire value:
            # a finite current-clock coordinate is serialized as its instant.
            (
                {
                    "asOf": {
                        "operand": {"all": {}},
                        "dimension": "transactionTime",
                        "coordinate": "",
                    }
                },
                "`coordinate` must be a non-empty temporal value",
            ),
            (
                {
                    "asOfRange": {
                        "operand": {"all": {}},
                        "dimension": "transactionTime",
                        "start": "",
                        "end": "2020-01-01T00:00:00Z",
                    }
                },
                "`start` must be a non-empty temporal value",
            ),
            (
                {
                    "asOfRange": {
                        "operand": {"all": {}},
                        "dimension": "transactionTime",
                        "start": "2020-01-01T00:00:00Z",
                        "end": "",
                    }
                },
                "`end` must be a non-empty temporal value",
            ),
            (
                {
                    "asOf": {
                        "operand": {"all": {}},
                        "dimension": "transactionTime",
                        "coordinate": "now",
                    }
                },
                "must be a canonical coordinate",
            ),
            (
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [{"segments": [{"rel": "bad rel"}]}],
                    }
                },
                "not a valid relationship reference",
            ),
            (
                {"orderBy": {"operand": {"all": {}}, "keys": [{"attr": "bad attr"}]}},
                "not a valid attribute reference",
            ),
            # Nested `where` is the schema's `elementPredicate`: a directive, a
            # top-level predicate, or any non-element node is illegal there.
            (
                {
                    "nestedExists": {
                        "path": "Customer.address.phones",
                        "where": {"limit": {"operand": {"all": {}}, "count": 1}},
                    }
                },
                "not a legal element predicate inside a nestedExists `where`",
            ),
            (
                {
                    "nestedExists": {
                        "path": "Customer.address.phones",
                        "where": {"eq": {"attr": "Order.id", "value": 1}},
                    }
                },
                "not a legal element predicate inside a nestedExists `where`",
            ),
            # An element-scoped nested path is element-relative (no `Class.` prefix);
            # a top-level `Class.valueObject.field` reference is illegal inside `where`.
            (
                {
                    "nestedExists": {
                        "path": "Customer.address.phones",
                        "where": {"nestedEq": {"path": "Customer.address.type", "value": "home"}},
                    }
                },
                "not a valid element-relative path",
            ),
        ],
    ),
)
def test_deserialize_rejects_malformed(doc: object, message: str) -> None:
    with pytest.raises(OperationError, match=message):
        op_algebra.deserialize(doc)


def test_deserialize_rejects_non_scalar_value() -> None:
    with pytest.raises(OperationError, match="scalar literal"):
        op_algebra.deserialize({"eq": {"attr": "Order.id", "value": {"nested": 1}}})


@pytest.mark.parametrize(
    "doc",
    [
        {
            "asOf": {
                "operand": {"all": {}},
                "dimension": "transactionTime",
                "coordinate": "latest",
            }
        },
        {
            "asOf": {
                "operand": {"all": {}},
                "dimension": "transactionTime",
                "coordinate": "2020-01-01T00:00:00Z",
            }
        },
        {
            "asOfRange": {
                "operand": {"all": {}},
                "dimension": "validTime",
                "start": "2020-01-01T00:00:00Z",
                "end": "2021-01-01T00:00:00Z",
            }
        },
    ],
)
def test_temporal_pin_round_trips(doc: dict[str, Any]) -> None:
    # A canonical temporal coordinate round-trips unchanged.
    node = op_algebra.deserialize(doc)
    assert op_algebra.serialize(node) == doc
