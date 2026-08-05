"""Per-row conversion into Snapshot Graph Input (m-snapshot-read).

Exercises `parallax.snapshot.materialize`'s conversion seam independently of the
Docker-gated compile/run sweeps: value-object document decoding (declared-shape
projection, the absence-collapse vocabulary, the refusal shape for stored data
that contradicts its declared type), scalar provenance, graph-local identity
(family normalization, projection independence, the table-per-concrete-subtype
exception, the scope's first-writer registration), and the deliberately physical
observation extraction the write side reads.

Conversion needs no Entity Class, so the suite drives accepted models straight
from the corpus descriptors; the merge and construction halves live in
`test_snapshot_merge.py`.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any, cast

import pytest
from _snapshot_graph_support import documents_of, identity_of

from parallax.conformance import models
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
from parallax.core.document_codec import encode_leaf
from parallax.core.entity import ValueObjectRecord
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.descriptor._records import (
    Attribute,
    Entity,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.materialize import (
    LevelContext,
    MergeScope,
    SnapshotDecodingError,
    SnapshotNodeInput,
    attribute_value,
    convert_row,
    logical_key,
    observable_columns,
)

_MODELS = models.load_models()
ORDERS = models.accepted_model(_MODELS["orders"])
ANIMAL = models.accepted_model(_MODELS["animal"])
CUSTOMER = models.accepted_model(_MODELS["customer"])
DOCUMENT = models.accepted_model(_MODELS["document"])
DOCUMENT_CODEC = models.accepted_model(_MODELS["document-codec"])

_NAMESPACE = "parallax.compatibility"


def _context(model: Metamodel, entity: str) -> LevelContext:
    identity = identity_of(model, entity)
    return LevelContext(identity, documents_of(model, identity))


def _converted(model: Metamodel, entity: str, row: dict[str, object]) -> SnapshotNodeInput:
    scope = MergeScope(model)
    return scope.node(convert_row(row, _context(model, entity), scope))


def _occurrence(node: SnapshotNodeInput, name: str) -> Any:
    """One converted occurrence's value, typed loosely for record assertions."""
    return next(entry.value for entry in node.value_objects if entry.identity.path[-1] == name)


def _leaf(record: ValueObjectRecord, name: str) -> object:
    return next(entry.value for entry in record.attributes if entry.identity.name == name)


def _nested(record: ValueObjectRecord, name: str) -> Any:
    return next(entry.value for entry in record.value_objects if entry.identity.path[-1] == name)


def _names(record: ValueObjectRecord) -> set[str]:
    return {entry.identity.name for entry in record.attributes} | {
        entry.identity.path[-1] for entry in record.value_objects
    }


# --------------------------------------------------------------------------- #
# Scalar provenance: physical columns become Attribute Identities, and only    #
# columns this concrete actually declares contribute.                          #
# --------------------------------------------------------------------------- #
def test_a_scalar_column_becomes_its_own_attribute_identity() -> None:
    node = _converted(ORDERS, "Order", {"id": 1, "name": "Ada"})
    assert {entry.identity.name for entry in node.attributes} == {"id", "name"}
    assert attribute_value(node, AttributeIdentity(EntityIdentity(_NAMESPACE, "Order"), "id")) == 1


def test_a_sibling_column_and_the_synthetic_family_tag_contribute_nothing() -> None:
    # A table-per-hierarchy row arrives null-padded with every sibling's own
    # columns, and the compiled read hands the resolved concrete separately. Only
    # what `Dog` declares in its own family reaches a member here — `indoor` is
    # `Cat`'s, and `familyVariant` is nobody's.
    node = _converted(
        ANIMAL,
        "Dog",
        {
            "id": 1,
            "name": "Rex",
            "owner_id": 10,
            "license_id": "L-100",
            "bark_volume": 7,
            "indoor": None,
            "familyVariant": "Dog",
        },
    )
    assert {entry.identity.name for entry in node.attributes} == {
        "id",
        "name",
        "ownerId",
        "licenseId",
        "barkVolume",
    }


