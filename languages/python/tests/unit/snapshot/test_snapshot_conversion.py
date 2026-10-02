"""Per-row conversion into one compact projection row (m-snapshot-read).

Exercises `parallax.snapshot.materialize`'s conversion seam independently of the
Docker-gated compile/run sweeps: value-object document decoding (declared-shape
projection, the absence-collapse vocabulary, the refusal shape for stored data
that contradicts its declared type), scalar provenance, Page identity claims
(family normalization, projection independence, and the table-per-concrete-subtype
exception), and the whole converted row with its documents decoded.

Every row is a result-keyed driver row of a real compiled read, bound as a find
binds it and converted through ``PreparedRead.convert_row``. A converted row is
POSITIONAL: every applicable member occupies its declared position and ``ABSENT``
stands where the read carried nothing, so what the suite asserts of a member is
what the row holds at that member's own position.

Conversion needs no Entity Class, so the suite drives accepted models straight
from the corpus descriptors; Root View judgment and Entity construction live in
`test_materializer_publication.py`.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import pytest

from parallax.conformance import vo_models
from parallax.core import predicate as oa
from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    SQL_NULL,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Decimal,
    NeutralType,
    PresentDocument,
)
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import encode_leaf
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Pin
from parallax.descriptor._records import (
    Attribute,
    DocumentLayout,
    Entity,
    Inheritance,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.materialize import MISSING_STORED_VALUE, PageBuilder, RootView
from parallax.snapshot.materialize._page import ABSENT, LogicalKey, StoredDataIssueInput, page_rows
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._typed import typed_root
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema
from tests._support.model_capabilities import graph_construction_for
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import formed, target
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._prepared_read_support import bound_read, compiled_read
from tests.unit.snapshot._encoded_identity_read import encoded_identity_page
from tests.unit.snapshot._snapshot_page_support import (
    driver_row,
    identity_of,
    physical_members,
    rendered_occurrence,
)

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
    """One converted projection: its layout, its member row, its issues, and the
    Page identity it claimed.

    Every read below goes through the layout, because that is the whole of how a
    row is read — a position means what the layout says it means and nothing on
    the row itself says so.
    """

    layout: EntityLayout
    values: tuple[object, ...]
    issues: tuple[StoredDataIssueInput, ...]
    key: LogicalKey | None

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
        """This row's Page identity claim, as family and primary key."""
        assert self.key is not None
        return self.key.family, self.key.primary_key


def _converted(model: Metamodel, entity: str, row: Mapping[str, object]) -> _Projection:
    """``row``, spelled by result key, converted through ``entity``'s bound read."""
    return _converted_by(compiled_read(model, entity), bound_read(model, entity), row)


def _converted_by(
    compiled: CompiledRead, prepared: PreparedRead, row: Mapping[str, object]
) -> _Projection:
    builder = PageBuilder(ViewSchema.of())
    index, _resolved, _document, _variant = prepared.convert_row(
        driver_row(compiled, row), builder, source=ROOT_LEVEL
    )
    page = builder.finish((index,), Pin())
    rows = page_rows(page)
    root = RootView(page)
    return _Projection(
        rows.layouts[index],
        rows.member_rows[index] if root.roots == (None,) else root.member_values(0),
        root.invalid_roots[0].issues if root.roots == (None,) else root.issues(0),
        rows.keys[index],
    )


def _state_row(model: Metamodel, entity: str, row: dict[str, object]) -> dict[str, object]:
    projection = _converted(model, entity, row)
    return physical_members(projection.layout, projection.values)


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
    node = _converted(SCALARS, "ScalarThing", {"id": 1, "payload_hex": "0a1b"})
    assert node.member(payload.identity) == b"\x0a\x1b"

    # An undecodable scalar records its issue AND leaves its own position absent,
    # so nothing downstream reads the raw stored spelling in its place.
    invalid = _converted(SCALARS, "ScalarThing", {"id": 1, "payload_hex": "not-hex"})
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


