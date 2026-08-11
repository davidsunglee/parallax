"""Operation-algebra node + serde unit tests (m-op-algebra).

The serde round-trip contract (`serialize(deserialize(x)) == x`) is proven over
every operation the corpus authors — reads and scenario/coherence read steps —
so every node kind in the read algebra (identities, comparisons, string/null/
membership, boolean + group, result-shaping, narrow, the nested value-object
family, navigation, deep fetch, and the temporal wrappers) round-trips through
the canonical single-key encoding. Structural rejection branches are pinned too.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, cast

import pytest

from _support.corpus import case_document
from _support.repo import REPO_ROOT
from parallax.conformance import case_format
from parallax.core import op_algebra
from parallax.core.op_algebra import (
    QUERY_DEFINITION_CODES,
    OperationError,
    QueryDefinitionError,
)


def _operations() -> list[tuple[str, dict[str, Any]]]:
    """Every authored operation in the read algebra."""
    found: list[tuple[str, dict[str, Any]]] = []
    for case in case_format.load_cases():
        when: Any = case_document(case).get("when") or {}
        operation: Any = when.get("operation")
        if isinstance(operation, dict):
            found.append((case.case_id, cast("dict[str, Any]", operation)))
        for key in ("scenario", "coherence"):
            steps: Any = when.get(key)
            if not isinstance(steps, list):
                continue
            for index, step in enumerate(cast("list[Any]", steps)):
                if not isinstance(step, dict):
                    continue
                inner: Any = cast("dict[str, Any]", step).get("find")
                if isinstance(inner, dict):
                    found.append((f"{case.case_id}/{key}/{index}", cast("dict[str, Any]", inner)))
    return found


_OPERATIONS = _operations()


@pytest.mark.parametrize("case_id, doc", _OPERATIONS, ids=[c for c, _ in _OPERATIONS])
def test_operation_serde_round_trip(case_id: str, doc: dict[str, Any]) -> None:
    node = op_algebra.deserialize(doc)
    assert op_algebra.serialize(node) == doc


_IDENTITY_DEFS = cast(
    "dict[str, Any]",
    json.loads((REPO_ROOT / "core" / "schemas" / "identity.schema.json").read_text()),
)["$defs"]


# One operation node per reference grammar, each carrying the reference under test
# at the position that grammar governs and nothing else that could fail. The
# element-relative slot is a scoped `where`'s own path, so its node fixes a valid
# outer `nestedExists` path and varies only the inner one.
_REFERENCE_POSITIONS: dict[str, Callable[[str], dict[str, Any]]] = {
    "attributeRef": lambda ref: {"eq": {"attr": ref, "value": 1}},
    "relationshipRef": lambda ref: {"exists": {"rel": ref}},
    "entityName": lambda ref: {"narrow": {"to": [ref], "operand": {"all": {}}}},
    "nestedRef": lambda ref: {"nestedEq": {"path": ref, "value": 1}},
    "valueObjectRef": lambda ref: {"nestedExists": {"path": ref}},
    "elementRef": lambda ref: {
        "nestedExists": {"path": "Order.lines", "where": {"nestedEq": {"path": ref, "value": 1}}}
    },
}

# Spellings spanning every distinction the grammars draw: bare and canonical, an
# Entity-only spelling, a member path of each depth, no Entity segment at all, the
# underscored member class the schemas admit, a lowercase Entity segment, a
# capitalized namespace segment, and two capitalized segments.
_REFERENCE_VECTORS = [
    "Order.id",
    "parallax.compatibility.Order.id",
    "Order",
    "catalog.SharedVariant",
    "Order.address.city",
    "catalog.SharedVariant.address.geo.lat",
    "address.city",
    "type",
    "Order.legacy_ID",
    "order.id",
    "Parallax.Order.id",
    "Order.Address",
]


@pytest.mark.parametrize("definition", sorted(_REFERENCE_POSITIONS))
@pytest.mark.parametrize("spelling", _REFERENCE_VECTORS)
def test_the_serde_accepts_exactly_what_the_shared_grammar_accepts(
    definition: str, spelling: str
) -> None:
    # `identity.schema.json` is the contract and the serde carries this target's
    # copy of it, so the two are pinned to the same accept set rather than merely
    # to compatible ones: they drifted once already, when the schemas gained the
    # underscored member class and the mirrors did not.
    admitted = re.fullmatch(_IDENTITY_DEFS[definition]["pattern"], spelling) is not None
    document = _REFERENCE_POSITIONS[definition](spelling)
    try:
        op_algebra.deserialize(document)
    except OperationError:
        accepted = False
    else:
        accepted = True
    assert accepted == admitted


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"eq": {"attr": "parallax.compatibility.Order.id", "value": 1}}, id="attr"),
        pytest.param({"exists": {"rel": "archive.SharedVariant.notes"}}, id="rel"),
        pytest.param(
            {
                "narrow": {
                    "to": ["archive.SharedVariant"],
                    "operand": {"all": {}},
                }
            },
            id="narrow",
        ),
        pytest.param(
            {"nestedEq": {"path": "parallax.compatibility.Customer.address.city", "value": "US"}},
            id="nested",
        ),
        pytest.param({"nestedExists": {"path": "catalog.Record.tags"}}, id="valueObject"),
        pytest.param({"eq": {"attr": "Order.legacy_ID", "value": 1}}, id="underscored-member"),
    ],
)
def test_a_canonical_or_underscored_reference_round_trips(document: dict[str, Any]) -> None:
    # The serde is structural: it re-emits the spelling it read, so accepting the
    # canonical form at every reference position is the whole of what the widened
    # mirrors buy. Which Entity the spelling names is resolution's question.
    assert op_algebra.serialize(op_algebra.deserialize(document)) == document


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


def test_nested_range_and_negated_membership_round_trip_in_both_scopes() -> None:
    # `nestedBetween` / `nestedNotIn` carry the SAME wire tag in both scopes — the
    # element `$def`s differ only in which body their `path` points at — so one pair
    # of node classes serves both, distinguished by the path grammar alone.
    path_scoped: dict[str, Any] = {
        "and": {
            "operands": [
                {
                    "nestedBetween": {
                        "path": "Customer.address.geo.elevation",
                        "lower": 5,
                        "upper": 12,
                    }
                },
                {"nestedNotIn": {"path": "Customer.address.city", "values": ["Oslo"]}},
            ]
        }
    }
    element_scoped: dict[str, Any] = {
        "nestedExists": {
            "path": "Customer.address.phones",
            "where": {
                "and": {
                    "operands": [
                        {"nestedBetween": {"path": "number", "lower": "555-9000", "upper": "5"}},
                        {"nestedNotIn": {"path": "type", "values": ["work"]}},
                    ]
                }
            },
        }
    }
    for doc in (path_scoped, element_scoped):
        assert op_algebra.serialize(op_algebra.deserialize(doc)) == doc


def test_nested_negated_membership_keeps_its_own_tag_through_serialization() -> None:
    # One `NestedMembership` class carries both tags, so a lost `op` would silently
    # serialize `nestedNotIn` back as `nestedIn` — the same predicate with the
    # opposite meaning.
    node = op_algebra.deserialize(
        {"nestedNotIn": {"path": "Customer.address.city", "values": ["Oslo"]}}
    )
    assert cast("op_algebra.NestedMembership", node).op == "nestedNotIn"
    assert next(iter(op_algebra.serialize(node))) == "nestedNotIn"


def test_nested_string_predicates_round_trip_in_both_scopes() -> None:
    # The five string tags are spelled identically in both scopes, so the single
    # scope-flagged dispatcher parses them from one body table and one node class.
    path_scoped: dict[str, Any] = {
        "and": {
            "operands": [
                {"nestedLike": {"path": "Customer.address.city", "value": "Os%"}},
                {"nestedNotLike": {"path": "Customer.address.city", "value": "B%"}},
                {"nestedStartsWith": {"path": "Customer.address.street", "value": "1 "}},
                {"nestedEndsWith": {"path": "Customer.address.street", "value": "Ave"}},
                {
                    "nestedContains": {
                        "path": "Customer.address.geo.country",
                        "value": "N",
                        "caseInsensitive": True,
                    }
                },
            ]
        }
    }
    element_scoped: dict[str, Any] = {
        "nestedExists": {
            "path": "Customer.address.phones",
            "where": {
                "and": {
                    "operands": [
                        {"nestedLike": {"path": "number", "value": "555-%"}},
                        {"nestedNotLike": {"path": "number", "value": "555-9999"}},
                        {"nestedStartsWith": {"path": "type", "value": "ho"}},
                        {"nestedEndsWith": {"path": "number", "value": "9999"}},
                        {"nestedContains": {"path": "geo.country", "value": "N"}},
                    ]
                }
            },
        }
    }
    for doc in (path_scoped, element_scoped):
        assert op_algebra.serialize(op_algebra.deserialize(doc)) == doc


def test_nested_string_predicate_keeps_its_own_tag_and_omitted_case_flag() -> None:
    # One `NestedStringMatch` class carries all five tags, so a lost `op` would
    # silently serialize `nestedNotLike` back as `nestedLike` — the complement. The
    # omitted `caseInsensitive` stays omitted and an explicit `false` round-trips,
    # exactly as the scalar `StringMatch` does.
    node = op_algebra.deserialize(
        {"nestedNotLike": {"path": "Customer.address.city", "value": "B"}}
    )
    assert cast("op_algebra.NestedStringMatch", node).op == "nestedNotLike"
    assert cast("op_algebra.NestedStringMatch", node).case_insensitive is None
    assert next(iter(op_algebra.serialize(node))) == "nestedNotLike"
    explicit: dict[str, Any] = {
        "nestedLike": {"path": "Customer.address.city", "value": "B", "caseInsensitive": False}
    }
    assert op_algebra.serialize(op_algebra.deserialize(explicit)) == explicit


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
    # narrow positions coexist on one path: the root's `{to}` and the
    # segment's `{to}` survive the round trip independently.
    doc: dict[str, Any] = {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [
                {
                    "narrow": {"to": ["Pet"]},
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
    assert path.narrow == ("Pet",)
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
    with pytest.raises(QueryDefinitionError, match="single-shot") as caught:
        key.nulls_first().nulls_last()
    assert caught.value.code == "query-expression-invalid"


_QUERY_SPEC_CODES = frozenset(
    {
        "query-target-mismatch",
        "query-expression-invalid",
        "query-path-invalid",
        "query-clause-invalid",
        "query-assignment-invalid",
        "query-assignment-target-mismatch",
        "query-not-mutation-compatible",
    }
)


def test_the_query_definition_code_set_is_exactly_the_seven_spec_codes() -> None:
    assert QUERY_DEFINITION_CODES == _QUERY_SPEC_CODES
    assert len(QUERY_DEFINITION_CODES) == 7


def test_a_code_outside_the_closed_query_set_cannot_be_raised() -> None:
    with pytest.raises(ValueError, match="not a query definition code") as caught:
        QueryDefinitionError(code="query-made-up", message="nope")
    assert not isinstance(caught.value, QueryDefinitionError)


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
            ({"narrow": {"to": [], "operand": {"all": {}}}}, "non-empty list"),
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
                {"narrow": {"to": [1, 2], "operand": {"all": {}}}},
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
                        "keys": [{"attr": "Order.sku", "direction": "up"}],
                    }
                },
                "`direction` must be 'asc' or 'desc'",
            ),
            (
                {"orderBy": {"operand": {"all": {}}, "keys": ["Order.sku"]}},
                "each key must be a mapping",
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
                                "narrow": {"to": ["Dog"], "x": 1},
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
                                "narrow": {"to": ["bad name"]},
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
                                "narrow": {"to": []},
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
                {"narrow": {"entity": "Animal", "to": ["Dog"], "operand": {"all": {}}}},
                r"narrow: unexpected key\(s\) \['entity'\]",
            ),
            (
                {"narrow": {"to": ["dog!"], "operand": {"all": {}}}},
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
                "must be 'valid-time' or 'transaction-time'",
            ),
            # Temporal coordinates are non-empty. ``now`` is not a wire value:
            # a finite current-clock coordinate is serialized as its instant.
            (
                {
                    "asOf": {
                        "operand": {"all": {}},
                        "dimension": "transaction-time",
                        "coordinate": "",
                    }
                },
                "`coordinate` must be a non-empty temporal value",
            ),
            (
                {
                    "asOfRange": {
                        "operand": {"all": {}},
                        "dimension": "transaction-time",
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
                        "dimension": "transaction-time",
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
                        "dimension": "transaction-time",
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
            (
                {
                    "nestedExists": {
                        "path": "Customer.address.phones",
                        "where": {
                            "nestedBetween": {
                                "path": "Customer.address.geo.elevation",
                                "lower": 1,
                                "upper": 2,
                            }
                        },
                    }
                },
                "not a valid element-relative path",
            ),
            (
                {"nestedBetween": {"path": "Customer.address.city", "lower": "a"}},
                r"missing required key\(s\) \['upper'\]",
            ),
            (
                {"nestedNotIn": {"path": "Customer.address.city", "values": []}},
                "`values` must be a non-empty list",
            ),
            (
                {"nestedStartsWith": {"path": "Customer.address.city", "value": 42}},
                "`value` must be a string",
            ),
            (
                {
                    "nestedContains": {
                        "path": "Customer.address.city",
                        "value": "a",
                        "caseInsensitive": "yes",
                    }
                },
                "`caseInsensitive` must be a boolean",
            ),
            (
                {
                    "nestedExists": {
                        "path": "Customer.address.phones",
                        "where": {"nestedLike": {"path": "Customer.address.city", "value": "Os%"}},
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
                "dimension": "transaction-time",
                "coordinate": "latest",
            }
        },
        {
            "asOf": {
                "operand": {"all": {}},
                "dimension": "transaction-time",
                "coordinate": "2020-01-01T00:00:00Z",
            }
        },
        {
            "asOfRange": {
                "operand": {"all": {}},
                "dimension": "valid-time",
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


def test_deserialize_canonicalizes_include_paths_before_serialization() -> None:
    short: dict[str, Any] = {"segments": [{"rel": "Order.items"}]}
    maximal: dict[str, Any] = {
        "segments": [
            {"rel": "Order.items"},
            {"rel": "OrderItem.statuses"},
        ]
    }
    statuses: dict[str, Any] = {"segments": [{"rel": "Order.statuses"}]}
    doc: dict[str, Any] = {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [statuses, short, maximal, maximal],
        }
    }

    assert op_algebra.serialize(op_algebra.deserialize(doc)) == {
        "deepFetch": {"operand": {"all": {}}, "paths": [maximal, statuses]}
    }


def test_serialize_canonicalizes_directly_constructed_include_paths() -> None:
    short = op_algebra.NavigationPath(segments=(op_algebra.PathSegment(rel="Order.items"),))
    maximal = op_algebra.NavigationPath(
        segments=(
            op_algebra.PathSegment(rel="Order.items"),
            op_algebra.PathSegment(rel="OrderItem.statuses"),
        )
    )
    statuses = op_algebra.NavigationPath(segments=(op_algebra.PathSegment(rel="Order.statuses"),))
    node = op_algebra.DeepFetch(operand=op_algebra.All(), paths=(statuses, short, maximal, maximal))

    assert op_algebra.serialize(node) == {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [
                {
                    "segments": [
                        {"rel": "Order.items"},
                        {"rel": "OrderItem.statuses"},
                    ]
                },
                {"segments": [{"rel": "Order.statuses"}]},
            ],
        }
    }
