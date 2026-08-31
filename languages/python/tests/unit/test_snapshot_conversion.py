"""Per-row conversion into one compact projection row (m-snapshot-read).

Exercises `parallax.snapshot.materialize`'s conversion seam independently of the
Docker-gated compile/run sweeps: value-object document decoding (declared-shape
projection, the absence-collapse vocabulary, the refusal shape for stored data
that contradicts its declared type), scalar provenance, graph-local identity
(family normalization, projection independence, the table-per-concrete-subtype
exception, the builder's first-writer registration), and the deliberately
physical observation extraction the write side reads.

A row is POSITIONAL: every applicable member occupies its declared position and
``ABSENT`` stands where the read carried nothing, so what the suite asserts of a
member is what the row holds at that member's own position.

Conversion needs no Entity Class, so the suite drives accepted models straight
from the corpus descriptors; the merge and construction halves live in
`test_snapshot_merge.py`.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import pytest
from _corpus_model_support import formed
from _corpus_model_support import model as corpus_model
from _snapshot_graph_support import (
    documents_of,
    identity_of,
    invalid_record,
    layout_of,
    rendered_occurrence,
)

from parallax.conformance import vo_models
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
    PresentDocument,
)
from parallax.core.document_codec import DocumentFinding, encode_leaf
from parallax.core.entity import graph_construction_of
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.sql_gen._compile import AttributeReadContract
from parallax.core.temporal_read import Pin
from parallax.descriptor._records import (
    Attribute,
    Entity,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.handle._materializer import materialize_graph
from parallax.snapshot.materialize import (
    InvalidRootInput,
    StoredDataIssueInput,
    observable_columns,
)
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import ABSENT, GraphBuilder, graph_rows
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

ORDERS = corpus_model("orders")
ANIMAL = corpus_model("animal")
CUSTOMER = corpus_model("customer")
DOCUMENT = corpus_model("document")
DOCUMENT_CODEC = corpus_model("document-codec")
SCALARS = corpus_model("scalars")

_NAMESPACE = "parallax.compatibility"


type _Record = Mapping[str, object]
"""One occurrence's member row, rendered by declared name for an assertion."""


@dataclass(frozen=True, slots=True)
class _Projection:
    """One converted projection: its layout, its member row, and its issues.

    Every read below goes through the layout, because that is the whole of how a
    row is read — a position means what the layout says it means and nothing on
    the row itself says so.
    """

    layout: EntityLayout
    values: tuple[object, ...]
    issues: tuple[StoredDataIssueInput, ...]

    @property
    def concrete_entity(self) -> EntityIdentity:
        return self.layout.concrete

    @property
    def carried(self) -> set[str]:
        """The Attribute positions this row holds a value at, by declared name."""
        return {
            attribute.identity.name
            for position, attribute in enumerate(self.layout.attributes)
            if self.values[position] is not ABSENT
        }

    def declaring(self, name: str) -> EntityIdentity:
        """Which position declares the Attribute this row carries under ``name``."""
        return next(
            attribute.identity.entity
            for attribute in self.layout.attributes
            if attribute.identity.name == name
        )

    def member(self, identity: AttributeIdentity) -> object:
        """``identity``'s value by position, or ``ABSENT`` where the row holds none."""
        position = self.layout.index_of.get(identity)
        return ABSENT if position is None else self.values[position]

    def logical_key(self) -> tuple[EntityIdentity, object]:
        """This row's graph-local identity, exactly as the builder derives one."""
        return self.layout.family, self.layout.key_of(self.values)


def _context(model: Metamodel, entity: str) -> LevelContext:
    identity = identity_of(model, entity)
    return LevelContext(layout_of(model, identity), documents_of(model, identity))


def _converted(
    model: Metamodel, entity: str, row: dict[str, object], **provenance: Any
) -> _Projection:
    builder = GraphBuilder(ViewSchema.of())
    index = convert_row(row, _context(model, entity), builder, source=ROOT_LEVEL, **provenance)
    rows = graph_rows(builder.seal((index,), Pin()))
    return _Projection(rows.layouts[index], rows.member_rows[index], rows.issues[index])


def _projection(context: LevelContext, row: dict[str, object]) -> _Projection:
    """One row converted under a caller-built level context."""
    builder = GraphBuilder(ViewSchema.of())
    index = convert_row(row, context, builder, source=ROOT_LEVEL)
    rows = graph_rows(builder.seal((index,), Pin()))
    return _Projection(rows.layouts[index], rows.member_rows[index], rows.issues[index])