def test_an_inherited_attribute_reaches_a_concrete_under_its_declaring_identity() -> None:
    node = _converted(ANIMAL, "Dog", {"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7})
    owners = [
        entry.identity.entity.name for entry in node.attributes if entry.identity.name == "name"
    ]
    assert owners == ["Animal"]


# --------------------------------------------------------------------------- #
# Value-object document decoding (m-value-object "Materialization and          #
# navigation contract").                                                       #
# --------------------------------------------------------------------------- #
def test_a_recursive_value_object_converts_to_records_at_every_depth() -> None:
    node = _converted(
        CUSTOMER,
        "Customer",
        {
            "id": 1,
            "name": "Ada",
            "address": {
                "street": "1 Park Ave",
                "city": "Oslo",
                "geo": {"country": "NO", "elevation": 10.5, "point": {"lat": 1.0, "lon": 2.0}},
                "phones": [{"type": "home", "number": "555"}],
            },
        },
    )
    address = cast("ValueObjectRecord", _occurrence(node, "address"))
    assert _leaf(address, "street") == "1 Park Ave"
    geo = cast("ValueObjectRecord", _nested(address, "geo"))
    assert _leaf(geo, "country") == "NO"
    point = cast("ValueObjectRecord", _nested(geo, "point"))
    assert (_leaf(point, "lat"), _leaf(point, "lon")) == (1.0, 2.0)
    phones = cast("tuple[ValueObjectRecord, ...]", _nested(address, "phones"))
    assert [_leaf(phone, "number") for phone in phones] == ["555"]


def test_every_nested_leaf_decodes_by_its_declared_neutral_type() -> None:
    # A document stores the codec's portable spelling and a converted member is
    # the MANAGED value that spelling encodes, at every depth. Six of the twelve
    # rows differ between the two — the ones models/customer.yaml does not reach —
    # so copying the stored value through would hand a caller a `str` wherever the
    # model declares a `Decimal`, `bytes`, `date`, `time`, `datetime`, or `UUID`.
    node = _converted(
        DOCUMENT_CODEC,
        "Sample",
        {
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
        },
    )
    profile = cast("ValueObjectRecord", _occurrence(node, "profile"))
    assert _leaf(profile, "amount") == decimal.Decimal("10.25")
    assert _leaf(profile, "blob") == b"\x0a\x1b"
    assert _leaf(profile, "day") == dt.date(2026, 1, 15)
    assert _leaf(profile, "clock") == dt.time(9, 30)
    assert _leaf(profile, "instant") == dt.datetime(2026, 1, 15, 9, 30, tzinfo=dt.UTC)
    assert _leaf(profile, "token") == uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
    entries = cast("tuple[ValueObjectRecord, ...]", _nested(profile, "entries"))
    assert _leaf(entries[0], "price") == decimal.Decimal("19.99")
    assert _leaf(entries[0], "issued") == dt.date(2026, 2, 1)


def test_a_present_leaf_outside_its_declared_type_fails_where_absence_still_collapses() -> None:
    # The two halves of one boundary. A member the document does not supply is a
    # presence state the model HAS — a missing key, a JSON null, an occurrence of the
    # wrong kind — and collapses to null / () as the read predicates do (m-op-algebra).
    # A leaf that IS supplied and decodes into no member of its declared value space is
    # a state the model does not have: it is invalid stored data (m-document-codec), so
    # it raises here instead of reaching a caller as the raw stored value.
    node = _converted(
        DOCUMENT_CODEC,
        "Sample",
        {
            "id": 3,
            "label": "Cyd",
            "profile": {"small": None, "origin": "unknown", "entries": "not-an-array"},
        },
    )
    profile = cast("ValueObjectRecord", _occurrence(node, "profile"))
    assert _leaf(profile, "small") is None
    assert _leaf(profile, "amount") is None
    assert _nested(profile, "origin") is None
    assert _nested(profile, "entries") == ()

    with pytest.raises(SnapshotDecodingError) as refusal:
        _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"amount": "bogus"}})
    assert refusal.value.code == "snapshot-decoding-failed"
    assert refusal.value.entity == EntityIdentity(_NAMESPACE, "Sample")
    assert refusal.value.member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(_NAMESPACE, "Sample"), ("profile",)), "amount"
    )
    assert "Sample.profile.amount" in str(refusal.value)