def test_a_classified_decoding_issue_names_a_nested_leaf_and_the_value_it_rejected() -> None:
    invalid = _converted(
        DOCUMENT_CODEC,
        "Sample",
        {"id": 1, "profile": {"entries": [{"issued": "2026-13-40"}]}},
    )
    assert invalid.issues[0].code == "stored-data-leaf-undecodable"
    assert invalid.issues[0].member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(EntityIdentity(_NAMESPACE, "Sample"), ("profile", "entries")), "issued"
    )
    assert invalid.issues[0].path == ("profile", "entries", 0, "issued")
    assert invalid.issues[0].stored_value == "2026-13-40"


def test_classified_decoding_separates_two_members_that_spell_one_dotted_path() -> None:
    # `origin` holding a leaf `city.name`, and `origin.city` holding a leaf `name`,
    # render the same dotted path, so no reading of a `.`-joined spelling can tell
    # them apart. The codec reports its member as a sequence of declared names and
    # the refusal resolves it step by step, which is what makes the applicable
    # identity the one whose stored value actually failed.
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
# Page identity claims: family normalization and projection independence.       #
# Table-per-concrete-subtype remains the family-normalization exception.       #
# --------------------------------------------------------------------------- #
def test_a_logical_key_is_family_normalized_for_a_concrete_subtype() -> None:
    node = _converted(ANIMAL, "Dog", {"id": 1, "name": "Rex", "owner_id": 10, "bark_volume": 7})
    assert node.logical_key() == (EntityIdentity(_NAMESPACE, "Animal"), 1)


def test_two_projections_of_one_row_key_alike_whichever_position_reached_it() -> None:
    broad = _converted(ANIMAL, "Animal", {"id": 1, "kind": "dog", "name": "Rex", "owner_id": 10})
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
    # Page construction registers the FIRST projection carrying a key for
    # relationship correlation, which is what a back-reference level resolves against.
    # A single-column key resolves by its raw scalar, the spelling the layout's own rule gives it.
    builder = PageBuilder(ViewSchema.of())
    prepared = bound_read(ORDERS, "Order")
    first, *_ = prepared.convert_row({"id": 1, "name": "Ada"}, builder, source=ROOT_LEVEL)
    second, *_ = prepared.convert_row({"id": 1, "name": "Ada"}, builder, source=ROOT_LEVEL)
    assert first != second
    assert builder.resolve(EntityIdentity(_NAMESPACE, "Order"), 1) == first


def test_the_builder_answers_nothing_for_a_key_it_never_registered() -> None:
    assert PageBuilder(ViewSchema.of()).resolve(EntityIdentity(_NAMESPACE, "Order"), 999) is None


# --------------------------------------------------------------------------- #
# The whole converted row under physical storage keys.                          #
# --------------------------------------------------------------------------- #
def test_a_converted_row_answers_the_whole_row_with_documents_decoded() -> None:
    # A stored document is carried as its DECODED declared members — the same
    # spelling a successor's carried-versus-changed comparison reads.
    row: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": PresentDocument({"street": "1 Park Ave", "city": "Oslo"}),
    }
    columns = _state_row(CUSTOMER, "Customer", row)
    assert columns["id"] == 1
    assert columns["name"] == "Ada"
    address = cast("Mapping[str, object]", columns["address"])
    assert address["city"] == "Oslo"
    with pytest.raises(KeyError):
        columns["not-a-column"]
    with pytest.raises(KeyError):
        address["not-a-member"]
    with pytest.raises(KeyError):
        address["geo"]


def test_a_converted_row_carries_a_many_occurrence_one_row_per_element() -> None:
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
    columns = _state_row(meta, "Fleet", {"id": 1, "stops": [{"label": "a"}]})
    stops = cast("tuple[Mapping[str, object], ...]", columns["stops"])
    assert tuple(map(dict, stops)) == ({"label": "a"},)


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