def _occurrence(node: _Projection, name: str) -> Any:
    """One converted occurrence's value, rendered by declared name.

    The rendering IS the positional walk the materializer and the wire lane each
    make over a member row, so a name absent from it is a position the row holds
    ``ABSENT`` at.
    """
    position, declared = next(
        (position, occurrence)
        for position, occurrence in enumerate(
            node.layout.occurrences, start=node.layout.attribute_count
        )
        if occurrence.identity.path[-1] == name
    )
    return rendered_occurrence(node.values[position], declared)


def _leaf(record: _Record, name: str) -> object:
    return record[name]


def _nested(record: _Record, name: str) -> Any:
    return record[name]


def _names(record: _Record) -> set[str]:
    return set(record)


# --------------------------------------------------------------------------- #
# The level context is a value keyed by the level it converts.                 #
# --------------------------------------------------------------------------- #
def test_a_level_context_is_hashable_and_keyed_by_the_level_it_converts() -> None:
    # The layout is a function of the model and the concrete Entity, so it
    # distinguishes no two contexts and stays out of equality: two contexts over
    # one level are one value however each reached its layout, and the context
    # keeps the hashability its remaining fields give it.
    order = _context(ORDERS, "Order")
    again = _context(ORDERS, "Order")
    assert order.layout is not again.layout
    assert order == again
    assert hash(order) == hash(again)
    assert {order, again} == {order}
    assert order != _context(ORDERS, "OrderItem")


# --------------------------------------------------------------------------- #
# Scalar provenance: physical columns become Attribute Identities, and only    #
# columns this concrete actually declares contribute.                          #
# --------------------------------------------------------------------------- #
def test_a_scalar_column_becomes_its_own_attribute_identity() -> None:
    node = _converted(ORDERS, "Order", {"id": 1, "name": "Ada"})
    assert node.carried == {"id", "name"}
    assert node.member(AttributeIdentity(EntityIdentity(_NAMESPACE, "Order"), "id")) == 1


def test_an_encoded_projection_key_decodes_into_its_logical_attribute() -> None:
    identity = identity_of(SCALARS, "ScalarThing")
    entity = SCALARS.entity(identity)
    assert entity is not None
    payload = entity.attribute("payload")
    assert payload is not None
    context = LevelContext(
        layout_of(SCALARS, identity),
        (),
        (
            AttributeReadContract(
                identity=payload.identity,
                column="payload",
                result_key="payload_hex",
                type=payload.type,
                nullable=payload.nullable,
                temporal_end=False,
                encoded=True,
            ),
        ),
    )
    node = _projection(context, {"payload_hex": "0a1b"})
    assert node.member(payload.identity) == b"\x0a\x1b"

    # An undecodable scalar records its issue AND leaves its own position absent,
    # so nothing downstream reads the raw stored spelling in its place.
    invalid = _projection(context, {"payload_hex": "not-hex"})
    assert [issue.code for issue in invalid.issues] == ["stored-data-leaf-undecodable"]
    assert invalid.member(payload.identity) is ABSENT


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
    assert node.carried == {"id", "name", "ownerId", "licenseId", "barkVolume"}


