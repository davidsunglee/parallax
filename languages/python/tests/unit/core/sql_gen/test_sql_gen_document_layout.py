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
from collections.abc import Callable

import pytest

from parallax.core import deep_fetch
from parallax.core import object_query as oq
from parallax.core import predicate as oa
from parallax.core.base import (
    INT64,
    STRING,
    TIMESTAMP,
    DocumentValue,
    PresentDocument,
)
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityMetadata
from parallax.core.navigate import (
    PropagatedRootSelections,
    RootSelections,
    resolve_temporal_visibility,
)
from parallax.core.object_query._nodes import IncludePathNode, TemporalDimension
from parallax.core.read_delivery._row_decoding import publication_keys, row_identity
from parallax.core.sql_gen import LoweredStatement
from parallax.core.sql_gen._compile import CompiledRead, compile_template
from parallax.core.sql_gen._compile import (
    compile_write_predicate as compile_validated_write_predicate,
)
from parallax.descriptor._ingest import ingest_document
from tests._support.sql import compile_projected_read, compile_read, compile_write_predicate
from tests.unit._corpus_model_support import formed
from tests.unit._document_layout_support import columns_model, document_model, entity

DOCUMENT = document_model()
COLUMNS = columns_model()


def _where(sql: str) -> str:
    return sql.partition(" from person t0 ")[2]


def test_a_read_projects_the_structured_column_once_and_never_a_member_column() -> None:
    compiled = compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert compiled.statement.sql == (
        "select t0.id, not t0.payload is null, t0.payload from person t0"
    )
    assert compiled.document_reads == ((1, 2),)
    # Instance form needs the same one column: the document already carries the
    # Value Object occurrences an instance additionally materializes.
    instance = compile_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    assert instance.statement.sql == (
        "select t0.id, not t0.payload is null, t0.payload from person t0"
    )


def test_a_row_form_read_needing_no_document_member_projects_no_document_at_all() -> None:
    # `Marker` declares the layout and nothing document-resident, so outside the
    # observation lane its Structured Column exists physically and is projected by
    # nothing: the rule is keyed to the members the read was asked for.
    compiled = compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Marker"))
    assert compiled.statement.sql == "select t0.id from marker t0"
    assert compiled.result_contract.shared_document is None


def _instance_form(target: EntityMetadata) -> CompiledRead:
    return compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, target, result_form="instance")


def _widened_resolve(target: EntityMetadata) -> CompiledRead:
    return compile_projected_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, target, include_value_objects=True
    )


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
    shared = compiled.result_contract.shared_document
    assert shared is not None and shared.column == "payload"
    # The column is still never a result field: it carries no member here and the
    # raw value leaves the published row all the same.
    document: DocumentValue = {"berthCode": "NB-118"}
    row = {"id": 1, "payload": PresentDocument(document)}
    assert publication_keys(compiled.result_contract, compiled.target, None) == ("id",)
    assert row_identity(compiled.result_contract, row)[3] == document


