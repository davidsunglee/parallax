"""Reads over a Relational Document Layout Entity (m-sql, m-storage-layout).

The one property under test is that the layout is not observable: a read of the
same members returns the same logical rows under the same result keys whichever
layout the root declares. What differs is confined to two places — the select
list projects one Structured Column instead of a column per member, and every
predicate and ordering term over a document-resident member lowers through the
`m-dialect` extraction and typed-cast seams the conventional nested vocabulary
already uses.

The model is compiled from Declarations and accepted directly
(`_document_layout_support`), which installs exactly the facets this lane reads and
nothing else, so a failure names the seam rather than whole-model formation;
everything below it is the production read lane. The corpus carries the end-to-end
proof (`models/document-layout.yaml`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable

import pytest

from parallax.core import object_query as oq
from parallax.core import predicate as oa
from parallax.core.base import SQL_NULL, DocumentValue, PresentDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import MemberShape
from parallax.core.metamodel import EntityMetadata
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._compile import CompiledRead
from tests._support.sql import compile_projected_read, compile_read, compile_write_predicate
from tests.unit._document_layout_support import columns_model, document_model, entity

DOCUMENT = document_model()
COLUMNS = columns_model()

# One person, spelled the two ways the two layouts store it. Every leaf inside
# the document carries the codec's own portable spelling, which is what a
# document-resident member reads back as before it is decoded.
_DOCUMENT_VALUE: DocumentValue = {
    "displayName": "Ada",
    "score": 7,
    "joinedOn": "2026-01-15",
    "address": {"city": "Oslo", "geo": {"country": "NO"}},
    "tags": [{"label": "founder"}],
}
_DOCUMENT_ROW = {
    "id": 1,
    "payload": PresentDocument(_DOCUMENT_VALUE),
}
_COLUMNS_ROW = {
    "id": 1,
    "display_name": "Ada",
    "score": 7,
    "joined_on": dt.date(2026, 1, 15),
    "address": PresentDocument({"city": "Oslo", "geo": {"country": "NO"}}),
    "tags": PresentDocument([{"label": "founder"}]),
}


def _where(sql: str) -> str:
    return sql.partition(" from person t0 ")[2]


def test_a_read_projects_the_structured_column_once_and_never_a_member_column() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert compiled.statement.sql == (
        "select t0.id, not t0.payload is null, t0.payload from person t0"
    )
    assert compiled.document_reads == ((1, 2),)
    # Instance form needs the same one column: the document already carries the
    # Value Object occurrences an instance additionally materializes.
    instance = compile_read(
        oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    assert instance.statement.sql == (
        "select t0.id, not t0.payload is null, t0.payload from person t0"
    )


def test_a_row_form_read_needing_no_document_member_projects_no_document_at_all() -> None:
    # `Marker` declares the layout and nothing document-resident, so outside the
    # observation lane its Structured Column exists physically and is projected by
    # nothing: the rule is keyed to the members the read was asked for.
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Marker"))
    assert compiled.statement.sql == "select t0.id from marker t0"
    assert compiled.structured_column is None


def _instance_form(target: EntityMetadata) -> CompiledRead:
    return compile_read(oa.All(), DOCUMENT, POSTGRES, target, result_form="instance")


def _widened_resolve(target: EntityMetadata) -> CompiledRead:
    return compile_projected_read(oa.All(), DOCUMENT, POSTGRES, target, include_value_objects=True)


@pytest.mark.parametrize("lane", [_instance_form, _widened_resolve], ids=["instance", "resolve"])
def test_an_observing_read_of_the_same_shape_projects_the_structured_column(
    lane: Callable[[EntityMetadata], CompiledRead],
) -> None:
    # The contrasting half: an instance-form read, and the resolving read a
    # materializing predicate write widens to every declared member, both observe the
    # stored document itself — which a Predecessor Row retains — so each projects the
    # Structured Column wherever the Table has one, however few members live inside.
    compiled = lane(entity(DOCUMENT, "Marker"))
    assert compiled.statement.sql == (
        "select t0.id, not t0.payload is null, t0.payload from marker t0"
    )
    assert compiled.structured_column == "payload"
    # The column is still never a result field: it carries no member here and the
    # raw value leaves the published row all the same.
    document: DocumentValue = {"berthCode": "NB-118"}
    row = {"id": 1, "payload": PresentDocument(document)}
    assert compiled.publication_keys(compiled.target, None) == ("id",)
    assert compiled.row_identity(row)[3] == document


def test_a_versioned_targets_narrowed_widening_still_projects_only_what_it_needs() -> None:
    # A `frozenset` widening is the versioned target's comparison-only need rather
    # than an observation, so it leaves the rule where it was: no member the read
    # asked for is document-resident, so no Structured Column is projected.
    compiled = compile_projected_read(
        oa.All(),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Marker"),
        include_value_objects=frozenset({"address"}),
    )
    assert compiled.statement.sql == "select t0.id from marker t0"


def test_a_direct_document_carrier_is_a_classified_member() -> None:
    # Under Columns layout the adapter still folds every adjacent document pair, so
    # each occurrence Column is classified rather than read as a finished value.
    compiled = compile_read(
        oa.All(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
    )
    assert compiled.classified_members(compiled.target).issuperset({"address", "tags"})


def test_raw_document_access_validates_the_resolved_member_and_folded_carrier() -> None:
    person = entity(DOCUMENT, "Person").identity
    marker = entity(DOCUMENT, "Marker").identity
    document = compile_read(
        oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )

    assert document.raw_member_of({"payload": SQL_NULL}, person, "display_name") is SQL_NULL
    display_name = document.raw_member_classifier(person, "display_name")
    assert display_name(document.raw_member_of(_DOCUMENT_ROW, person, "display_name")) == (
        "Ada",
        (),
    )
    address = document.raw_member_classifier(person, "address")
    address_value, address_findings = address(
        document.raw_member_of(_DOCUMENT_ROW, person, "address")
    )
    assert address_value == {"city": "Oslo", "geo": {"country": "NO"}}
    assert address_findings == ()

    def object_output(_shape: MemberShape, values: Iterable[object]) -> tuple[object, ...]:
        return tuple(values)

    with pytest.raises(ValueError, match="must be supplied together"):
        document.raw_member_classifier(person, "address", build_object=object_output)
    with pytest.raises(KeyError, match="missing"):
        document.raw_member_classifier(marker, "missing")
    with pytest.raises(KeyError, match="missing"):
        document.raw_member_classifier(person, "missing")
    with pytest.raises(KeyError, match="missing"):
        document.raw_member_of(_DOCUMENT_ROW, person, "missing")
    with pytest.raises(KeyError, match="missing"):
        document.raw_member_of(_DOCUMENT_ROW, marker, "missing")
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        document.raw_member_of({"payload": _DOCUMENT_VALUE}, person, "display_name")

    columns = compile_read(
        oa.All(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
    )
    classify_address = columns.raw_member_classifier(person, "address")
    assert classify_address(_COLUMNS_ROW["address"])[0] == {
        "city": "Oslo",
        "geo": {"country": "NO"},
    }
    incomplete_classifier = columns.raw_member_classifier(
        person,
        "address",
        build_object=object_output,
    )
    with pytest.raises(ValueError, match="must be supplied together"):
        incomplete_classifier(_COLUMNS_ROW["address"])
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        classify_address({"city": "Oslo"})
    with pytest.raises(KeyError, match="missing"):
        columns.raw_member_classifier(person, "missing")


def test_the_compiled_read_names_the_occurrences_a_row_can_carry_under_either_layout() -> None:
    # A Position Layout answers this from its logical MEMBER sequence, because an
    # occurrence is a member under either layout while it is a Column only under
    # `Columns` — reading its physical columns would leave a document row with no
    # occurrence to materialize at all.
    document = compile_read(
        oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    columns = compile_read(
        oa.All(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
    )
    assert [member.storage.name for member in document.documents] == ["address", "tags"]
    assert [member.storage.name for member in document.documents] == [
        member.storage.name for member in columns.documents
    ]
    assert [member.storage.name for member in document.projected_documents] == [
        "address",
        "tags",
    ]


def test_row_form_keeps_position_documents_separate_from_selected_occurrences() -> None:
    compiled = compile_read(oa.All(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"))
    assert [member.storage.name for member in compiled.documents] == ["address", "tags"]
    assert compiled.projected_documents == ()


def test_the_raw_document_is_never_a_result_field() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert "payload" not in compiled.publication_keys(compiled.target, None)


def test_row_identity_refuses_a_raw_document_outside_the_database_port_contract() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        compiled.row_identity({"id": 1, "payload": _DOCUMENT_VALUE})


def test_an_entity_document_classifies_each_requested_member() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert compiled.classified_members(compiled.target) == frozenset(
        {"display_name", "score", "joined_on"}
    )


def test_an_occurrence_only_entity_document_still_requires_a_folded_carrier() -> None:
    from parallax.descriptor._records import (
        Attribute,
        DocumentLayout,
        Entity,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )
    from tests.unit._corpus_model_support import formed

    holder = Entity(
        name="Holder",
        table="holder",
        layout=DocumentLayout(column="payload"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="profile",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    model = formed(Metamodel(entities=(holder,)))
    compiled = compile_read(
        oa.All(), model, POSTGRES, entity(model, "Holder"), result_form="instance"
    )
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        compiled.raw_member_of(
            {"id": 1, "payload": {"profile": {"label": "x"}}}, compiled.target, "profile"
        )


def test_predecessor_document_retention_requires_a_folded_carrier() -> None:
    compiled = _instance_form(entity(DOCUMENT, "Marker"))
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        compiled.row_identity({"id": 1, "payload": {}})


@pytest.mark.parametrize(
    ("predicate", "expected", "binds"),
    [
        (
            oa.Comparison(op="eq", attr="Person.displayName", value="Ada"),
            "where jsonb_extract_path_text(t0.payload, ?) = ?",
            ("displayName", "Ada"),
        ),
        (
            oa.Comparison(op="greaterThan", attr="Person.score", value=3),
            "where cast(jsonb_extract_path_text(t0.payload, ?) as bigint) > ?",
            ("score", 3),
        ),
        (
            oa.Between(attr="Person.score", lower=1, upper=9),
            "where cast(jsonb_extract_path_text(t0.payload, ?) as bigint) between ? and ?",
            ("score", 1, 9),
        ),
        (
            oa.Membership(op="in", attr="Person.score", values=(1, 2)),
            "where cast(jsonb_extract_path_text(t0.payload, ?) as bigint) in (?, ?)",
            ("score", 1, 2),
        ),
        (
            oa.NullCheck(op="isNull", attr="Person.displayName"),
            "where jsonb_extract_path_text(t0.payload, ?) is null",
            ("displayName",),
        ),
        (
            oa.NullCheck(op="isNotNull", attr="Person.displayName"),
            "where not jsonb_extract_path_text(t0.payload, ?) is null",
            ("displayName",),
        ),
        (
            oa.StringMatch(op="startsWith", attr="Person.displayName", value="Ad"),
            "where jsonb_extract_path_text(t0.payload, ?) like ?",
            ("displayName", "Ad%"),
        ),
    ],
)
def test_a_document_path_predicate_lowers_through_the_extraction_and_cast_seams(
    predicate: oa.PredicateNode, expected: str, binds: tuple[object, ...]
) -> None:
    # The path comes from the compiled Member Placement, so a top-level Attribute
    # is a ONE-segment path bind; whether the extraction casts is fixed by the
    # declared type, and the path segments always bind ahead of the compared
    # value because the emitted text puts their holes first.
    compiled = compile_read(predicate, DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert _where(compiled.statement.sql) == expected
    assert compiled.statement.binds == binds


def test_a_text_compared_member_binds_the_comparison_text_the_writer_stored() -> None:
    # A `date` compares as extracted text, so what SQL binds is the characters
    # the extraction returns — not the authored literal, which may spell the same
    # value another way.
    compiled = compile_read(
        oa.Comparison(op="eq", attr="Person.joinedOn", value="2026-01-15"),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert compiled.statement.binds == ("joinedOn", "2026-01-15")


def test_a_direct_column_still_binds_its_literal_as_authored() -> None:
    # The primary key stays a direct role under either layout, so its comparison
    # is an ordinary typed column comparison and nothing about the document
    # reaches it.
    compiled = compile_read(
        oa.Comparison(op="eq", attr="Person.id", value=1),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert _where(compiled.statement.sql) == "where t0.id = ?"
    assert compiled.statement.binds == (1,)


def test_an_ordering_key_over_a_document_member_lowers_through_the_same_seams() -> None:
    compiled = compile_read(
        oa.All(),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
        order_by=(oq.OrderKey(attr="Person.score", direction="desc", nulls="last"),),
    )
    assert compiled.statement.sql.endswith(
        "order by cast(jsonb_extract_path_text(t0.payload, ?) as bigint) desc nulls last"
    )
    assert compiled.statement.binds == ("score",)


def test_a_nested_occurrence_predicate_walks_from_the_occurrences_own_placement() -> None:
    # Under `Columns` the occurrence owns its column and the path starts below it;
    # under `Document` it is a subtree of the shared column, so its own path
    # prefixes every segment the predicate walks.
    document = compile_read(
        oa.NestedComparison(op="nestedEq", path="Person.address.geo.country", value="NO"),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert (
        _where(document.statement.sql) == "where jsonb_extract_path_text(t0.payload, ?, ?, ?) = ?"
    )
    assert document.statement.binds == ("address", "geo", "country", "NO")
    columns = compile_read(
        oa.NestedComparison(op="nestedEq", path="Person.address.geo.country", value="NO"),
        COLUMNS,
        POSTGRES,
        entity(COLUMNS, "Person"),
    )
    assert _where(columns.statement.sql) == "where jsonb_extract_path_text(t0.address, ?, ?) = ?"
    assert columns.statement.binds == ("geo", "country", "NO")


def test_a_to_many_traversal_guards_the_array_at_its_placed_path() -> None:
    compiled = compile_read(
        oa.NestedExists(
            path="Person.tags", where=oa.NestedComparison(op="nestedEq", path="label", value="x")
        ),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert _where(compiled.statement.sql) == (
        "where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.payload, ?)) = ? "
        "then jsonb_extract_path(t0.payload, ?) else cast(? as jsonb) end) t1 "
        "where jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert compiled.statement.binds == ("tags", "array", "tags", "[]", "label", "x")


def test_an_any_element_flat_predicate_guards_the_array_at_its_placed_path() -> None:
    compiled = compile_read(
        oa.NestedComparison(op="nestedEq", path="Person.tags.label", value="x"),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert compiled.statement.binds == ("tags", "array", "tags", "[]", "label", "x")


def test_a_write_predicate_extracts_from_the_bare_structured_column() -> None:
    # A write's rendered predicate is unaliased (`m-batch-write`), and the
    # document reference takes that same decision — the extraction goes bare too.
    compiled = compile_write_predicate(
        oa.Comparison(op="eq", attr="Person.displayName", value="Ada"),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert compiled.sql == "jsonb_extract_path_text(payload, ?) = ?"
    assert compiled.binds == ("displayName", "Ada")