def test_an_inherited_attribute_reaches_a_concrete_under_its_declaring_identity() -> None:
    node = _converted(ANIMAL, "Dog", {"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7})
    assert node.declaring("name") == EntityIdentity(_NAMESPACE, "Animal")


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
    address = cast("_Record", _occurrence(node, "address"))
    assert _leaf(address, "street") == "1 Park Ave"
    geo = cast("_Record", _nested(address, "geo"))
    assert _leaf(geo, "country") == "NO"
    point = cast("_Record", _nested(geo, "point"))
    assert (_leaf(point, "lat"), _leaf(point, "lon")) == (1.0, 2.0)
    phones = cast("tuple[_Record, ...]", _nested(address, "phones"))
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
    profile = cast("_Record", _occurrence(node, "profile"))
    assert _leaf(profile, "amount") == decimal.Decimal("10.25")
    assert _leaf(profile, "blob") == b"\x0a\x1b"
    assert _leaf(profile, "day") == dt.date(2026, 1, 15)
    assert _leaf(profile, "clock") == dt.time(9, 30)
    assert _leaf(profile, "instant") == dt.datetime(2026, 1, 15, 9, 30, tzinfo=dt.UTC)
    assert _leaf(profile, "token") == uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
    entries = cast("tuple[_Record, ...]", _nested(profile, "entries"))
    assert _leaf(entries[0], "price") == decimal.Decimal("19.99")
    assert _leaf(entries[0], "issued") == dt.date(2026, 2, 1)


def test_a_present_leaf_outside_its_declared_type_is_classified_where_absence_collapses() -> None:
    # The two halves of one boundary. A member the document DOES supply in a state
    # the model has — a JSON null, an occurrence of the wrong kind — collapses to
    # null / () as the read predicates do (m-predicate), and a member it supplies
    # not at all reads `ABSENT` at its own position, which is how the row keeps the
    # document's own presence. A leaf that IS supplied and decodes into no member of its
    # declared value space is a state the model does not have: it is invalid stored
    # data (m-document-codec), so conversion records an issue instead of retaining
    # the raw stored value.
    node = _converted(
        DOCUMENT_CODEC,
        "Sample",
        {
            "id": 3,
            "label": "Cyd",
            "profile": {"small": None, "origin": "unknown", "entries": "not-an-array"},
        },
    )
    profile = cast("_Record", _occurrence(node, "profile"))
    assert _leaf(profile, "small") is None
    assert "amount" not in _names(profile)
    assert _nested(profile, "origin") is None
    assert _nested(profile, "entries") == ()

    invalid = _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"amount": "bogus"}})
    assert invalid.issues[0].code == "stored-data-leaf-undecodable"
    assert invalid.issues[0].entity == EntityIdentity(_NAMESPACE, "Sample")
    assert invalid.issues[0].member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(_NAMESPACE, "Sample"), ("profile",)), "amount"
    )


def test_a_classified_decoding_issue_names_a_nested_leaf_and_exposes_no_stored_value() -> None:
    invalid = _converted(
        DOCUMENT_CODEC,
        "Sample",
        {"id": 1, "profile": {"entries": [{"issued": "2026-13-40"}]}},
    )
    assert invalid.issues[0].code == "stored-data-leaf-undecodable"
    assert invalid.issues[0].member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(_NAMESPACE, "Sample"), ("profile", "entries")), "issued"
    )


def test_classified_decoding_separates_two_members_that_spell_one_dotted_path() -> None:
    # `origin` holding a leaf `city.name`, and `origin.city` holding a leaf `name`,
    # render the same dotted path, so no reading of a `.`-joined spelling can tell
    # them apart. The codec reports its member as a sequence of declared names and
    # the refusal resolves it step by step, which is what makes the applicable
    # identity (`python.md` §3) the one whose stored value actually failed.
    entity = Entity(
        name="Twin",
        table="twin",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="profile",
                column="profile",
                value_objects=(
                    NestedValueObject(
                        name="origin",
                        attributes=(ValueObjectAttribute(name="city.name", type="int32"),),
                    ),
                    NestedValueObject(
                        name="origin.city",
                        attributes=(ValueObjectAttribute(name="name", type="int32"),),
                    ),
                ),
            ),
        ),
    )
    model = formed(DescriptorMetamodel(entities=(entity,)))
    invalid = _converted(model, "Twin", {"id": 1, "profile": {"origin": {"city.name": "bogus"}}})
    assert invalid.issues[0].member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(None, "Twin"), ("profile", "origin")), "city.name"
    )

    sibling = _converted(model, "Twin", {"id": 1, "profile": {"origin.city": {"name": "bogus"}}})
    sibling_issue = next(
        issue for issue in sibling.issues if issue.code == "stored-data-leaf-undecodable"
    )
    assert sibling_issue.member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(None, "Twin"), ("profile", "origin.city")), "name"
    )


def test_classified_decoding_resolves_a_leaf_whose_own_name_carries_a_dot() -> None:
    # Only an Entity name is dot-free; a member name is any nonempty string
    # (m-metamodel "Canonical identities and order"). The codec reports the failing
    # member as a sequence of declared names, so resolving it by splitting a
    # rendered path on every separator would find no such leaf and report the
    # containing occurrence instead — a `ValueObjectIdentity` where the applicable
    # identity is the leaf's own.
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
    model = formed(DescriptorMetamodel(entities=(entity,)))
    invalid = _converted(model, "Dotted", {"id": 1, "profile": {"amount.v1": "bogus"}})
    assert invalid.issues[0].member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(None, "Dotted"), ("profile",)), "amount.v1"
    )


