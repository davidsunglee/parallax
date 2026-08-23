"""Conversion of a Relational Document Layout row (m-snapshot-read, m-storage-layout).

The production read path's own document-layout witness. Every corpus case over
`models/document-layout.yaml` grades a rejected model, a write sequence, a row-form
oracle, or a graph the compatibility engine assembles itself, so none of them reaches
`parallax.snapshot.materialize`; a *materializing* read of a document row answering
the same members a `Columns` row answers is graded here instead.

What runs here is the driver's own sequence, database aside: the layout's own
instance-form projection (`compile_read`), the fan-out that lands each
document-resident member under the result key a direct Column would have carried
(`m-sql`), and per-row conversion into one compact projection row. The one property
under test is that the layout is not observable at that seam — a document row and
its member-for-member `Columns` twin convert to the same member row, including the
not-present states a document can spell and a Column cannot.

The twins are two different models, so their layouts are two different objects and
comparing rows POSITIONALLY would compare two coordinate systems. The comparison is
therefore each row rendered by declared member name, which is exactly what "the
layout is unobservable" claims: the same members, holding the same values.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from _document_layout_support import columns_model, document_model, entity
from _snapshot_graph_support import documents_of, layout_of, rendered_members

from _support.sql import compile_read
from parallax.conformance import models
from parallax.core import predicate as oa
from parallax.core.base import DocumentValue, PresentDocument
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize import StoredDataIssueInput
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import GraphBuilder, graph_rows
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

_CORPUS = models.load_models()["document-layout"]
_TWIN_DOCUMENT = document_model()
_TWIN_COLUMNS = columns_model()


@dataclass(frozen=True, slots=True)
class _Converted:
    """One converted row, as the members it carries and what it classified."""

    members: Mapping[str, Any]
    issues: tuple[StoredDataIssueInput, ...]


def _converted(model: Metamodel, name: str, stored: Mapping[str, object]) -> _Converted:
    """One stored row through the production read sequence, database aside."""
    target = entity(model, name)
    compiled = compile_read(oa.All(), model, POSTGRES, target, result_form="instance")
    materialized = compiled.materialize_row(stored)
    builder = GraphBuilder(ViewSchema.of())
    context = LevelContext(
        layout_of(model, materialized.resolved_entity),
        compiled.projected_documents,
        compiled.attribute_reads(materialized.resolved_entity),
    )
    index = convert_row(
        materialized.values,
        context,
        builder,
        source=ROOT_LEVEL,
        findings=materialized.findings,
        family_tag_unknown=materialized.family_tag_unknown,
        classified_members=materialized.classified_members,
    )
    rows = graph_rows(builder.seal((index,), Pin()))
    return _Converted(
        rendered_members(rows.layouts[index], rows.member_rows[index]), rows.issues[index]
    )


def _members(node: _Converted) -> Mapping[str, Any]:
    return node.members


# The corpus fixture's own first Traveler, in the physical shape the layout stores
# it: one direct Column for the primary key and one Structured Column carrying
# every other member under its own name, each leaf in the codec's portable
# spelling (`joinedOn` an ISO-8601 string, `score` a JSON number).
_ADA_DOCUMENT: DocumentValue = {
    "displayName": "Ada",
    "score": 7,
    "joinedOn": "2026-01-15",
    "note": "north wing",
    "address": {"city": "Oslo", "geo": {"country": "NO"}},
    "tags": [{"label": "founder"}, {"label": "staff"}],
}
_ADA: Mapping[str, object] = {
    "id": 1,
    "payload": PresentDocument(_ADA_DOCUMENT),
}


def test_a_document_layout_row_converts_every_member_by_its_declared_identity() -> None:
    node = _converted(_CORPUS, "Traveler", _ADA)
    members = _members(node)
    assert members["displayName"] == "Ada"
    assert members["score"] == 7
    assert members["joinedOn"] == dt.date(2026, 1, 15)
    assert members["note"] == "north wing"
    assert members["address"] == {"city": "Oslo", "geo": {"country": "NO"}}
    assert members["tags"] == ({"label": "founder"}, {"label": "staff"})


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"displayName": "Bo"}, id="the-key-is-absent"),
        pytest.param({"displayName": "Bo", "note": None}, id="the-key-holds-json-null"),
    ],
)
def test_an_absent_and_a_json_null_document_leaf_convert_alike(
    payload: dict[str, DocumentValue],
) -> None:
    # The corpus's own presence pair (`m-storage-layout-021`, Travelers 2 and 3),
    # asserted where a graph is built rather than where rows are compared: a
    # Column has one not-present state and a document has two, and conversion
    # answers `None` for all three so the layout cannot be told apart by them.
    node = _converted(
        _CORPUS,
        "Traveler",
        {"id": 2, "payload": PresentDocument(dict(payload))},
    )
    members = _members(node)
    assert members["note"] is None
    assert members["address"] is None
    assert members["tags"] == ()


def test_unavailable_entity_document_members_are_not_hydrated_while_retaining_findings() -> None:
    node = _converted(
        _CORPUS,
        "Traveler",
        {"id": 2, "payload": PresentDocument({"displayName": 7})},
    )
    assert [issue.code for issue in node.issues] == ["stored-data-leaf-undecodable"]
    assert "displayName" not in _members(node)


def test_the_layout_is_unobservable_across_a_member_for_member_twin() -> None:
    # The two models declare the same members with the same names, types, and
    # Columns and differ only in the root's `layout`, so equal converted rows
    # are the whole claim: nothing below conversion can tell which shape the row
    # was stored in.
    stored_document_value: DocumentValue = {
        "displayName": "Ada",
        "score": 7,
        "joinedOn": "2026-01-15",
        "address": {"city": "Oslo", "geo": {"country": "NO"}},
        "tags": [{"label": "founder"}],
    }
    stored_document: Mapping[str, object] = {
        "id": 1,
        "payload": PresentDocument(stored_document_value),
    }
    stored_columns: Mapping[str, object] = {
        "id": 1,
        "display_name": "Ada",
        "score": 7,
        "joined_on": dt.date(2026, 1, 15),
        "address": PresentDocument({"city": "Oslo", "geo": {"country": "NO"}}),
        "tags": PresentDocument([{"label": "founder"}]),
    }
    assert _converted(_TWIN_DOCUMENT, "Person", stored_document) == _converted(
        _TWIN_COLUMNS, "Person", stored_columns
    )


def test_wrong_kind_occurrences_classify_identically_without_retaining_valid_siblings() -> None:
    document = _converted(
        _TWIN_DOCUMENT,
        "Person",
        {
            "id": 1,
            "payload": PresentDocument({"tags": [{"label": "valid"}, "wrong"]}),
        },
    )
    columns = _converted(
        _TWIN_COLUMNS,
        "Person",
        {
            "id": 1,
            "display_name": None,
            "score": None,
            "joined_on": None,
            "tags": PresentDocument([{"label": "valid"}, "wrong"]),
        },
    )
    assert document == columns
    assert [issue.code for issue in document.issues] == ["stored-data-many-wrong-kind"]
    assert _members(document)["tags"] == ()


def test_an_entity_with_no_document_resident_member_converts_off_its_columns_alone() -> None:
    # `Marker` declares the layout and nothing inside it, so its Structured Column
    # is physically present, is carried by a materializing read, and holds no
    # member at all. Conversion answers the row's own Columns and contributes
    # nothing for the document.
    identity = entity(_TWIN_DOCUMENT, "Marker").identity
    assert documents_of(_TWIN_DOCUMENT, identity) == ()
    node = _converted(_TWIN_DOCUMENT, "Marker", {"id": 5, "payload": PresentDocument({})})
    assert _members(node) == {"id": 5}