@pytest.mark.parametrize("key", [None, "not-an-int"], ids=["null", "provider-representation"])
def test_a_native_requested_root_key_is_not_reclassified(key: object) -> None:
    # A native key reaches this seam only after its installed SQL type and
    # constraint have admitted it. The provider-normalized value is therefore an
    # identity claim, not fresh input to the host's scalar codec.
    builder = PageBuilder(ViewSchema.of())
    ref, *_ = bound_read(CUSTOMER, "Customer").convert_row(
        {"id": key, "name": "Ada", "address": SQL_NULL}, builder, source=ROOT_LEVEL
    )
    page = builder.finish((ref,), Pin())
    assert page_rows(page).roots == (ref,)
    view = RootView(page, 0)
    assert view.invalid_roots == ()
    (root,) = typed_root(
        view,
        CUSTOMER,
        CONCURRENCY,
        graph_construction_for(vo_models.CUSTOMER_MODEL),
    )
    assert cast("Any", root).id == key


def _named(*, document: bool) -> Metamodel:
    """One Entity whose required ``name`` is document-resident under ``document``
    and its own native Column otherwise."""
    named = Entity(
        name="Named",
        table="named",
        layout=DocumentLayout(column="payload") if document else None,
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="name", type="string", column="name"),
        ),
    )
    return formed(DescriptorMetamodel(entities=(named,)))


NAMED_DOCUMENT = _named(document=True)
NAMED_COLUMNS = _named(document=False)
_NAMED = EntityIdentity(None, "Named")


@pytest.mark.parametrize(
    ("model", "entity", "row", "code"),
    [
        pytest.param(
            NAMED_DOCUMENT,
            "Named",
            {"id": 1, "payload": {"name": None}},
            "stored-data-attribute-null",
            id="document-attribute",
        ),
    ],
)
def test_entity_attribute_findings_use_attribute_specific_issue_codes(
    model: Metamodel, entity: str, row: dict[str, object], code: str
) -> None:
    # A rejected Entity Attribute is diagnosed by the attribute's own role rather
    # than by the leaf vocabulary its carrier's codec speaks.
    node = _converted(model, entity, row)
    assert [issue.code for issue in node.issues] == [code]


def test_encoded_identifier_findings_use_the_primary_key_issue_code() -> None:
    page = encoded_identity_page({"id_wire": "not-a-key"})
    root = RootView(page)
    assert [issue.code for record in root.invalid_roots for issue in record.issues] == [
        "stored-data-primary-key-undecodable"
    ]
    assert page_rows(page).keys[0] is None


# --------------------------------------------------------------------------- #
# Evidence: the rejected value itself, and the place it was found.             #
# --------------------------------------------------------------------------- #
_CUSTOMER = EntityIdentity(_NAMESPACE, "Customer")
_ADDRESS = ValueObjectIdentity(_CUSTOMER, ("address",))
_PHONES = ValueObjectIdentity(_CUSTOMER, ("address", "phones"))


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (
            {"id": 1, "name": "Ada", "address": {"city": "Oslo"}},
            (
                "stored-data-required-member-absent",
                ValueObjectAttributeIdentity(_ADDRESS, "street"),
                ("address", "street"),
                MISSING_STORED_VALUE,
            ),
        ),
        (
            {"id": 1, "name": "Ada", "address": {"street": None, "city": "Oslo"}},
            (
                "stored-data-required-member-null",
                ValueObjectAttributeIdentity(_ADDRESS, "street"),
                ("address", "street"),
                None,
            ),
        ),
        (
            {"id": 1, "name": "Ada", "address": {"street": "1 Park Ave", "geo": "unknown"}},
            (
                "stored-data-one-wrong-kind",
                ValueObjectIdentity(_CUSTOMER, ("address", "geo")),
                ("address", "geo"),
                "unknown",
            ),
        ),
        (
            {"id": 1, "name": "Ada", "address": "not-an-object"},
            ("stored-data-one-wrong-kind", _ADDRESS, ("address",), "not-an-object"),
        ),
        (
            {
                "id": 1,
                "name": "Ada",
                "address": {"street": "1 Park Ave", "phones": {"type": "home"}},
            },
            (
                "stored-data-many-wrong-kind",
                _PHONES,
                ("address", "phones"),
                {"type": "home"},
            ),
        ),
        (
            {
                "id": 1,
                "name": "Ada",
                "address": {
                    "street": "1 Park Ave",
                    "phones": [{"type": "home", "number": "555"}, {"number": 7}],
                },
            },
            (
                "stored-data-leaf-undecodable",
                ValueObjectAttributeIdentity(_PHONES, "number"),
                ("address", "phones", 1, "number"),
                7,
            ),
        ),
    ],
    ids=[
        "member-absent",
        "member-null",
        "one-wrong-kind",
        "whole-occurrence-wrong-kind",
        "many-wrong-kind",
        "array-element-leaf",
    ],
)
def test_every_issue_carries_what_was_rejected_and_where_it_was_found(
    row: dict[str, object],
    expected: tuple[str, object, tuple[object, ...], object],
) -> None:
    # The whole vocabulary, read as one table, because the two new fields only
    # mean anything against each other: `None` is a stored null and
    # `MISSING_STORED_VALUE` a member no stored object held, an empty path is a
    # member its identity already locates exactly, and an integer segment is an
    # array position that no member identity can express. A code that carried the
    # wrong one of either would read here as an ordinary row.
    (issue,) = _converted(CUSTOMER, "Customer", row).issues
    assert (issue.code, issue.member, issue.path, issue.stored_value) == expected