def test_numeric_member_names_remain_distinct_from_array_positions() -> None:
    entity = Entity(
        name="NumericNames",
        table="numeric_names",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="0",
                column="zero",
                attributes=(ValueObjectAttribute(name="12", type="int32"),),
            ),
        ),
    )
    model = formed(DescriptorMetamodel(entities=(entity,)))
    invalid = _converted(model, "NumericNames", {"id": 1, "zero": {"12": "wrong"}})
    assert invalid.issues[0].member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(None, "NumericNames"), ("0",)), "12"
    )


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
def test_a_stored_leaf_that_is_not_the_tables_own_spelling_is_classified(
    member: str, stored: object
) -> None:
    # Every Neutral Type has exactly ONE document spelling, and for the six
    # text-compared ones those characters are what SQL compares and orders by. Each
    # row here decodes into its declared value space and is still a DIFFERENT document
    # from the one a writer of the same value stores, so converting it would hand a
    # caller a value whose own row no predicate over that member finds.
    invalid = _converted(
        DOCUMENT_CODEC, "Sample", {"id": 1, "label": "Ada", "profile": {member: stored}}
    )
    assert invalid.issues[0].code == "stored-data-leaf-undecodable"
    assert isinstance(invalid.issues[0].member, ValueObjectAttributeIdentity)
    assert invalid.issues[0].member.name == member


def test_an_integral_float_leaf_answers_the_same_whichever_rendering_carries_it() -> None:
    # `20` and `20.0` are one JSON number, so validity cannot turn on which of them
    # the parser handed back as an `int` and which as a `float`. `2**24 + 1` names a
    # value binary32 does not hold in either rendering, so both are invalid stored
    # data rather than the silently rounded `16777216.0` a narrow-first reader gives.
    for rendering in (2**24 + 1, float(2**24 + 1)):
        invalid = _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"ratio": rendering}})
        assert invalid.issues[0].code == "stored-data-leaf-undecodable"
        assert isinstance(invalid.issues[0].member, ValueObjectAttributeIdentity)
        assert invalid.issues[0].member.name == "ratio"
    for rendering in (20, 20.0):
        node = _converted(DOCUMENT_CODEC, "Sample", {"id": 1, "profile": {"ratio": rendering}})
        assert _leaf(cast("_Record", _occurrence(node, "profile")), "ratio") == 20.0


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
    record = cast("_Record", _occurrence(node, "profile"))
    for name, _neutral, value in _SAMPLE_LEAVES:
        assert _leaf(record, name) == value


def test_an_undeclared_stored_key_never_contributes() -> None:
    node = _converted(
        CUSTOMER,
        "Customer",
        {"id": 1, "name": "Ada", "address": {"street": "x", "city": "y", "zip": "0"}},
    )
    assert "zip" not in _names(cast("_Record", _occurrence(node, "address")))


def test_a_null_top_level_document_collapses_to_an_absent_occurrence() -> None:
    node = _converted(CUSTOMER, "Customer", {"id": 4, "name": "Mary", "address": None})
    assert _occurrence(node, "address") is None


def test_an_omitted_nested_one_contributes_nothing_while_an_omitted_many_is_carried_empty() -> None:
    # Presence is the stored document's own fact, so a key it never held reaches
    # the row as `ABSENT` at its own position rather than as a value holding the
    # collapse. The writer's carriers are synthesized from the row by skipping
    # exactly those positions, which is what keeps the member outside the frozen
    # value's `model_fields_set`, so re-serializing the occurrence cannot spell an
    # omission as an explicit null. What a caller READS for such a member is
    # still `None`; that collapse belongs to construction and is pinned where the
    # frozen value is built.
    #
    # `phones` is the position that rule does not reach: a `many` has no absent
    # state, so an omitted key is one of its three zero spellings and the value
    # carries it as the empty collection (`m-snapshot-read`). This decode is the
    # fallback one — no member of the row arrives preclassified — and it has to
    # answer exactly as the classified row transform does.
    node = _converted(
        CUSTOMER, "Customer", {"id": 5, "name": "Kavi", "address": {"street": "x", "city": "y"}}
    )
    address = cast("_Record", _occurrence(node, "address"))
    assert _names(address) == {"street", "city", "phones"}
    assert _nested(address, "phones") == ()


