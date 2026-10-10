"""Predicate node + serde unit tests (m-predicate).

The serde round-trip contract (`serialize(deserialize(x)) == x`) is proven over
every predicate the corpus authors — the `predicate` clause of every read query
and of every scenario/coherence read step — so every node kind in the selection
grammar (constants, scalar operations over a field or a bound scalar element,
boolean + group, quantifiers, presence, and narrowing) round-trips through the
canonical single-key encoding. Structural rejection branches are pinned too.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, cast

import pytest

from parallax.conformance import case_format
from parallax.core import predicate
from parallax.core.predicate import CanonicalDocumentError, QueryDefinitionError
from parallax.core.predicate._nodes import QUERY_DEFINITION_CODES
from tests._support.corpus import case_document
from tests._support.repo import REPO_ROOT


def _predicates() -> list[tuple[str, dict[str, Any]]]:
    """The `predicate` clause of every Object Query the corpus authors."""
    found: list[tuple[str, dict[str, Any]]] = []
    for case in case_format.load_cases():
        when: Any = case_document(case).get("when") or {}
        query: Any = when.get("objectQuery")
        if isinstance(query, dict):
            found.append((case.case_id, cast("dict[str, Any]", query)["predicate"]))
        for key in ("scenario", "coherence"):
            steps: Any = when.get(key)
            if not isinstance(steps, list):
                continue
            for index, step in enumerate(cast("list[Any]", steps)):
                if not isinstance(step, dict):
                    continue
                inner: Any = cast("dict[str, Any]", step).get("objectQuery")
                if isinstance(inner, dict):
                    found.append(
                        (
                            f"{case.case_id}/{key}/{index}",
                            cast("dict[str, Any]", inner)["predicate"],
                        )
                    )
    return found


_PREDICATES = _predicates()


@pytest.mark.parametrize("case_id, doc", _PREDICATES, ids=[c for c, _ in _PREDICATES])
def test_predicate_serde_round_trip(case_id: str, doc: dict[str, Any]) -> None:
    node = predicate.deserialize(doc)
    assert predicate.serialize(node) == doc


_IDENTITY_DEFS = cast(
    "dict[str, Any]",
    json.loads((REPO_ROOT / "core" / "schemas" / "identity.schema.json").read_text()),
)["$defs"]


# One predicate node per reference position, each carrying the reference under
# test at the position that grammar governs and nothing else that could fail. A
# predicate path is Entity-qualified at the queried position and relative inside
# a scope; which one a position takes is a model-aware scope rule, so every path
# slot structurally admits either spelling.
_PATH_POSITIONS: dict[str, Callable[[str], dict[str, Any]]] = {
    "field": lambda ref: {"eq": {"path": ref, "value": 1}},
    "nullCheck": lambda ref: {"isNull": {"path": ref}},
    "quantifier": lambda ref: {"any": {"path": ref}},
    "universal": lambda ref: {"all": {"path": ref, "where": {"true": {}}}},
    "presence": lambda ref: {"notExists": {"path": ref}},
    "narrowTarget": lambda ref: {"narrow": {"path": ref, "to": ["Dog"], "operand": {"true": {}}}},
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
    "address.City",
]


def _admitted(definition: str, spelling: str) -> bool:
    return re.fullmatch(_IDENTITY_DEFS[definition]["pattern"], spelling) is not None


def _accepted(document: dict[str, Any]) -> bool:
    try:
        predicate.deserialize(document)
    except CanonicalDocumentError:
        return False
    return True


@pytest.mark.parametrize("position", sorted(_PATH_POSITIONS))
@pytest.mark.parametrize("spelling", _REFERENCE_VECTORS)
def test_every_path_slot_accepts_exactly_the_shared_path_grammars(
    position: str, spelling: str
) -> None:
    # `identity.schema.json` is the contract and the serde carries this target's
    # copy of it, so the two are pinned to the same accept set rather than merely
    # to compatible ones.
    admitted = _admitted("qualifiedPath", spelling) or _admitted("relativePath", spelling)
    assert _accepted(_PATH_POSITIONS[position](spelling)) == admitted


@pytest.mark.parametrize("spelling", _REFERENCE_VECTORS)
def test_a_subtype_alternative_accepts_exactly_the_entity_name_grammar(spelling: str) -> None:
    document: dict[str, Any] = {"narrow": {"to": [spelling], "operand": {"true": {}}}}
    assert _accepted(document) == _admitted("entityName", spelling)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"eq": {"path": "parallax.compatibility.Order.id", "value": 1}}, id="field"),
        pytest.param({"any": {"path": "archive.SharedVariant.notes"}}, id="quantifier"),
        pytest.param(
            {"narrow": {"to": ["archive.SharedVariant"], "operand": {"true": {}}}},
            id="narrow",
        ),
        pytest.param(
            {"eq": {"path": "parallax.compatibility.Customer.address.city", "value": "US"}},
            id="dotted",
        ),
        pytest.param({"exists": {"path": "catalog.Record.address"}}, id="presence"),
        pytest.param({"eq": {"path": "Order.legacy_ID", "value": 1}}, id="underscored-member"),
    ],
)
def test_a_canonical_or_underscored_reference_round_trips(document: dict[str, Any]) -> None:
    # The serde is structural: it re-emits the spelling it read. Which Entity
    # the spelling names is resolution's question.
    assert predicate.serialize(predicate.deserialize(document)) == document


def test_node_round_trip_from_python() -> None:
    node = predicate.And(
        operands=(
            predicate.Comparison(op="eq", subject=predicate.FieldSubject("Order.id"), value=42),
            predicate.Not(
                operand=predicate.NullCheck(
                    op="isNull", subject=predicate.FieldSubject("Order.sku")
                )
            ),
        )
    )
    assert predicate.deserialize(predicate.serialize(node)) == node


def test_the_constants_carry_empty_bodies() -> None:
    assert predicate.deserialize({"true": {}}) == predicate.TrueNode()
    assert predicate.deserialize({"false": {}}) == predicate.FalseNode()
    assert predicate.serialize(predicate.TrueNode()) == {"true": {}}
    assert predicate.serialize(predicate.FalseNode()) == {"false": {}}


def test_string_match_case_insensitive_default_omitted() -> None:
    node = predicate.StringMatch(
        op="like", subject=predicate.FieldSubject("Order.name"), value="ada"
    )
    assert predicate.serialize(node) == {"like": {"path": "Order.name", "value": "ada"}}
    node_ci = predicate.StringMatch(
        op="like", subject=predicate.FieldSubject("Order.name"), value="ada", case_insensitive=True
    )
    like_body = cast("dict[str, Any]", predicate.serialize(node_ci)["like"])
    assert like_body["caseInsensitive"] is True


def test_string_match_explicit_case_insensitive_round_trips() -> None:
    # An explicitly authored `caseInsensitive` (either `false` or `true`) round-
    # trips verbatim; an explicit `false` is NOT dropped as if omitted.
    for flag in (False, True):
        doc: dict[str, Any] = {
            "like": {"path": "Order.name", "value": "ada", "caseInsensitive": flag}
        }
        node = predicate.deserialize(doc)
        assert cast("predicate.StringMatch", node).case_insensitive is flag
        assert predicate.serialize(node) == doc


def test_string_match_omitted_case_insensitive_round_trips_omitted() -> None:
    # A key that OMITS `caseInsensitive` deserializes to `None` and serializes
    # back omitted (the schema-defaulted minimal form), never gaining `false`.
    doc: dict[str, Any] = {"like": {"path": "Order.name", "value": "ada"}}
    node = predicate.deserialize(doc)
    assert cast("predicate.StringMatch", node).case_insensitive is None
    assert predicate.serialize(node) == doc


def test_an_operation_without_a_path_reads_the_bound_scalar_element() -> None:
    # Every scalar operation but a null check omits `path` to read the element a
    # scalar-collection quantifier binds.
    doc: dict[str, Any] = {
        "all": {
            "path": "Order.tags",
            "where": {
                "and": {
                    "operands": [
                        {"between": {"lower": "a", "upper": "m"}},
                        {"notIn": {"values": ["b"]}},
                        {"startsWith": {"value": "a", "caseInsensitive": True}},
                        {"greaterThan": {"value": "a"}},
                    ]
                }
            },
        }
    }
    node = predicate.deserialize(doc)
    assert predicate.serialize(node) == doc
    where = cast("predicate.And", cast("predicate.Quantifier", node).where)
    assert all(
        cast("predicate.Range", operand).subject is predicate.CURRENT_SCALAR_ELEMENT
        for operand in where.operands
    )


def test_quantifiers_presence_and_a_target_local_narrow_round_trip() -> None:
    doc: dict[str, Any] = {
        "and": {
            "operands": [
                {
                    "none": {
                        "path": "Customer.address.phones",
                        "where": {"eq": {"path": "type", "value": "home"}},
                    }
                },
                {"any": {"path": "Customer.orders"}},
                {"exists": {"path": "Customer.address.geo"}},
                {
                    "narrow": {
                        "path": "Customer.favorite",
                        "to": ["Dog"],
                        "operand": {"greaterThan": {"path": "barkVolume", "value": 3}},
                    }
                },
            ]
        }
    }
    assert predicate.serialize(predicate.deserialize(doc)) == doc


def test_negated_membership_keeps_its_own_tag_through_serialization() -> None:
    # One `Membership` class carries both tags, so a lost `op` would silently
    # serialize `notIn` back as `in` — the same predicate with the opposite meaning.
    node = predicate.deserialize({"notIn": {"path": "Customer.address.city", "values": ["Oslo"]}})
    assert cast("predicate.Membership", node).op == "notIn"
    assert next(iter(predicate.serialize(node))) == "notIn"


_QUERY_SPEC_CODES = frozenset(
    {
        "query-target-mismatch",
        "query-expression-invalid",
        "query-path-invalid",
        "query-clause-invalid",
        "query-assignment-invalid",
        "query-not-mutation-compatible",
    }
)


def test_the_query_definition_code_set_is_exactly_the_six_spec_codes() -> None:
    assert QUERY_DEFINITION_CODES == _QUERY_SPEC_CODES
    assert len(QUERY_DEFINITION_CODES) == 6


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
            ({"mystery": {}}, "unknown predicate node"),
            ({"eq": {"path": 1, "value": 2}}, "must be a string"),
            ({"in": {"path": "Order.id", "values": []}}, "non-empty list"),
            ({"and": {"operands": [{"true": {}}]}}, "at least two"),
            ({"and": {"operands": "nope"}}, "at least two"),
            ({"narrow": {"to": [], "operand": {"true": {}}}}, "non-empty list"),
            ({"not": {}}, "missing required key"),
            # Closed-shape / required-property / type enforcement (m-predicate
            # serde MUST validate every node in predicate.schema.json unchanged).
            ({"true": {"junk": 1}}, r"true: unexpected key\(s\) \['junk'\]"),
            ({"eq": {"path": "Order.id"}}, r"eq: missing required key\(s\) \['value'\]"),
            ({"eq": {"path": "Order.id", "value": 1, "x": 2}}, r"eq: unexpected key\(s\) \['x'\]"),
            (
                {"like": {"path": "Order.name", "value": "ada", "caseInsensitive": "yes"}},
                "`caseInsensitive` must be a boolean",
            ),
            (
                {"narrow": {"to": [1, 2], "operand": {"true": {}}}},
                "`to` entries must be strings",
            ),
            # Reference-pattern enforcement (predicate.schema.json $defs): each
            # reference string must match the schema pattern for its position.
            (
                {"eq": {"path": "not a ref", "value": 1}},
                "not a valid predicate path",
            ),
            (
                {"narrow": {"entity": "Animal", "to": ["Dog"], "operand": {"true": {}}}},
                r"narrow: unexpected key\(s\) \['entity'\]",
            ),
            (
                {"narrow": {"to": ["dog!"], "operand": {"true": {}}}},
                "not a valid entity name",
            ),
            ({"any": {"path": "Order"}}, "not a valid predicate path"),
            ({"exists": {"path": "Order.Customer"}}, "not a valid predicate path"),
            ({"all": {"path": "Order.items"}}, r"all: missing required key\(s\) \['where'\]"),
            (
                {"exists": {"path": "Order.items", "where": {"true": {}}}},
                r"exists: unexpected key\(s\) \['where'\]",
            ),
            ({"isNull": {}}, r"isNull: missing required key\(s\) \['path'\]"),
            ({"true": {"value": True}}, r"true: unexpected key\(s\) \['value'\]"),
            ({"eq": {"attr": "Order.id", "value": 1}}, r"eq: unexpected key\(s\) \['attr'\]"),
            ({"nestedEq": {"path": "Order.address.city", "value": 1}}, "unknown predicate node"),
            ({"navigate": {"rel": "Order.customer"}}, "unknown predicate node"),
            (
                {"between": {"path": "Customer.address.city", "lower": "a"}},
                r"missing required key\(s\) \['upper'\]",
            ),
            (
                {"startsWith": {"path": "Customer.address.city", "value": 42}},
                "`value` must be a string",
            ),
        ],
    ),
)
def test_deserialize_rejects_malformed(doc: object, message: str) -> None:
    with pytest.raises(CanonicalDocumentError, match=message):
        predicate.deserialize(doc)


def test_deserialize_rejects_non_scalar_value() -> None:
    with pytest.raises(CanonicalDocumentError, match="scalar literal"):
        predicate.deserialize({"eq": {"path": "Order.id", "value": {"nested": 1}}})


def test_a_field_subject_names_a_path_and_a_universal_carries_its_where() -> None:
    with pytest.raises(ValueError, match="nonempty path"):
        predicate.FieldSubject("")
    with pytest.raises(ValueError, match="carries a `where`"):
        predicate.Quantifier("all", "Order.items")