def test_an_unknown_family_tag_carries_the_tag_it_could_not_resolve() -> None:
    # The same evidence contract for the one issue no member owns: the stored
    # tag itself, at no path, on the family root the row converted under.
    (issue,) = _converted(
        ANIMAL, "Animal", {"id": 1, "kind": "unicorn", "name": "Ada", "owner_id": 10}
    ).issues
    assert (issue.code, issue.member, issue.path, issue.stored_value) == (
        "stored-data-family-tag-unknown",
        None,
        (),
        "unicorn",
    )


def test_a_wrong_kind_parent_is_diagnosed_once_at_its_own_path() -> None:
    # The container is what contradicts the model; its declared members are only
    # unreachable because of it. Synthesizing an absence issue per descendant
    # would report four defects where the stored document has one, and would
    # attribute them to members whose own stored state was never seen.
    node = _converted(
        CUSTOMER,
        "Customer",
        {"id": 1, "name": "Ada", "address": {"street": "1 Park Ave", "geo": 7}},
    )
    assert [(issue.code, issue.path) for issue in node.issues] == [
        ("stored-data-one-wrong-kind", ("address", "geo"))
    ]


def test_structured_evidence_is_detached_read_only_and_recursive() -> None:
    # A `many` stored as one object is the shape that carries a whole subtree as
    # evidence, so it is where the freezing has to hold at every depth: objects
    # answer as read-only mappings, arrays as tuples, and nothing shares a
    # container with the row the value arrived on.
    phones: dict[str, object] = {"type": "home", "tags": ["primary", "voice"]}
    row: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": {"street": "1 Park Ave", "phones": phones},
    }
    (issue,) = _converted(CUSTOMER, "Customer", row).issues
    evidence = cast("Mapping[str, object]", issue.stored_value)
    assert evidence == {"type": "home", "tags": ("primary", "voice")}
    with pytest.raises(TypeError):
        cast("dict[str, object]", evidence)["type"] = "work"
    phones["type"] = "work"
    assert evidence["type"] == "home"


@pytest.mark.parametrize("view", [False, True], ids=["bytearray", "memoryview"])
def test_a_mutable_provider_carrier_is_copied_out_of_the_evidence(view: bool) -> None:
    # An encoded projection is host-checked. A driver may answer it with a buffer
    # it still owns, either directly or through a view; retained diagnostic
    # evidence must therefore be detached from that mutable carrier.
    buffer = bytearray(b"\x0a\x1b")
    carrier: object = memoryview(buffer) if view else buffer
    (issue,) = _converted(SCALARS, "ScalarThing", {"id": 1, "payload_hex": carrier}).issues
    del carrier
    buffer[0] = 0xFF
    assert issue.stored_value == b"\x0a\x1b"
    assert type(issue.stored_value) is bytes


def _diagnoses(node: _Projection) -> list[tuple[object, ...]]:
    """``node``'s issues as the whole of what each one diagnoses."""
    return [(issue.code, issue.member, issue.path, issue.stored_value) for issue in node.issues]