def test_a_nested_occurrence_stored_in_a_kind_it_forbids_collapses_while_present() -> None:
    # The complement: the document DOES hold these keys, in a kind their
    # multiplicity does not admit. Absence collapse resolves the value — `None`
    # for a One, `()` for a Many — and presence is unaffected, so invalid storage
    # can never read back as an omission.
    node = _converted(
        CUSTOMER,
        "Customer",
        {
            "id": 3,
            "name": "Grace",
            "address": {"street": "x", "city": "y", "geo": "unknown", "phones": "not-an-array"},
        },
    )
    address = cast("_Record", _occurrence(node, "address"))
    assert _nested(address, "geo") is None
    assert _nested(address, "phones") == ()


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
    meta = formed(DescriptorMetamodel(entities=(entity,)))
    node = _converted(meta, "Fleet", {"id": 1, "stops": [{"label": "a"}, {"label": "b"}]})
    stops = cast("tuple[_Record, ...]", _occurrence(node, "stops"))
    assert [_leaf(stop, "label") for stop in stops] == ["a", "b"]


# --------------------------------------------------------------------------- #
# Graph-local identity: family normalization, projection independence, and the #
# table-per-concrete-subtype exception.                                        #
# --------------------------------------------------------------------------- #
def test_a_logical_key_is_family_normalized_for_a_concrete_subtype() -> None:
    node = _converted(ANIMAL, "Dog", {"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7})
    assert node.logical_key() == (EntityIdentity(_NAMESPACE, "Animal"), 1)


def test_two_projections_of_one_row_key_alike_whichever_position_reached_it() -> None:
    broad = _converted(ANIMAL, "Animal", {"id": 1, "name": "Rex", "owner_id": 10})
    narrowed = _converted(ANIMAL, "Dog", {"id": 1, "name": "Rex", "owner_id": 10})
    assert broad.logical_key() == narrowed.logical_key()


def test_a_non_participant_keys_by_its_own_identity() -> None:
    node = _converted(ORDERS, "Order", {"id": 1, "name": "Ada"})
    assert node.logical_key() == (EntityIdentity(_NAMESPACE, "Order"), 1)


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
    assert invoice.logical_key() == (EntityIdentity(_NAMESPACE, "Invoice"), 1)


def test_a_narrowed_abstract_read_and_a_direct_concrete_read_key_alike() -> None:
    # A table-per-concrete-subtype position resolving to exactly one concrete
    # emits no `familyVariant` column at all (`m-sql`'s `_compile_tpcs_single`);
    # the compiled read still names the resolved concrete, which is what keeps
    # the two routes' keys identical.
    narrowed = _converted(DOCUMENT, "Invoice", _INVOICE_ROW)
    direct = _converted(DOCUMENT, "Invoice", dict(_INVOICE_ROW))
    assert narrowed.logical_key() == direct.logical_key()


def test_a_key_less_entity_never_forms() -> None:
    # The accepted Metamodel requires a standalone Entity to declare exactly one
    # primary-key Attribute (m-metamodel `metamodel-primary-key-missing`), so a
    # key-less entity never reaches conversion at all — the layout's own refusal
    # for one guards a model no formation accepts.
    entity = Entity(
        name="NoPk", table="no_pk", attributes=(Attribute(name="x", type="int64", column="x"),)
    )
    with pytest.raises(MetamodelValidationError, match="metamodel-primary-key-missing"):
        formed(DescriptorMetamodel(entities=(entity,)))


def test_the_builder_registers_the_first_projection_of_a_logical_key() -> None:
    # Graph-local identity resolution names the FIRST projection registered for a
    # key, which is what a back-reference level resolves against. A single-column
    # key resolves by its raw scalar, the spelling the layout's own rule gives it.
    builder = GraphBuilder(ViewSchema.of())
    context = _context(ORDERS, "Order")
    first = convert_row({"id": 1, "name": "Ada"}, context, builder, source=ROOT_LEVEL)
    second = convert_row({"id": 1, "name": "Ada"}, context, builder, source=ROOT_LEVEL)
    assert first != second
    assert builder.resolve(EntityIdentity(_NAMESPACE, "Order"), 1) == first


def test_the_builder_answers_nothing_for_a_key_it_never_registered() -> None:
    assert GraphBuilder(ViewSchema.of()).resolve(EntityIdentity(_NAMESPACE, "Order"), 999) is None


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
        "address": PresentDocument({"street": "1 Park Ave", "city": "Oslo"}),
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
    meta = formed(DescriptorMetamodel(entities=(entity,)))
    columns = observable_columns({"id": 1, "stops": [{"label": "a"}]}, _context(meta, "Fleet"))
    assert columns["stops"] == [{"label": "a"}]


def test_observable_columns_rekeys_and_decodes_an_encoded_scalar_projection() -> None:
    identity = identity_of(SCALARS, "ScalarThing")
    entity = SCALARS.entity(identity)
    assert entity is not None
    payload = entity.attribute("payload")
    assert payload is not None
    context = LevelContext(
        layout_of(SCALARS, identity),
        (),
        (
            AttributeReadContract(
                identity=payload.identity,
                column="payload",
                result_key="payload_hex",
                type=payload.type,
                nullable=payload.nullable,
                temporal_end=False,
                encoded=True,
            ),
        ),
    )
    assert observable_columns({"payload_hex": "0a1b"}, context) == {"payload": b"\x0a\x1b"}


def test_observable_columns_preserves_an_already_classified_document_occurrence() -> None:
    managed = {
        "amount": decimal.Decimal("10.25"),
        "blob": b"\x0a\x1b",
        "day": dt.date(2026, 1, 15),
        "clock": dt.time(9, 30),
        "instant": dt.datetime(2026, 1, 15, 9, 30, tzinfo=dt.UTC),
        "token": uuid.UUID("123e4567-e89b-12d3-a456-426614174000"),
    }
    columns = observable_columns(
        {"id": 1, "profile": managed},
        _context(DOCUMENT_CODEC, "Sample"),
        classified_members=frozenset({"profile"}),
    )
    assert columns["profile"] == managed


def test_a_whole_document_stored_in_a_kind_it_cannot_be_read_as_names_the_occurrence() -> None:
    # This is an invalid One occurrence inside the Entity document, so the
    # occurrence itself owns the finding.
    invalid = _converted(CUSTOMER, "Customer", {"id": 1, "name": "Ada", "address": "not-an-object"})
    assert {issue.code for issue in invalid.issues} == {"stored-data-one-wrong-kind"}
    assert invalid.issues[0].member == ValueObjectIdentity(
        EntityIdentity(_NAMESPACE, "Customer"), ("address",)
    )


def test_a_member_the_read_did_not_carry_is_absent_rather_than_null() -> None:
    # A positional row cannot omit, so the distinction omission used to carry is
    # spelled: the member the read never projected reads ABSENT, and a nullable
    # member the row stored NULL at reads None. Both name no child row, which is
    # why a gathered correlation key still skips each.
    unread = _converted(ORDERS, "OrderItem", {"id": 11})
    stored_null = _converted(ORDERS, "OrderItem", {"id": 11, "shipped_on": None})
    shipped = AttributeIdentity(EntityIdentity(_NAMESPACE, "OrderItem"), "shippedOn")
    assert unread.member(shipped) is ABSENT
    assert stored_null.member(shipped) is None
    assert "shippedOn" not in unread.carried
    assert "shippedOn" in stored_null.carried


@pytest.mark.parametrize(
    ("row", "code"),
    [
        ({"id": None, "name": "Ada"}, "stored-data-primary-key-null"),
        ({"id": "not-an-int", "name": "Ada"}, "stored-data-primary-key-undecodable"),
    ],
)
def test_an_invalid_requested_root_key_is_non_hydrating(row: dict[str, object], code: str) -> None:
    builder = GraphBuilder(ViewSchema.of())
    ref = convert_row(row, _context(CUSTOMER, "Customer"), builder, source=ROOT_LEVEL)
    graph = builder.seal((ref,), Pin())
    root = graph_rows(graph).roots[0]
    assert isinstance(root, InvalidRootInput)
    assert root.issues[0].code == code
    (root,) = materialize_graph(
        graph,
        CUSTOMER,
        graph_construction_of(vo_models.CUSTOMER_MODEL),
    )
    published = invalid_record(root)
    assert published.data is None
    assert published.object_key is None
    assert {issue.code for issue in published.issues} == {code}


def test_direct_attribute_null_and_unknown_family_tag_become_projection_issues() -> None:
    node = _converted(CUSTOMER, "Customer", {"id": 1, "name": None}, family_tag_unknown=True)
    assert [issue.code for issue in node.issues] == [
        "stored-data-family-tag-unknown",
        "stored-data-attribute-null",
    ]


@pytest.mark.parametrize(
    ("finding", "code"),
    [
        (
            DocumentFinding("leaf-undecodable", ("id",)),
            "stored-data-primary-key-undecodable",
        ),
        (DocumentFinding("required-member-null", ("name",)), "stored-data-attribute-null"),
    ],
)
def test_entity_document_findings_use_attribute_specific_issue_codes(
    finding: DocumentFinding, code: str
) -> None:
    node = _converted(CUSTOMER, "Customer", {"id": 1, "name": "Ada"}, findings=(finding,))
    assert node.issues[0].code == code
