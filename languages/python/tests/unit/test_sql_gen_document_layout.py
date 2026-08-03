"""Reads over a Relational Document Layout Entity (m-sql, m-storage-layout).

The one property under test is that the layout is not observable: a read of the
same members returns the same logical rows under the same result keys whichever
layout the root declares. What differs is confined to two places — the select
list projects one Structured Column instead of a column per member, and every
predicate and ordering term over a document-resident member lowers through the
`m-dialect` extraction and typed-cast seams the conventional nested vocabulary
already uses.

The capability gate still refuses this shape at whole-model formation, so the
model is accepted directly (`_document_layout_support`); everything below it is
the production read lane.
"""

from __future__ import annotations

import datetime as dt

import pytest
from _document_layout_support import columns_model, document_model, entity

from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import compile_read, compile_write_predicate

DOCUMENT = document_model()
COLUMNS = columns_model()

# One person, spelled the two ways the two layouts store it. Every leaf inside
# the document carries the codec's own portable spelling, which is what a
# document-resident member reads back as before it is decoded.
_DOCUMENT_ROW = {
    "id": 1,
    "payload": {
        "displayName": "Ada",
        "score": 7,
        "joinedOn": "2026-01-15",
        "address": {"city": "Oslo", "geo": {"country": "NO"}},
        "tags": [{"label": "founder"}],
    },
}
_COLUMNS_ROW = {
    "id": 1,
    "display_name": "Ada",
    "score": 7,
    "joined_on": dt.date(2026, 1, 15),
    "address": {"city": "Oslo", "geo": {"country": "NO"}},
    "tags": [{"label": "founder"}],
}


def _where(sql: str) -> str:
    return sql.partition(" from person t0 ")[2]


def test_a_read_projects_the_structured_column_once_and_never_a_member_column() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert compiled.statement.sql == "select t0.id, t0.payload from person t0"
    # Instance form needs the same one column: the document already carries the
    # Value Object occurrences an instance additionally materializes.
    instance = compile_read(
        oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    assert instance.statement.sql == "select t0.id, t0.payload from person t0"


def test_a_read_needing_no_document_member_projects_no_document_at_all() -> None:
    # `Marker` declares the layout and nothing document-resident, so the
    # Structured Column exists physically and is projected by nothing: the rule
    # is keyed to the members the read was asked for, never to the declaration.
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Marker"))
    assert compiled.statement.sql == "select t0.id from marker t0"
    assert compiled.transform_row({"id": 1}) == {"id": 1}


def test_a_row_form_read_fans_the_document_out_under_the_columns_own_result_keys() -> None:
    document = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    columns = compile_read(oa.All(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"))
    assert document.transform_row(_DOCUMENT_ROW) == columns.transform_row(
        {key: value for key, value in _COLUMNS_ROW.items() if key not in ("address", "tags")}
    )


def test_an_instance_form_read_fans_out_the_occurrences_too() -> None:
    document = compile_read(
        oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    columns = compile_read(
        oa.All(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
    )
    assert document.transform_row(_DOCUMENT_ROW) == columns.transform_row(_COLUMNS_ROW)


def test_the_fan_out_decodes_by_declared_type_rather_than_by_the_json_values_shape() -> None:
    # A `date` is an ISO-8601 string inside the document and a driver `date` in a
    # column of its own; the fan-out returns the MANAGED value, so one logical
    # value is not observably different under the two layouts.
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert compiled.transform_row(_DOCUMENT_ROW)["joined_on"] == dt.date(2026, 1, 15)


def test_a_missing_and_an_explicitly_null_document_key_both_read_as_one_absence() -> None:
    # Absence collapse is the consumer's, applied to the codec's answer: a NULL
    # Column has one not-present state and the document has two, and a result row
    # must not be able to tell them apart.
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    missing = compiled.transform_row({"id": 1, "payload": {}})
    explicit = compiled.transform_row({"id": 1, "payload": {"displayName": None, "score": None}})
    assert missing == explicit
    assert missing["display_name"] is None


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


def test_the_raw_document_is_never_a_result_field() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert "payload" not in compiled.transform_row(_DOCUMENT_ROW)


@pytest.mark.parametrize(
    ("operation", "expected", "binds"),
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
    operation: oa.Operation, expected: str, binds: tuple[object, ...]
) -> None:
    # The path comes from the compiled Member Placement, so a top-level Attribute
    # is a ONE-segment path bind; whether the extraction casts is fixed by the
    # declared type, and the path segments always bind ahead of the compared
    # value because the emitted text puts their holes first.
    compiled = compile_read(operation, DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
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
        oa.OrderBy(
            operand=oa.All(),
            keys=(oa.OrderKey(attr="Person.score", direction="desc", nulls="last"),),
        ),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
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