def test_document_codec_findings_do_not_imply_native_column_reclassification() -> None:
    # A document-resident Entity Attribute is judged by the document codec and
    # retains its diagnosis. A native Column is instead trusted after database
    # enforcement and provider normalization, so the host does not recreate the
    # same finding from its raw value.
    document = _converted(NAMED_DOCUMENT, "Named", {"id": 1, "payload": {"name": None}})
    columns = _converted(NAMED_COLUMNS, "Named", {"id": 1, "name": None})
    assert _diagnoses(document) == [
        ("stored-data-attribute-null", AttributeIdentity(_NAMED, "name"), (), None)
    ]
    assert columns.issues == ()


def _hull_family() -> Metamodel:
    """A table-per-hierarchy family whose ROOT declares an occurrence. A read
    narrowed to `Skiff` classifies that occurrence for its own position only, so
    a `Barge` row outside the position, or a row tagged for a concrete the model
    never composed, carries it unclassified."""
    hull = Entity(
        name="Hull",
        table="hull",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="profile",
                column="profile",
                nullable=True,
                attributes=(ValueObjectAttribute(name="label", type="string"),),
                value_objects=(
                    NestedValueObject(
                        name="origin",
                        nullable=True,
                        attributes=(ValueObjectAttribute(name="port", type="string"),),
                    ),
                    NestedValueObject(
                        name="marks",
                        multiplicity="many",
                        attributes=(ValueObjectAttribute(name="tag", type="string"),),
                    ),
                ),
            ),
        ),
    )
    skiff = Entity(
        name="Skiff",
        inheritance=Inheritance(role="concrete-subtype", parent="Hull", tag_value="skiff"),
        attributes=(Attribute(name="oars", type="int32", column="oars", nullable=True),),
    )
    barge = Entity(
        name="Barge",
        inheritance=Inheritance(role="concrete-subtype", parent="Hull", tag_value="barge"),
        attributes=(Attribute(name="deck", type="int32", column="deck", nullable=True),),
    )
    return formed(DescriptorMetamodel(entities=(hull, skiff, barge)))


HULL = _hull_family()
_HULL_TO_SKIFF = compile_read(
    oa.All(),
    HULL,
    POSTGRES,
    target(HULL, "Hull"),
    narrow_to=(target(HULL, "Skiff").identity,),
    result_form="instance",
)
_HULL_TO_SKIFF_READ = bind(CatalogedModel(HULL), _HULL_TO_SKIFF)


def _narrowed_hull(row: Mapping[str, object]) -> _Projection:
    return _converted_by(_HULL_TO_SKIFF, _HULL_TO_SKIFF_READ, row)


_HULL_PROFILE_LABEL = ValueObjectAttributeIdentity(
    ValueObjectIdentity(EntityIdentity(None, "Hull"), ("profile",)), "label"
)


def test_an_occurrence_no_compiled_stage_classified_decodes_as_a_classified_one_does() -> None:
    # Conversion decodes this occurrence itself, and has to answer exactly as the
    # compiled classification does: an omitted nested One contributes nothing,
    # an omitted Many is carried empty, and a leaf outside its declared type is
    # diagnosed at its own path.
    profile: dict[str, object] = {"label": "a"}
    classified = _narrowed_hull({"id": 1, "kind": "skiff", "profile": profile})
    sibling = _narrowed_hull({"id": 1, "kind": "barge", "profile": profile})
    unknown = _narrowed_hull({"id": 1, "kind": "galley", "profile": profile})
    assert (classified.concrete_entity.name, sibling.concrete_entity.name) == ("Skiff", "Barge")
    for node in (classified, sibling, unknown):
        assert _occurrence(node, "profile") == {"label": "a", "marks": ()}

    invalid = _narrowed_hull({"id": 2, "kind": "barge", "profile": {"label": 7}})
    assert _diagnoses(invalid) == [
        ("stored-data-leaf-undecodable", _HULL_PROFILE_LABEL, ("profile", "label"), 7)
    ]
    unknown_invalid = _narrowed_hull({"id": 2, "kind": "galley", "profile": {"label": 7}})
    assert _diagnoses(unknown_invalid) == [
        ("stored-data-family-tag-unknown", None, (), "galley"),
        ("stored-data-leaf-undecodable", _HULL_PROFILE_LABEL, ("profile", "label"), 7),
    ]