def test_a_versioned_targets_narrowed_widening_still_projects_only_what_it_needs() -> None:
    # A `frozenset` widening is the versioned target's comparison-only need rather
    # than an observation, so it leaves the rule where it was: no member the read
    # asked for is document-resident, so no Structured Column is projected.
    compiled = compile_projected_read(
        oa.TrueNode(),
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
        oa.TrueNode(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
    )
    assert compiled.result_contract.classified_by_entity.get(
        compiled.target, frozenset()
    ).issuperset({"address", "tags"})


def test_the_compiled_read_names_the_occurrences_a_row_can_carry_under_either_layout() -> None:
    # A Position Layout answers this from its logical MEMBER sequence, because an
    # occurrence is a member under either layout while it is a Column only under
    # `Columns` — reading its physical columns would leave a document row with no
    # occurrence to materialize at all.
    document = compile_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    columns = compile_read(
        oa.TrueNode(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
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
    compiled = compile_read(oa.TrueNode(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"))
    assert [member.storage.name for member in compiled.documents] == ["address", "tags"]
    assert compiled.projected_documents == ()


def test_the_raw_document_is_never_a_result_field() -> None:
    compiled = compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert "payload" not in publication_keys(compiled.result_contract, compiled.target, None)


def test_an_entity_document_classifies_each_requested_member() -> None:
    compiled = compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    assert compiled.result_contract.classified_by_entity.get(
        compiled.target, frozenset()
    ) == frozenset({"display_name", "score", "joined_on"})


@pytest.mark.parametrize(
    ("predicate", "expected", "binds"),
    [
        (
            oa.Comparison(op="eq", subject=oa.FieldSubject("Person.displayName"), value="Ada"),
            "where jsonb_extract_path_text(t0.payload, ?) = ?",
            ("displayName", "Ada"),
        ),
        (
            oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Person.score"), value=3),
            "where cast(jsonb_extract_path_text(t0.payload, ?) as bigint) > ?",
            ("score", 3),
        ),
        (
            oa.Range(subject=oa.FieldSubject("Person.score"), lower=1, upper=9),
            "where cast(jsonb_extract_path_text(t0.payload, ?) as bigint) between ? and ?",
            ("score", 1, 9),
        ),
        (
            oa.Membership(op="in", subject=oa.FieldSubject("Person.score"), values=(1, 2)),
            "where cast(jsonb_extract_path_text(t0.payload, ?) as bigint) in (?, ?)",
            ("score", 1, 2),
        ),
        (
            oa.NullCheck(op="isNull", subject=oa.FieldSubject("Person.displayName")),
            "where jsonb_extract_path_text(t0.payload, ?) is null",
            ("displayName",),
        ),
        (
            oa.NullCheck(op="isNotNull", subject=oa.FieldSubject("Person.displayName")),
            "where not jsonb_extract_path_text(t0.payload, ?) is null",
            ("displayName",),
        ),
        (
            oa.StringMatch(
                op="startsWith", subject=oa.FieldSubject("Person.displayName"), value="Ad"
            ),
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
        oa.Comparison(op="eq", subject=oa.FieldSubject("Person.joinedOn"), value="2026-01-15"),
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
        oa.Comparison(op="eq", subject=oa.FieldSubject("Person.id"), value=1),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert _where(compiled.statement.sql) == "where t0.id = ?"
    assert compiled.statement.binds == (1,)


def test_an_ordering_key_over_a_document_member_lowers_through_the_same_seams() -> None:
    compiled = compile_read(
        oa.TrueNode(),
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
        oa.Comparison(op="eq", subject=oa.FieldSubject("Person.address.geo.country"), value="NO"),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert (
        _where(document.statement.sql) == "where jsonb_extract_path_text(t0.payload, ?, ?, ?) = ?"
    )
    assert document.statement.binds == ("address", "geo", "country", "NO")
    columns = compile_read(
        oa.Comparison(op="eq", subject=oa.FieldSubject("Person.address.geo.country"), value="NO"),
        COLUMNS,
        POSTGRES,
        entity(COLUMNS, "Person"),
    )
    assert _where(columns.statement.sql) == "where jsonb_extract_path_text(t0.address, ?, ?) = ?"
    assert columns.statement.binds == ("geo", "country", "NO")


def test_a_to_many_traversal_guards_the_array_at_its_placed_path() -> None:
    compiled = compile_read(
        oa.Quantifier(
            "any",
            "Person.tags",
            oa.Comparison(op="eq", subject=oa.FieldSubject("label"), value="x"),
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


def test_presence_of_a_placed_single_value_object_reads_its_placed_path() -> None:
    compiled = compile_read(
        oa.Presence("notExists", "Person.address.geo"),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert compiled.statement.binds == ("address", "geo", "object")


def test_a_write_predicate_extracts_from_the_bare_structured_column() -> None:
    # A write's rendered predicate is unaliased (`m-batch-write`), and the
    # document reference takes that same decision — the extraction goes bare too.
    compiled = compile_write_predicate(
        oa.Comparison(op="eq", subject=oa.FieldSubject("Person.displayName"), value="Ada"),
        DOCUMENT,
        POSTGRES,
        entity(DOCUMENT, "Person"),
    )
    assert compiled.sql == "jsonb_extract_path_text(payload, ?) = ?"
    assert compiled.binds == ("displayName", "Ada")


# --------------------------------------------------------------------------- #
# Temporal visibility beside document-resident reads: an axis bound keeps a   #
# Column of its own, so a perspective binds managed instants after whatever    #
# path segments and comparison text the predicate beside it bound.            #
# --------------------------------------------------------------------------- #
_KEY = {"name": "id", "type": "int64", "primaryKey": True}
_PAYLOAD = {"document": {"column": "payload"}}
_FLEETS = formed(
    ingest_document(
        {
            "entities": [
                {
                    "name": "Fleet",
                    "table": "fleet",
                    "layout": _PAYLOAD,
                    "temporality": "bitemporal",
                    "attributes": [
                        _KEY,
                        {"name": "name", "type": "string", "maxLength": 32, "nullable": True},
                    ],
                    "relationships": [
                        {
                            "name": "ships",
                            "cardinality": "one-to-many",
                            "join": {
                                "source": "id",
                                "target": {"entity": "Ship", "attribute": "fleetId"},
                            },
                        }
                    ],
                },
                {
                    "name": "Ship",
                    "table": "ship",
                    "layout": _PAYLOAD,
                    "temporality": "bitemporal",
                    "attributes": [
                        _KEY,
                        {"name": "fleetId", "type": "int64"},
                        {"name": "flag", "type": "string", "maxLength": 8, "nullable": True},
                    ],
                    "relationships": [{"name": "fleet", "reverseOf": "Fleet.ships"}],
                },
            ]
        }
    )
)
_VALID = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_TX = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_VALID_WIRE, _TX_WIRE = "2024-03-01T00:00:00.000000Z", "2024-02-01T00:00:00.000000Z"
_PINNED: dict[TemporalDimension, oq.TemporalSelection] = {
    "valid-time": oq.AsOf("2024-03-01T00:00:00Z"),
    "transaction-time": oq.AsOf("2024-02-01T00:00:00Z"),
}
_PINNED_BINDS = (_VALID, _VALID, _TX, _TX)
_PINNED_WIRE = (_VALID_WIRE, _VALID_WIRE, _TX_WIRE, _TX_WIRE)


def _spans(statement: LoweredStatement) -> list[tuple[range, object, str]]:
    """Each typed span as the bind positions it covers, its type, and its form."""
    return [
        (range(min(indexes), max(indexes) + 1), span.neutral_type, span.form)
        for span in statement.typed_bind_spans
        if (indexes := tuple(span.indexes()))
    ]


def _visible(alias: str) -> str:
    return f"{alias}from_z <= ? and {alias}thru_z > ? and {alias}in_z <= ? and {alias}out_z > ?"


def test_a_correlated_perspective_binds_after_the_document_path_and_operand_before_it() -> None:
    statement = compile_read(
        oa.Quantifier(
            "any", "Fleet.ships", oa.Comparison(op="eq", subject=oa.FieldSubject("flag"), value="X")
        ),
        _FLEETS,
        POSTGRES,
        entity(_FLEETS, "Fleet"),
        temporal=_PINNED,
    ).statement

    assert statement.sql.endswith(
        "from fleet t0 where exists (select 1 from ship t1 where t1.fleet_id = t0.id and "
        f"jsonb_extract_path_text(t1.payload, ?) = ? and {_visible('t1.')}) and {_visible('t0.')}"
    )
    assert statement.binds == ("flag", "X", *_PINNED_BINDS, *_PINNED_BINDS)
    assert statement.wire_binds() == ("flag", "X", *_PINNED_WIRE, *_PINNED_WIRE)
    assert _spans(statement) == [
        (range(1, 2), STRING, "COMPARISON_TEXT"),
        (range(2, 10), TIMESTAMP, "MANAGED"),
    ]


def test_a_shared_join_binds_its_perspective_before_the_document_read_beside_it() -> None:
    statement = compile_read(
        oa.Comparison(op="eq", subject=oa.FieldSubject("Ship.fleet.name"), value="N"),
        _FLEETS,
        POSTGRES,
        entity(_FLEETS, "Ship"),
        temporal=_PINNED,
    ).statement

    assert statement.sql.endswith(
        f"from ship t0 left join fleet t1 on t1.id = t0.fleet_id and {_visible('t1.')} "
        f"where jsonb_extract_path_text(t1.payload, ?) = ? and {_visible('t0.')}"
    )
    assert statement.binds == (*_PINNED_BINDS, "name", "N", *_PINNED_BINDS)
    assert statement.wire_binds() == (*_PINNED_WIRE, "name", "N", *_PINNED_WIRE)
    assert _spans(statement) == [
        (range(4), TIMESTAMP, "MANAGED"),
        (range(5, 6), STRING, "COMPARISON_TEXT"),
        (range(6, 10), TIMESTAMP, "MANAGED"),
    ]


def test_an_include_child_binds_its_retained_perspective_after_its_keys() -> None:
    fleet = entity(_FLEETS, "Fleet")
    query = oq.validate_object_query(
        fleet,
        oq.object_query(
            fleet.identity,
            oa.TrueNode(),
            temporal=_PINNED,
            includes=(IncludePathNode(segments=(oq.IncludeSegment(rel="Fleet.ships"),)),),
        ),
        _FLEETS,
    )
    (step,) = deep_fetch.plan(
        query, _FLEETS, projection=deep_fetch.ReadProjectionRequest("all", True)
    ).fetch_steps
    assert isinstance(step, deep_fetch.QueryFetchStep)

    statement = (
        compile_template(step.query, _FLEETS, POSTGRES, result_form="instance")
        .render([1, 2])
        .statement
    )

    assert statement.sql.endswith(f"from ship t0 where t0.fleet_id = any(?) and {_visible('t0.')}")
    assert statement.binds == ([1, 2], *_PINNED_BINDS)
    assert statement.wire_binds() == ([1, 2], *_PINNED_WIRE)
    assert _spans(statement) == [
        (range(1), INT64, "MANAGED_ARRAY"),
        (range(1, 5), TIMESTAMP, "MANAGED"),
    ]


@pytest.mark.parametrize(
    "resolution", [RootSelections, PropagatedRootSelections], ids=["injected", "retained"]
)
def test_a_write_root_perspective_follows_a_document_predicate_in_place(
    resolution: type[RootSelections | PropagatedRootSelections],
) -> None:
    ship = entity(_FLEETS, "Ship")
    query = oq.validate_object_query(
        ship,
        oq.object_query(
            ship.identity,
            oa.Comparison(op="eq", subject=oa.FieldSubject("Ship.flag"), value="X"),
            temporal=_PINNED,
        ),
        _FLEETS,
    )
    closed = resolve_temporal_visibility(
        query.predicate, target=ship, model=_FLEETS, resolution=resolution(query.temporal)
    )

    compiled = compile_validated_write_predicate(closed, _FLEETS, POSTGRES, ship)

    assert compiled.sql == f"jsonb_extract_path_text(payload, ?) = ? and {_visible('')}"
    assert compiled.binds == ("flag", "X", *_PINNED_BINDS)
    assert compiled.lowered is not None
    assert _spans(compiled.lowered) == [
        (range(1, 2), STRING, "COMPARISON_TEXT"),
        (range(2, 6), TIMESTAMP, "MANAGED"),
    ]