def test_a_decoding_refusal_names_a_nested_leaf_and_exposes_no_stored_value() -> None:
    with pytest.raises(SnapshotDecodingError) as refusal:
        _converted(
            DOCUMENT_CODEC,
            "Sample",
            {"id": 1, "profile": {"entries": [{"issued": "2026-13-40"}]}},
        )
    assert refusal.value.member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(_NAMESPACE, "Sample"), ("profile", "entries")), "issued"
    )
    assert "Sample.profile.entries.issued" in str(refusal.value)
    # The value that provoked it stays on the chained cause, never in the message.
    assert "2026-13-40" not in str(refusal.value)
    assert "2026-13-40" in str(refusal.value.cause)


def test_a_decoding_refusal_resolves_a_leaf_whose_own_name_carries_a_dot() -> None:
    # Only an Entity name is dot-free; a member name is any nonempty string
    # (m-metamodel "Canonical identities and order"). The codec reports the failing
    # member as a `.`-joined path, so resolving it by splitting on every separator
    # would find no such leaf and report the containing occurrence instead — a
    # `ValueObjectIdentity` where the applicable identity is the leaf's own.
    entity = Entity(
        name="Dotted",
        table="dotted",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="profile",
                column="profile",
                attributes=(ValueObjectAttribute(name="amount.v1", type="int32"),),
            ),
        ),
    )
    model = models.accepted_model(DescriptorMetamodel(entities=(entity,)))
    with pytest.raises(SnapshotDecodingError) as refusal:
        _converted(model, "Dotted", {"id": 1, "profile": {"amount.v1": "bogus"}})
    assert refusal.value.member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(None, "Dotted"), ("profile",)), "amount.v1"
    )
    assert "Dotted.profile.amount.v1" in str(refusal.value)


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
    # from the one a writer of the same value stores, so converting it would hand a
    # caller a value whose own row no predicate over that member finds.
    with pytest.raises(SnapshotDecodingError, match=rf"Sample\.profile\.{member}"):
        _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "label": "Ada", "profile": {member: stored}})


def test_an_integral_float_leaf_answers_the_same_whichever_rendering_carries_it() -> None:
    # `20` and `20.0` are one JSON number, so validity cannot turn on which of them
    # the parser handed back as an `int` and which as a `float`. `2**24 + 1` names a
    # value binary32 does not hold in either rendering, so both are invalid stored
    # data rather than the silently rounded `16777216.0` a narrow-first reader gives.
    for rendering in (2**24 + 1, float(2**24 + 1)):
        with pytest.raises(SnapshotDecodingError, match=r"Sample\.profile\.ratio"):
            _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"ratio": rendering}})
    for rendering in (20, 20.0):
        node = _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"ratio": rendering}})
        assert _leaf(cast("ValueObjectRecord", _occurrence(node, "profile")), "ratio") == 20.0


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


def test_every_document_the_codec_encodes_is_one_conversion_reads_back() -> None:
    # `m-snapshot-read` depends on `m-document-codec` for reduction, not for the
    # encoding table, so the claim is asserted over every declarable Neutral Type
    # and through the encoder itself rather than against a second list of
    # spellings that could drift with it.
    profile = {name: encode_leaf(neutral, value) for name, neutral, value in _SAMPLE_LEAVES}
    node = _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "label": "Ada", "profile": profile})
    record = cast("ValueObjectRecord", _occurrence(node, "profile"))
    for name, _neutral, value in _SAMPLE_LEAVES:
        assert _leaf(record, name) == value


def test_an_undeclared_stored_key_never_contributes() -> None:
    node = _converted(
        CUSTOMER,
        "Customer",
        {"id": 1, "name": "Ada", "address": {"street": "x", "city": "y", "zip": "0"}},
    )
    assert "zip" not in _names(cast("ValueObjectRecord", _occurrence(node, "address")))


