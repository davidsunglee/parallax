"""DB-free tests for the shared Entity-identity grammars (m-metamodel).

`identity.schema.json` is the single owner of every serialized Entity-identity and
member-reference grammar: `predicate.schema.json`, `subtype-selection.schema.json`,
`write-instruction.schema.json`, and `compatibility-case.schema.json` reference it
across files rather than each keeping a literal copy. These tests pin the relationship
three ways:

* the GRAMMARS themselves — what each `$def` accepts and refuses, including the
  capitalization that makes an Entity spelling separable from a member path
  (a namespace segment is lowercase, an Entity's local name is capitalized, a
  member identifier is lowercase-initial);
* CROSS-FILE equivalence — a document validates identically whether it is reached
  through the canonical `$def` or through a consuming schema's `$ref`; and
* the DELIBERATE duplication in `metamodel.schema.json`, which keeps local copies
  of three definitions instead of referencing them because it is vendored into
  language distributions and validated standalone with no registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from reference_harness.schemas import build_registry, load_schemas

_CORE = Path(__file__).resolve().parents[2] / "core"
_SCHEMAS = load_schemas(_CORE)
_REGISTRY = build_registry(_SCHEMAS)

_IDENTITY = _SCHEMAS["identity.schema.json"]
_METAMODEL = _SCHEMAS["metamodel.schema.json"]
_IDENTITY_URL = _IDENTITY["$id"]
_OPERATION_URL = _SCHEMAS["predicate.schema.json"]["$id"]
_SUBTYPE_SELECTION_URL = _SCHEMAS["subtype-selection.schema.json"]["$id"]
_WRITE_URL = _SCHEMAS["write-instruction.schema.json"]["$id"]
_CASE_URL = _SCHEMAS["compatibility-case.schema.json"]["$id"]

# Every vector is (spelling, accepted). They are shared between the grammar tests
# and the cross-file equivalence test, so a `$ref` cannot pass on a narrower corpus
# than the canonical `$def` was judged against.
_VECTORS: dict[str, list[tuple[str, bool]]] = {
    "namespaceSegment": [
        ("archive", True),
        ("parallax.compatibility", True),
        ("compat2.overlap9", True),
        ("Archive", False),  # a namespace segment never begins capitalized
        ("parallax.Compatibility", False),
        ("legacy_ns", False),  # underscores belong to the member grammar
        ("2nd", False),
        ("archive.", False),
        ("", False),
    ],
    "entityLocalName": [
        ("Order", True),
        ("SharedVariant", True),
        ("A1", True),
        ("order", False),  # an Entity's local name always begins capitalized
        ("catalog.SharedVariant", False),  # local name, so never dotted
        ("_Order", False),
        ("", False),
    ],
    "entityName": [
        ("Order", True),
        ("catalog.SharedVariant", True),
        ("parallax.compatibility.Order", True),
        ("order", False),
        ("catalog.sharedVariant", False),
        ("Catalog.SharedVariant", False),  # a capitalized namespace segment
        ("catalog.", False),
        (".Order", False),
        ("", False),
    ],
    "identifier": [
        ("id", True),
        ("customerId", True),
        ("already_snake", True),  # m-descriptor ships a defaultColumn vector for it
        ("legacy_ID", True),
        ("Id", False),
        ("2id", False),
        ("a.b", False),
        ("", False),
    ],
    "attributeRef": [
        ("Order.id", True),
        ("parallax.compatibility.Order.id", True),
        ("Order.legacy_ID", True),  # the member segment admits underscores
        ("Order", False),  # no member segment
        ("order.id", False),  # a lowercase Entity segment is an element path
        ("Order.Id", False),
        ("parallax.Compatibility.Order.id", False),
        ("Order.address.city", False),  # two member segments is a nestedRef
        ("", False),
    ],
    "relationshipRef": [
        ("Order.items", True),
        ("parallax.compatibility.Order.items", True),
        ("Order", False),
        ("order.items", False),
        ("Order.Items", False),
        ("", False),
    ],
    "nestedRef": [
        ("Customer.address.city", True),
        ("Customer.address.geo.lat", True),
        ("parallax.compatibility.Customer.address.city", True),
        ("Customer.address", False),  # an attribute leaf is required
        ("customer.address.city", False),
        ("Customer.Address.city", False),
        ("Customer.address.", False),
        ("", False),
    ],
    "valueObjectRef": [
        ("Customer.address", True),
        ("Customer.address.phones", True),
        ("parallax.compatibility.Customer.address", True),
        ("Customer", False),  # the value object member is required
        ("customer.address", False),
        ("Customer.Address", False),
        ("", False),
    ],
    "elementRef": [
        ("type", True),
        ("geo.country", True),
        ("legacy_ID", True),
        ("Customer.address", False),  # an element path carries no Entity spelling
        ("geo.Country", False),
        ("Geo.country", False),
        ("", False),
    ],
}

# Where each grammar is reached through a consuming schema's cross-file `$ref`.
_CONSUMERS: dict[str, list[tuple[str, str]]] = {
    "attributeRef": [(_OPERATION_URL, "attributeRef"), (_WRITE_URL, "writeAssignment")],
    "relationshipRef": [(_OPERATION_URL, "relationshipRef")],
    "nestedRef": [(_OPERATION_URL, "nestedRef")],
    "valueObjectRef": [(_OPERATION_URL, "valueObjectRef")],
    "elementRef": [(_OPERATION_URL, "elementRef")],
    "entityName": [
        (_SUBTYPE_SELECTION_URL, "subtypeSelection"),
        (_WRITE_URL, "entityName"),
        (_CASE_URL, "entityName"),
    ],
}

# `writeAssignment` wraps its reference in an object, so a bare spelling has to be
# lifted into the shape the consuming `$def` validates.
_WRAPPERS: dict[str, object] = {"writeAssignment": "attr"}


def _fragment_validator(schema_id_url: str, pointer: str) -> Draft202012Validator:
    """A validator whose root is a bare cross-file ``$ref`` (by absolute ``$id``)."""
    return Draft202012Validator({"$ref": f"{schema_id_url}#/$defs/{pointer}"}, registry=_REGISTRY)


def _valid(validator: Draft202012Validator, doc: Any) -> bool:
    return next(validator.iter_errors(doc), None) is None


# --- the grammars themselves ---------------------------------------------------


def test_every_identity_def_has_vectors() -> None:
    assert set(_VECTORS) == set(_IDENTITY["$defs"])


def test_each_grammar_accepts_and_refuses_its_own_vectors() -> None:
    for pointer, vectors in _VECTORS.items():
        validator = _fragment_validator(_IDENTITY_URL, pointer)
        for spelling, expected in vectors:
            assert _valid(validator, spelling) is expected, f"{pointer} {spelling!r}"


def test_an_element_path_and_a_value_object_path_are_disjoint() -> None:
    """The capitalized Entity segment is what keeps the two families apart.

    `elementRef` is the only reference family carrying no capitalized segment, so
    a splitter can decide from the text alone whether a dotted path names an
    Entity at all — which is the property the m-metamodel parse rule rests on.
    """
    element = _fragment_validator(_IDENTITY_URL, "elementRef")
    value_object = _fragment_validator(_IDENTITY_URL, "valueObjectRef")
    for spelling in ("address.city", "Customer.address"):
        assert _valid(element, spelling) is not _valid(value_object, spelling)


# --- cross-file equivalence ----------------------------------------------------


def test_each_consuming_ref_behaves_like_the_canonical_def() -> None:
    """Every consumer accepts/refuses exactly what the canonical `$def` does."""
    for pointer, consumers in _CONSUMERS.items():
        canonical = _fragment_validator(_IDENTITY_URL, pointer)
        for schema_url, consumer_pointer in consumers:
            through_ref = _fragment_validator(schema_url, consumer_pointer)
            key = _WRAPPERS.get(consumer_pointer)
            for spelling, expected in _VECTORS[pointer]:
                assert _valid(canonical, spelling) is expected
                if consumer_pointer == "subtypeSelection":
                    doc: Any = [spelling]
                else:
                    doc = spelling if key is None else {key: spelling, "value": 0}
                assert _valid(through_ref, doc) is expected, (
                    f"{schema_url}#/$defs/{consumer_pointer} {spelling!r}"
                )


def test_no_consuming_schema_redefines_an_identity_grammar() -> None:
    """The grammars live in one file; the consumers reference them."""
    owned = set(_IDENTITY["$defs"])
    for name in ("predicate.schema.json", "write-instruction.schema.json"):
        for pointer, node in _SCHEMAS[name]["$defs"].items():
            if pointer in owned:
                assert "pattern" not in node, f"{name} redefines {pointer}"
                assert node.get("$ref", "").startswith("identity.schema.json#"), (
                    f"{name} `{pointer}` must reference identity.schema.json"
                )


# --- the deliberate duplication in metamodel.schema.json -----------------------

_LOCAL_COPIES = ("namespaceSegment", "entityLocalName", "identifier")


def test_metamodel_local_copies_equal_the_shared_definitions() -> None:
    """`metamodel.schema.json` duplicates three definitions on purpose.

    It is vendored into language distributions and validated standalone with no
    registry, so it MUST NOT reach another file. The duplication is guarded here
    instead: each local copy is byte-equal to the definition it copies, so the two
    cannot drift the way the five literal `Class.member` copies once did.
    """
    for pointer in _LOCAL_COPIES:
        assert _METAMODEL["$defs"][pointer] == _IDENTITY["$defs"][pointer], pointer


def test_metamodel_schema_carries_no_cross_file_reference() -> None:
    def refs(node: Any) -> list[str]:
        if isinstance(node, dict):
            found = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
            return found + [r for value in node.values() for r in refs(value)]
        if isinstance(node, list):
            return [r for item in node for r in refs(item)]
        return []

    external = [ref for ref in refs(_METAMODEL) if not ref.startswith("#")]
    assert not external, f"metamodel.schema.json must validate standalone: {external}"


def test_entity_identity_positions_use_the_local_copies() -> None:
    entity = _METAMODEL["$defs"]["entity"]["properties"]
    assert entity["name"]["$ref"] == "#/$defs/entityLocalName"
    assert entity["namespace"]["$ref"] == "#/$defs/namespaceSegment"
