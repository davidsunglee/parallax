"""Snapshot graph assembler unit tests (m-snapshot-read).

Exercises `parallax.snapshot.materialize` independently of the Docker-gated
compile/run sweeps: value-object document decoding (declared-shape projection,
the absence-collapse vocabulary), graph-local identity (family normalization,
projection independence, the identity map's first-writer registration), to-
many/to-one fan-back order preservation, the empty-level attach shape, and
back-reference resolution (including the loud failure when an ancestor is
somehow missing from the identity map).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any, cast

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Decimal,
    NeutralType,
)
from parallax.core.deep_fetch import FetchLevel, LevelRef, RootRef
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import encode_leaf
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.sql_gen import compile_read
from parallax.descriptor._records import (
    Attribute,
    Entity,
    Metamodel,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.snapshot.materialize import (
    Assembler,
    MaterializeError,
    Node,
    decode_row,
    identity_key,
)


def _entity(model: Any, name: str) -> EntityMetadata:
    return next(entity for entity in model.entities if entity.identity.name == name)


_MODELS = models.load_models()
ORDERS = models.accepted_model(_MODELS["orders"])
ANIMAL = models.accepted_model(_MODELS["animal"])
CUSTOMER = models.accepted_model(_MODELS["customer"])
DOCUMENT = models.accepted_model(_MODELS["document"])
DOCUMENT_CODEC = models.accepted_model(_MODELS["document-codec"])


def _doc(decoded: dict[str, object], key: str) -> dict[str, Any]:
    """A decoded document member, typed loosely for test-side JSON-shaped
    assertions (the assembler's own `Node.fields` is intentionally a plain
    ``dict[str, object]`` — heterogeneous by design, m-snapshot-read)."""
    return cast("dict[str, Any]", decoded[key])


def _kids(node: Node, key: str) -> list[Node]:
    """A to-many relationship attachment, typed for test-side assertions."""
    return cast("list[Node]", node.relationships[key])


def _kid(node: Node, key: str) -> Node | None:
    """A to-one relationship attachment, typed for test-side assertions."""
    return cast("Node | None", node.relationships[key])


# --------------------------------------------------------------------------- #
# Value-object document decoding (m-value-object "Materialization and         #
# navigation contract").                                                      #
# --------------------------------------------------------------------------- #
def test_decode_row_passes_scalars_through_unchanged() -> None:
    row = {"id": 1, "name": "Ada"}
    assert decode_row(ORDERS, "Order", row) == row


def test_decode_row_decodes_a_recursive_value_object() -> None:
    row = {
        "id": 1,
        "name": "Ada",
        "address": {
            "street": "1 Park Ave",
            "city": "Oslo",
            "geo": {"country": "NO", "elevation": 10.5, "point": {"lat": 1.0, "lon": 2.0}},
            "phones": [{"type": "home", "number": "555"}],
        },
    }
    decoded = decode_row(CUSTOMER, "Customer", row)
    address = _doc(decoded, "address")
    geo = _doc(address, "geo")
    assert address["street"] == "1 Park Ave"
    assert geo["country"] == "NO"
    assert geo["point"] == {"lat": 1.0, "lon": 2.0}
    assert address["phones"] == [{"type": "home", "number": "555"}]


def test_decode_row_decodes_every_nested_leaf_by_its_declared_neutral_type() -> None:
    # A document stores the codec's portable spelling and a materialized member is
    # the MANAGED value that spelling encodes, at every depth. Six of the twelve
    # rows differ between the two — the ones models/customer.yaml does not reach —
    # so copying the stored value through would hand a caller a `str` wherever the
    # model declares a `Decimal`, `bytes`, `date`, `time`, `datetime`, or `UUID`.
    row = {
        "id": 1,
        "label": "Ada",
        "profile": {
            "amount": "10.25",
            "blob": "0a1b",
            "day": "2026-01-15",
            "clock": "09:30:00",
            "instant": "2026-01-15T09:30:00.000000Z",
            "token": "123e4567-e89b-12d3-a456-426614174000",
            "entries": [{"price": "19.99", "issued": "2026-02-01"}],
        },
    }
    profile = _doc(decode_row(DOCUMENT_CODEC, "Sample", row), "profile")
    assert profile["amount"] == decimal.Decimal("10.25")
    assert profile["blob"] == b"\x0a\x1b"
    assert profile["day"] == dt.date(2026, 1, 15)
    assert profile["clock"] == dt.time(9, 30)
    assert profile["instant"] == dt.datetime(2026, 1, 15, 9, 30, tzinfo=dt.UTC)
    assert profile["token"] == uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
    element = cast("list[dict[str, Any]]", profile["entries"])[0]
    assert element["price"] == decimal.Decimal("19.99")
    assert element["issued"] == dt.date(2026, 2, 1)


def test_a_present_leaf_outside_its_declared_type_fails_where_absence_still_collapses() -> None:
    # The two halves of one boundary. A member the document does not supply is a
    # presence state the model HAS — a missing key, a JSON null, an occurrence of the
    # wrong kind — and collapses to null / [] as the read predicates do (m-op-algebra).
    # A leaf that IS supplied and decodes into no member of its declared value space is
    # a state the model does not have: it is invalid stored data (m-document-codec), so
    # it raises here instead of reaching a caller as the raw stored value.
    collapsing = {
        "id": 3,
        "label": "Cyd",
        "profile": {"small": None, "origin": "unknown", "entries": "not-an-array"},
    }
    profile = _doc(decode_row(DOCUMENT_CODEC, "Sample", collapsing), "profile")
    assert profile["small"] is None
    assert profile["amount"] is None
    assert profile["origin"] is None
    assert profile["entries"] == []

    wrong_typed = {"id": 1, "label": "Ada", "profile": {"amount": "bogus"}}
    with pytest.raises(MaterializeError, match=r"profile\.amount.*invalid stored data"):
        decode_row(DOCUMENT_CODEC, "Sample", wrong_typed)

    nested = {"id": 1, "label": "Ada", "profile": {"entries": [{"issued": "2026-13-40"}]}}
    with pytest.raises(MaterializeError, match=r"profile\.entries\.issued.*invalid stored data"):
        decode_row(DOCUMENT_CODEC, "Sample", nested)


@pytest.mark.parametrize(
    ("member", "stored"),
    [
        ("amount", "10.2"),
        ("amount", 10.25),
        ("blob", "0A1B"),
        ("day", "20260115"),
        ("clock", "09:30"),
        ("instant", "2026-01-15T11:30:00+02:00"),
        ("instant", "2026-01-15T09:30:00Z"),
        ("token", "123E4567-E89B-12D3-A456-426614174000"),
        ("ratio", 1048576.3),
    ],
    ids=lambda param: repr(param),
)
def test_a_stored_leaf_that_is_not_the_tables_own_spelling_is_refused(
    member: str, stored: object
) -> None:
    # Every Neutral Type has exactly ONE document spelling, and for the six
    # text-compared ones those characters are what SQL compares and orders by. Each
    # row here decodes into its declared value space and is still a DIFFERENT document
    # from the one a writer of the same value stores, so materializing it would hand a
    # caller a value whose own row no predicate over that member finds.
    row = {"id": 1, "label": "Ada", "profile": {member: stored}}
    with pytest.raises(MaterializeError, match=rf"profile\.{member}.*invalid stored data"):
        decode_row(DOCUMENT_CODEC, "Sample", row)


def test_an_integral_float_leaf_answers_the_same_whichever_rendering_carries_it() -> None:
    # `20` and `20.0` are one JSON number, so validity cannot turn on which of them
    # the parser handed back as an `int` and which as a `float`. `2**24 + 1` names a
    # value binary32 does not hold in either rendering, so both are invalid stored
    # data rather than the silently rounded `16777216.0` a narrow-first reader gives.
    for rendering in (2**24 + 1, float(2**24 + 1)):
        with pytest.raises(MaterializeError, match=r"profile\.ratio.*invalid stored data"):
            decode_row(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"ratio": rendering}})
    for rendering in (20, 20.0):
        decoded = decode_row(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"ratio": rendering}})
        assert _doc(decoded, "profile")["ratio"] == 20.0


# One value per declarable Neutral Type, under the `document-codec` model's own
# member declaring it. Four carry a value whose document spelling is a decision rather
# than an identity — the exact digit string, the shortest float number at the declared
# width, and the UTC instant a non-UTC offset names.
_PLUS_TWO = dt.timezone(dt.timedelta(hours=2))
_SAMPLE_LEAVES: list[tuple[str, NeutralType, object]] = [
    ("flag", BOOLEAN, True),
    ("small", INT32, -7),
    ("big", INT64, 2**40),
    ("ratio", FLOAT32, 1048576.25),
    ("measure", FLOAT64, 562949953421312.25),
    ("text", STRING, "alpha"),
    ("amount", Decimal(12, 2), decimal.Decimal("1.5")),
    ("blob", BYTES, b"\x0a\x1b"),
    ("day", DATE, dt.date(2026, 1, 15)),
    ("clock", TIME, dt.time(23, 59, 59, 500000)),
    ("instant", TIMESTAMP, dt.datetime(2026, 1, 15, 11, 30, tzinfo=_PLUS_TWO)),
    ("token", UUID, uuid.UUID("123e4567-e89b-12d3-a456-426614174000")),
]


def test_every_document_the_codec_encodes_is_one_this_module_reads_back() -> None:
    # `m-snapshot-read` declares no dependency on `m-document-codec`
    # (`core/spec/modules.md`), so this module states the encoding table it recognizes
    # rather than calling the codec's. The two have to agree row for row, or a
    # document the codec writes is one this refuses — so the claim is asserted over
    # every declarable Neutral Type, and through the encoder itself rather than
    # against a second list of spellings that could drift with it.
    profile = {name: encode_leaf(neutral, value) for name, neutral, value in _SAMPLE_LEAVES}
    row = {"id": 1, "label": "Ada", "profile": profile}
    decoded = _doc(decode_row(DOCUMENT_CODEC, "Sample", row), "profile")
    for name, _neutral, value in _SAMPLE_LEAVES:
        assert decoded[name] == value


def test_decode_row_drops_undeclared_members() -> None:
    row = {"id": 1, "name": "Ada", "address": {"street": "x", "city": "y", "zip": "00000"}}
    decoded = decode_row(CUSTOMER, "Customer", row)
    assert "zip" not in _doc(decoded, "address")


def test_decode_row_null_top_level_document_collapses_to_none() -> None:
    row = {"id": 4, "name": "Mary", "address": None}
    assert decode_row(CUSTOMER, "Customer", row)["address"] is None


def test_decode_row_missing_nested_one_collapses_to_none() -> None:
    row = {"id": 5, "name": "Kavi", "address": {"street": "x", "city": "y"}}
    decoded = decode_row(CUSTOMER, "Customer", row)
    assert _doc(decoded, "address")["geo"] is None


def test_decode_row_non_object_intermediate_collapses_to_none() -> None:
    row = {"id": 6, "name": "Rin", "address": {"street": "x", "city": "y", "geo": "unknown"}}
    decoded = decode_row(CUSTOMER, "Customer", row)
    assert _doc(decoded, "address")["geo"] is None


def test_decode_row_missing_many_collapses_to_empty_list() -> None:
    row = {"id": 3, "name": "Grace", "address": {"street": "x", "city": "y"}}
    decoded = decode_row(CUSTOMER, "Customer", row)
    assert _doc(decoded, "address")["phones"] == []


def test_decode_row_non_array_many_collapses_to_empty_list() -> None:
    row = {
        "id": 9,
        "name": "Omar",
        "address": {"street": "x", "city": "y", "phones": "not-an-array"},
    }
    decoded = decode_row(CUSTOMER, "Customer", row)
    assert _doc(decoded, "address")["phones"] == []


def test_decode_row_preserves_family_variant_as_a_plain_scalar() -> None:
    row = {"id": 1, "name": "Rex", "owner_id": 10, "familyVariant": "Dog"}
    assert decode_row(ANIMAL, "Dog", row)["familyVariant"] == "Dog"


def test_decode_row_decodes_a_top_level_many_cardinality_value_object() -> None:
    # No corpus model declares a many-cardinality value object DIRECTLY on an
    # entity (every corpus `many` sits nested inside a top-level `one`, e.g.
    # Customer.address.phones) — a hand-built descriptor pins the entity-attached
    # `many` branch of `_decode_value_object` on its own.
    entity = Entity(
        name="Fleet",
        table="fleet",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="stops",
                column="stops",
                multiplicity="many",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    meta = models.accepted_model(Metamodel(entities=(entity,)))
    row = {"id": 1, "stops": [{"label": "a"}, {"label": "b"}]}
    assert decode_row(meta, "Fleet", row)["stops"] == [{"label": "a"}, {"label": "b"}]


# --------------------------------------------------------------------------- #
# Graph-local identity: family normalization, projection independence.        #
# --------------------------------------------------------------------------- #
def test_identity_key_is_family_normalized_for_a_narrowed_concrete() -> None:
    row = {"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7}
    assert identity_key(ANIMAL, "Dog", row) == (
        EntityIdentity("parallax.compatibility", "Animal"),
        (1,),
    )


def test_identity_key_matches_regardless_of_reaching_position() -> None:
    # The SAME physical row reached via "Animal" (broad) or "Dog" (narrowed)
    # resolves to the identical key — projection independence (m-snapshot-read).
    row = {"id": 1, "name": "Rex", "owner_id": 10}
    assert identity_key(ANIMAL, "Animal", row) == identity_key(ANIMAL, "Dog", row)


def test_identity_key_degrades_to_entity_name_for_a_non_participant() -> None:
    key = identity_key(ORDERS, "Order", {"id": 1})
    assert key is not None
    assert key[0] == EntityIdentity("parallax.compatibility", "Order")


def test_a_standalone_entity_without_a_primary_key_does_not_form() -> None:
    # The accepted Metamodel requires a standalone Entity to declare exactly one
    # primary-key Attribute (m-metamodel `metamodel-primary-key-missing`), so a
    # key-less entity never forms and never reaches `identity_key` — its `None`
    # return for an entity that declares no primary key is defensive.
    entity = Entity(
        name="NoPk", table="no_pk", attributes=(Attribute(name="x", type="int64", column="x"),)
    )
    with pytest.raises(MetamodelValidationError, match="metamodel-primary-key-missing"):
        models.accepted_model(Metamodel(entities=(entity,)))


# --------------------------------------------------------------------------- #
# A table-per-concrete-subtype                                                #
# ABSTRACT-position read narrowing (or naturally resolving) to exactly ONE    #
# concrete emits no `familyVariant` column (`m-sql`'s `_compile_tpcs_single`) #
# — identity must still key to the resolved CONCRETE, never the abstract     #
# queried position, matching the `familyVariant`-carrying multi-concrete     #
# case (`ddb0a54`'s identity_key rule).                                      #
# --------------------------------------------------------------------------- #
_INVOICE_ROW = {
    "id": 1,
    "title": "Invoice-A",
    "folder_id": None,
    "currency": "USD",
    "amount_due": "120.00",
}


def test_identity_key_resolves_a_narrowed_single_concrete_tpcs_position() -> None:
    # Without narrowing, the identity key would be
    # `("FinancialDocument", (1,))` — the ABSTRACT queried position — even
    # though the narrow resolves to exactly one concrete and the row carries
    # no `familyVariant` at all (the SQL legitimately omits it).
    key = identity_key(DOCUMENT, "FinancialDocument", _INVOICE_ROW, ("Invoice",))
    assert key == (EntityIdentity("parallax.compatibility", "Invoice"), (1,))


def test_identity_key_matches_a_direct_concrete_read_of_the_same_row() -> None:
    # Projection independence (m-snapshot-read): the narrowed-abstract route
    # and the direct-concrete route resolve to the identical key.
    narrowed = identity_key(DOCUMENT, "FinancialDocument", _INVOICE_ROW, ("Invoice",))
    direct = identity_key(DOCUMENT, "Invoice", _INVOICE_ROW, None)
    assert narrowed == direct == (EntityIdentity("parallax.compatibility", "Invoice"), (1,))


def test_identity_key_stays_root_normalized_when_the_narrow_still_spans_two_concretes() -> None:
    # `FinancialDocument` itself (no narrow) resolves to {Invoice, Receipt} — a
    # 2+-concrete position, so the row's OWN `familyVariant` column (never this
    # helper's fallback) is what actually decides identity there; a row that
    # (defensively) carries none degrades to the read's own queried position.
    key = identity_key(DOCUMENT, "FinancialDocument", _INVOICE_ROW, None)
    assert key == (EntityIdentity("parallax.compatibility", "FinancialDocument"), (1,))


def test_identity_key_tph_narrowed_to_one_concrete_stays_root_normalized() -> None:
    # The TPH sibling check: table-per-hierarchy ALWAYS
    # carries `familyVariant` for an abstract-target read regardless of the
    # narrow's resolved cardinality (m-inheritance-012), so `identity_key`'s
    # TPCS-only branch never even applies here — no gap to close.
    row = {"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7}
    assert identity_key(ANIMAL, "Animal", row, ("Dog",)) == (
        EntityIdentity("parallax.compatibility", "Animal"),
        (1,),
    )


# --------------------------------------------------------------------------- #
# Assembler: node construction, pk_columns.                                   #
# --------------------------------------------------------------------------- #
def test_materialize_root_builds_one_node_per_row() -> None:
    asm = Assembler(meta=ORDERS)
    nodes = asm.materialize_root("Order", [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}])
    assert [n.fields["name"] for n in nodes] == ["Ada", "Linus"]


def test_materialize_root_pk_columns_are_family_normalized() -> None:
    asm = Assembler(meta=ANIMAL)
    nodes = asm.materialize_root(
        "Dog", [{"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7}]
    )
    assert nodes[0].pk_columns == ("id",)


def test_materialize_root_threads_the_narrow_into_resolved_entity() -> None:
    # `materialize_root`'s own `narrow_to` (a find executor's
    # `~parallax.core.sql_gen.CompiledRead.narrow_to`) lets the assembler
    # recover a single-resolved-position TPCS row's own concrete even though
    # the row carries no `familyVariant` at all.
    asm = Assembler(meta=DOCUMENT)
    nodes = asm.materialize_root("FinancialDocument", [_INVOICE_ROW], narrow_to=("Invoice",))
    assert nodes[0].resolved_entity == EntityIdentity("parallax.compatibility", "Invoice")
    assert "familyVariant" not in nodes[0].fields


def test_materialize_root_decodes_documents_from_the_compiled_provenance() -> None:
    # The compiled read decides document provenance once, where the projection
    # was decided, and carries it here: the assembler decodes exactly those
    # contributors instead of re-projecting a family superset of its own, so a
    # row whose document column is absent still renders the declared shape.
    customer = models.accepted_model(_MODELS["customer"])
    compiled = compile_read(
        oa.All(), customer, POSTGRES, _entity(customer, "Customer"), result_form="instance"
    )
    assert [member.storage.name for member in compiled.documents] == ["address"]
    asm = Assembler(meta=customer)
    nodes = asm.materialize_root(
        "Customer",
        [{"id": 1, "name": "Ada", "address": {"city": "Oslo"}}],
        resolved_position=compiled.resolved_position,
        documents=compiled.documents,
    )
    assert _doc(nodes[0].value_objects, "address")["city"] == "Oslo"
    assert "address" not in nodes[0].fields


def test_materialize_root_omitted_documents_falls_back_to_the_family_projection() -> None:
    # The defensive direct-call route: an omitted `documents` reproduces the
    # Inheritance Facet projection the compiled read would have carried.
    customer = models.accepted_model(_MODELS["customer"])
    asm = Assembler(meta=customer)
    nodes = asm.materialize_root("Customer", [{"id": 1, "name": "Ada", "address": None}])
    assert nodes[0].value_objects == {"address": None}


def test_materialize_root_omitted_narrow_to_defaults_to_none() -> None:
    # Backward compatible: an omitted `narrow_to` behaves
    # exactly as before.
    asm = Assembler(meta=ORDERS)
    nodes = asm.materialize_root("Order", [{"id": 1, "name": "Ada"}])
    assert nodes[0].resolved_entity == EntityIdentity("parallax.compatibility", "Order")


# --------------------------------------------------------------------------- #
# attach_level: to-many fan-back, to-one fan-back, the empty-level shape.     #
# --------------------------------------------------------------------------- #
_ORDER_ID = AttributeIdentity(EntityIdentity("parallax.compatibility", "Order"), "id")
_ITEM_ORDER_ID = AttributeIdentity(EntityIdentity("parallax.compatibility", "OrderItem"), "orderId")


def _to_many_level(attach_key: str = "items") -> FetchLevel:
    return FetchLevel(
        attach_key=attach_key,
        to_many=True,
        parent=RootRef(),
        parent_column="id",
        parent_attribute=_ORDER_ID,
        child_target="OrderItem",
        related_attr="OrderItem.orderId",
        related_column="order_id",
        related_attribute=_ITEM_ORDER_ID,
    )


def _to_one_level(attach_key: str = "passport") -> FetchLevel:
    # Reuses OrderItem as a structurally-convenient child entity (the assembler's
    # attach logic is generic over cardinality; the entity's own semantics do
    # not matter for this unit-level fan-back proof).
    return FetchLevel(
        attach_key=attach_key,
        to_many=False,
        parent=RootRef(),
        parent_column="id",
        parent_attribute=_ORDER_ID,
        child_target="OrderItem",
        related_attr="OrderItem.orderId",
        related_column="person_id",
        related_attribute=_ITEM_ORDER_ID,
    )


def test_attach_level_fans_to_many_children_preserving_fetched_order() -> None:
    asm = Assembler(meta=ORDERS)
    parent_rows = [{"id": 1}, {"id": 2}]
    parent_nodes = asm.materialize_root("Order", parent_rows)
    child_rows = [
        {"id": 12, "order_id": 1},
        {"id": 11, "order_id": 1},
        {"id": 21, "order_id": 2},
    ]
    children = asm.attach_level(_to_many_level(), parent_nodes, parent_rows, child_rows)
    assert len(children) == 3
    assert [n.fields["id"] for n in _kids(parent_nodes[0], "items")] == [12, 11]
    assert [n.fields["id"] for n in _kids(parent_nodes[1], "items")] == [21]


def test_attach_level_to_many_no_match_attaches_empty_list() -> None:
    asm = Assembler(meta=ORDERS)
    parent_rows = [{"id": 1}]
    parent_nodes = asm.materialize_root("Order", parent_rows)
    children = asm.attach_level(_to_many_level(), parent_nodes, parent_rows, [])
    assert children == []
    assert parent_nodes[0].relationships["items"] == []


def test_attach_level_to_one_matches_a_single_node() -> None:
    asm = Assembler(meta=ORDERS)
    parent_rows = [{"id": 1}, {"id": 2}]
    parent_nodes = asm.materialize_root("Order", parent_rows)
    child_rows = [{"id": 101, "order_id": 5, "person_id": 1}]
    asm.attach_level(_to_one_level(), parent_nodes, parent_rows, child_rows)
    passport = _kid(parent_nodes[0], "passport")
    assert passport is not None
    assert passport.fields["id"] == 101
    assert _kid(parent_nodes[1], "passport") is None


def test_attach_level_empty_level_short_circuit_attaches_uniformly() -> None:
    """m-deep-fetch: an empty gathered parent-key set issues NO child query at
    all — `child_rows=None` (never an empty LIST, which would mean a query DID
    run and returned nothing) attaches the empty/null result uniformly."""
    asm = Assembler(meta=ORDERS)
    parent_rows = [{"id": 1}, {"id": 2}]
    parent_nodes = asm.materialize_root("Order", parent_rows)

    many_children = asm.attach_level(_to_many_level(), parent_nodes, parent_rows, None)
    assert many_children == []
    assert all(node.relationships["items"] == [] for node in parent_nodes)

    one_children = asm.attach_level(_to_one_level(), parent_nodes, parent_rows, None)
    assert one_children == []
    assert all(node.relationships["passport"] is None for node in parent_nodes)


# --------------------------------------------------------------------------- #
# Back-reference (ancestor-revisit) resolution.                               #
# --------------------------------------------------------------------------- #
def _back_reference_level(family: EntityIdentity, to_many: bool = False) -> FetchLevel:
    return FetchLevel(
        attach_key="order",
        to_many=to_many,
        parent=LevelRef(0),
        parent_column="order_id",
        parent_attribute=_ITEM_ORDER_ID,
        is_back_reference=True,
        back_reference_family=family,
    )


def test_back_reference_resolves_the_ancestor_already_in_the_identity_map() -> None:
    asm = Assembler(meta=ORDERS)
    root_rows = [{"id": 1}]
    root_nodes = asm.materialize_root("Order", root_rows)
    item_rows = [{"id": 11, "order_id": 1}, {"id": 12, "order_id": 1}]
    item_nodes = asm.attach_level(_to_many_level(), root_nodes, root_rows, item_rows)

    asm.attach_level(
        _back_reference_level(EntityIdentity("parallax.compatibility", "Order")),
        item_nodes,
        item_rows,
        None,
    )

    assert item_nodes[0].relationships["order"] is root_nodes[0]
    assert item_nodes[1].relationships["order"] is root_nodes[0]


def test_back_reference_null_fk_attaches_none() -> None:
    # A null correlation FK never needs an identity-map lookup at all (no
    # ancestor row exists to resolve) — attaches None directly.
    asm = Assembler(meta=ORDERS)
    item_rows = [{"id": 11, "order_id": None}]
    item_nodes = [Node(fields=dict(item_rows[0]), pk_columns=("id",))]

    asm.attach_level(
        _back_reference_level(EntityIdentity("parallax.compatibility", "Order")),
        item_nodes,
        item_rows,
        None,
    )

    assert item_nodes[0].relationships["order"] is None


def test_back_reference_raises_when_the_ancestor_is_not_registered() -> None:
    asm = Assembler(meta=ORDERS)
    orphan_rows = [{"id": 11, "order_id": 999}]
    orphan_nodes = [Node(fields=dict(orphan_rows[0]), pk_columns=("id",))]

    with pytest.raises(MaterializeError):
        asm.attach_level(
            _back_reference_level(EntityIdentity("parallax.compatibility", "Order")),
            orphan_nodes,
            orphan_rows,
            None,
        )


# --------------------------------------------------------------------------- #
# Diamond identity: independently-rendered per-view nodes still register the  #
# SAME graph-local identity (first-writer-wins) so a later back-reference      #
# resolves the SHARED node — never a lookalike copy.                          #
# --------------------------------------------------------------------------- #
def test_diamond_positions_are_independently_rendered_but_share_identity() -> None:
    asm = Assembler(meta=ORDERS)
    root_rows = [{"id": 1}]
    root_nodes = asm.materialize_root("Order", root_rows)
    shared_rows = [{"id": 11, "order_id": 1}]

    level_a = _to_many_level("items")
    level_b = _to_many_level("itemsByShipDate")
    nodes_a = asm.attach_level(level_a, root_nodes, root_rows, shared_rows)
    nodes_b = asm.attach_level(level_b, root_nodes, root_rows, shared_rows)

    # Each view renders its OWN node object (never sharing field-dict identity,
    # so a narrower/broader projection at another position never leaks in) …
    assert nodes_a[0] is not nodes_b[0]
    assert nodes_a[0].fields == nodes_b[0].fields
    # … while the identity map registers the FIRST node seen for that key,
    # available to any later back-reference targeting the same row.
    key = identity_key(ORDERS, "OrderItem", shared_rows[0])
    assert key is not None
    # White-box identity proof: reaches the assembler's own internal registry.
    assert asm._identity[key] is nodes_a[0]  # pyright: ignore[reportPrivateUsage] - unit test reads the assembler's private identity map