def test_a_null_top_level_document_collapses_to_an_absent_occurrence() -> None:
    node = _converted(CUSTOMER, "Customer", {"id": 4, "name": "Mary", "address": None})
    assert _occurrence(node, "address") is None


@pytest.mark.parametrize(
    ("stored", "expected"),
    [({"street": "x", "city": "y"}, None), ({"street": "x", "city": "y", "geo": "unknown"}, None)],
    ids=["missing", "non-object"],
)
def test_a_missing_or_non_object_nested_one_collapses_to_none(
    stored: dict[str, object], expected: object
) -> None:
    node = _converted(CUSTOMER, "Customer", {"id": 5, "name": "Kavi", "address": stored})
    assert _nested(cast("ValueObjectRecord", _occurrence(node, "address")), "geo") is expected


@pytest.mark.parametrize(
    "stored",
    [{"street": "x", "city": "y"}, {"street": "x", "city": "y", "phones": "not-an-array"}],
    ids=["missing", "non-array"],
)
def test_a_missing_or_non_array_many_collapses_to_the_empty_tuple(
    stored: dict[str, object],
) -> None:
    node = _converted(CUSTOMER, "Customer", {"id": 3, "name": "Grace", "address": stored})
    assert _nested(cast("ValueObjectRecord", _occurrence(node, "address")), "phones") == ()


def test_a_top_level_many_cardinality_value_object_converts_to_a_record_tuple() -> None:
    # No corpus model declares a many-cardinality value object DIRECTLY on an
    # entity (every corpus `many` sits nested inside a top-level `one`, e.g.
    # Customer.address.phones) — a hand-built descriptor pins the entity-attached
    # `many` branch of conversion on its own.
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
    meta = models.accepted_model(DescriptorMetamodel(entities=(entity,)))
    node = _converted(meta, "Fleet", {"id": 1, "stops": [{"label": "a"}, {"label": "b"}]})
    stops = cast("tuple[ValueObjectRecord, ...]", _occurrence(node, "stops"))
    assert [_leaf(stop, "label") for stop in stops] == ["a", "b"]


# --------------------------------------------------------------------------- #
# Graph-local identity: family normalization, projection independence, and the #
# table-per-concrete-subtype exception.                                        #
# --------------------------------------------------------------------------- #
def test_a_logical_key_is_family_normalized_for_a_concrete_subtype() -> None:
    node = _converted(ANIMAL, "Dog", {"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7})
    assert logical_key(ANIMAL, node) == (EntityIdentity(_NAMESPACE, "Animal"), (1,))


def test_two_projections_of_one_row_key_alike_whichever_position_reached_it() -> None:
    broad = _converted(ANIMAL, "Animal", {"id": 1, "name": "Rex", "owner_id": 10})
    narrowed = _converted(ANIMAL, "Dog", {"id": 1, "name": "Rex", "owner_id": 10})
    assert logical_key(ANIMAL, broad) == logical_key(ANIMAL, narrowed)


def test_a_non_participant_keys_by_its_own_identity() -> None:
    node = _converted(ORDERS, "Order", {"id": 1, "name": "Ada"})
    assert logical_key(ORDERS, node) == (EntityIdentity(_NAMESPACE, "Order"), (1,))


_INVOICE_ROW: dict[str, object] = {
    "id": 1,
    "title": "Invoice-A",
    "folder_id": None,
    "currency": "USD",
    "amount_due": "120.00",
}


def test_table_per_concrete_subtype_keys_by_the_rows_own_concrete() -> None:
    # Each concrete owns its own physical table with its own primary-key
    # namespace (m-inheritance-109's own fixture: "Primary keys are per-table, so
    # id 1 recurs across Invoice/Receipt/Memo"), so normalizing to the family root
    # would conflate two DIFFERENT rows that merely share a key value.
    invoice = _converted(DOCUMENT, "Invoice", _INVOICE_ROW)
    assert logical_key(DOCUMENT, invoice) == (EntityIdentity(_NAMESPACE, "Invoice"), (1,))


def test_a_narrowed_abstract_read_and_a_direct_concrete_read_key_alike() -> None:
    # A table-per-concrete-subtype position resolving to exactly one concrete
    # emits no `familyVariant` column at all (`m-sql`'s `_compile_tpcs_single`);
    # the compiled read still names the resolved concrete, which is what keeps
    # the two routes' keys identical.
    narrowed = _converted(DOCUMENT, "Invoice", _INVOICE_ROW)
    direct = _converted(DOCUMENT, "Invoice", dict(_INVOICE_ROW))
    assert logical_key(DOCUMENT, narrowed) == logical_key(DOCUMENT, direct)


def test_a_key_less_entity_never_forms() -> None:
    # The accepted Metamodel requires a standalone Entity to declare exactly one
    # primary-key Attribute (m-metamodel `metamodel-primary-key-missing`), so a
    # key-less entity never reaches conversion at all — `logical_key`'s `None`
    # return for one is defensive.
    entity = Entity(
        name="NoPk", table="no_pk", attributes=(Attribute(name="x", type="int64", column="x"),)
    )
    with pytest.raises(MetamodelValidationError, match="metamodel-primary-key-missing"):
        models.accepted_model(DescriptorMetamodel(entities=(entity,)))


def test_the_scope_registers_the_first_projection_of_a_logical_key() -> None:
    # Graph-local identity resolution names the FIRST projection registered for a
    # key, which is what a back-reference level resolves against.
    scope = MergeScope(ORDERS)
    context = _context(ORDERS, "Order")
    first = convert_row({"id": 1, "name": "Ada"}, context, scope)
    second = convert_row({"id": 1, "name": "Ada"}, context, scope)
    assert first != second
    assert scope.resolve(EntityIdentity(_NAMESPACE, "Order"), (1,)) == first


def test_the_scope_answers_nothing_for_a_key_it_never_registered() -> None:
    scope = MergeScope(ORDERS)
    assert scope.resolve(EntityIdentity(_NAMESPACE, "Order"), (999,)) is None


# --------------------------------------------------------------------------- #
# The observation extraction, which is deliberately physical.                  #
# --------------------------------------------------------------------------- #
def test_observable_columns_answers_the_whole_row_with_documents_decoded() -> None:
    # A Predecessor Row is column-keyed by contract (`m-unit-work`), and the
    # document it retains carries the DECODED declared members — the same
    # spelling a successor's carried-versus-changed comparison reads.
    row: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": {"street": "1 Park Ave", "city": "Oslo"},
    }
    columns = observable_columns(row, _context(CUSTOMER, "Customer"))
    assert columns["id"] == 1
    assert columns["name"] == "Ada"
    assert cast("dict[str, Any]", columns["address"])["city"] == "Oslo"


def test_observable_columns_renders_a_many_occurrence_as_a_list() -> None:
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
    meta = models.accepted_model(DescriptorMetamodel(entities=(entity,)))
    columns = observable_columns({"id": 1, "stops": [{"label": "a"}]}, _context(meta, "Fleet"))
    assert columns["stops"] == [{"label": "a"}]


def test_a_whole_document_stored_in_a_kind_it_cannot_be_read_as_names_the_occurrence() -> None:
    # A top-level occurrence's own column holding a non-object is not an absence
    # state the model has: there is no member path to blame, so the refusal names
    # the occurrence itself.
    with pytest.raises(SnapshotDecodingError) as refusal:
        _converted(CUSTOMER, "Customer", {"id": 1, "name": "Ada", "address": "not-an-object"})
    assert refusal.value.member == ValueObjectIdentity(
        EntityIdentity(_NAMESPACE, "Customer"), ("address",)
    )


def test_a_member_a_node_carries_no_entry_for_answers_none() -> None:
    # Absent and loaded-null answer alike here, which is what every caller needs:
    # a gathered correlation key skips both.
    node = _converted(ORDERS, "Order", {"id": 1})
    assert (
        attribute_value(node, AttributeIdentity(EntityIdentity(_NAMESPACE, "Order"), "name"))
        is None
    )
