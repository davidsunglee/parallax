"""Writes to a Relational Document Layout Entity (m-storage-layout, m-dialect).

Two properties are under test, and they are the write-side halves of the one the
read suite pins. First, every document-resident member the statement touches
reaches the SAME shared Structured Column: an opening statement fills it with one
complete document and a revising one patches only the paths it assigns, so an
unassigned key — a model member the step left alone as much as a key a newer
application version wrote — survives. Second, what lands there is the CODEC's
spelling of each value rather than the carrier the write input happened to hold.

The model is the read suite's own (`_document_layout_support`), so the two
suites' claims are about one declaration seen from both sides.
"""

from __future__ import annotations

from typing import cast

from _document_layout_support import columns_model, document_model, entity

from _support.lowering_probes import lower_instruction
from parallax.core.db_port import JsonDocument
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import KeyedWrite, WriteInstruction
from parallax.snapshot.handle._keyed_sql import collapse_group_key

DOCUMENT = document_model()
COLUMNS = columns_model()


def _lower(instruction: WriteInstruction, model: Metamodel = DOCUMENT) -> list[Statement]:
    return lower_instruction(instruction, model)


def _document(statement: Statement, index: int = -1) -> object:
    return cast("JsonDocument", statement.binds[index]).value


def test_an_insert_binds_one_document_at_the_structured_column() -> None:
    (statement,) = _lower(
        KeyedWrite(
            "insert",
            "Person",
            (
                {
                    "id": 1,
                    "displayName": "Ada",
                    "score": 7,
                    "joinedOn": "2026-01-15",
                    "address": {"city": "Oslo", "geo": {"country": "NO"}},
                    "tags": [{"label": "founder"}],
                },
            ),
        )
    )
    assert statement.sql == "insert into person(id, payload) values (?, ?)"
    assert statement.binds[0] == 1
    assert _document(statement) == {
        "displayName": "Ada",
        "score": 7,
        "joinedOn": "2026-01-15",
        "address": {"city": "Oslo", "geo": {"country": "NO"}},
        "tags": [{"label": "founder"}],
    }


def test_an_inserts_document_omits_what_the_row_omits_and_nulls_what_it_nulls() -> None:
    # Presence is the codec's classification, not the caller's: a member the row
    # never names contributes no key at all, one it sets to `None` contributes JSON
    # null, and the `many` occurrence contributes its array either way.
    (statement,) = _lower(
        KeyedWrite("insert", "Person", ({"id": 2, "displayName": None, "tags": []},))
    )
    assert _document(statement) == {"displayName": None, "tags": []}


def test_an_entity_with_no_document_member_still_binds_the_empty_object() -> None:
    # The Structured Column is `NOT NULL` and every governed row carries a document,
    # so an insert binds it whether or not the Entity has anything to put inside.
    (statement,) = _lower(KeyedWrite("insert", "Marker", ({"id": 3},)))
    assert statement.sql == "insert into marker(id, payload) values (?, ?)"
    assert _document(statement) == {}


def test_a_document_leaf_binds_the_codecs_spelling_not_the_inputs_carrier() -> None:
    # `joinedOn` is a `date`. The write input carries the portable wire spelling and
    # the document stores the codec's, which for a date are the same characters —
    # what matters is that the value went THROUGH the encoding table rather than to a
    # serializer, which is what a `decimal` or `bytes` leaf would expose.
    (statement,) = _lower(
        KeyedWrite("insert", "Person", ({"id": 4, "joinedOn": "2026-01-15", "tags": []},))
    )
    assert _document(statement) == {"joinedOn": "2026-01-15", "tags": []}


def test_an_update_patches_only_the_assigned_paths_in_canonical_order() -> None:
    # The ROW lists `score` first; the statement assigns `displayName` first, because
    # canonical logical placement order is the layout's and both dialects apply their
    # mutation expressions left to right (m-dialect).
    (statement,) = _lower(
        KeyedWrite("update", "Person", ({"id": 1, "score": 9, "displayName": "Ada"},))
    )
    assert statement.sql == (
        "update person set payload = "
        "jsonb_set(jsonb_set(payload, ?, cast(? as jsonb)), ?, cast(? as jsonb)) where id = ?"
    )
    assert statement.binds == ("{displayName}", '"Ada"', "{score}", "9", 1)


def test_an_assigned_none_writes_json_null_rather_than_removing_the_key() -> None:
    # A NULL Column has one not-present state, so an assignment of `None` writes the
    # document's null rather than dropping the key — the two read back the same, and
    # writing neither would leave the stored value standing.
    (statement,) = _lower(KeyedWrite("update", "Person", ({"id": 1, "displayName": None},)))
    assert statement.binds == ("{displayName}", "null", 1)


def test_assigning_a_whole_occurrence_binds_one_composite_at_its_own_path() -> None:
    # One path and one pair: the occurrence's own Document Path, and its document as
    # the managed carrier the adapter hands to the driver — never its rendered text,
    # which would put a key order into the statement.
    (statement,) = _lower(KeyedWrite("update", "Person", ({"id": 1, "address": {"city": "Bodo"}},)))
    assert statement.sql == (
        "update person set payload = jsonb_set(payload, ?, cast(? as jsonb)) where id = ?"
    )
    assert statement.binds[0] == "{address}"
    assert statement.binds[1] == JsonDocument({"city": "Bodo"})
    assert statement.binds[2] == 1


def test_a_direct_member_still_assigns_its_own_column() -> None:
    # The primary key is a direct role under either layout, so a delete keyed by it
    # names a Column and never extracts from the document.
    (statement,) = _lower(KeyedWrite("delete", "Person", ({"id": 1},)))
    assert statement.sql == "delete from person where id = ?"


def test_a_columns_layout_twin_writes_the_same_members_to_their_own_columns() -> None:
    # The contrast that makes the claim above a layout decision rather than a
    # rewrite: the same instruction over the same members emits five columns.
    (statement,) = _lower(
        KeyedWrite("insert", "Person", ({"id": 1, "displayName": "Ada", "tags": []},)),
        COLUMNS,
    )
    assert statement.sql == "insert into person(id, display_name, tags) values (?, ?, ?)"


def test_two_rows_naming_different_document_members_do_not_share_one_statement() -> None:
    # Both rows select the same two columns, so a grouping decision made from the
    # column list alone would collapse them and bind the second row's document
    # against the first row's member set. Placement tells them apart by path.
    person = entity(DOCUMENT, "Person")
    display_name = collapse_group_key(DOCUMENT, person, "insert", {"id": 1, "displayName": "Ada"})
    score = collapse_group_key(DOCUMENT, person, "insert", {"id": 2, "score": 7})
    same = collapse_group_key(DOCUMENT, person, "insert", {"id": 3, "displayName": "Bo"})
    assert display_name != score
    assert display_name == same


def test_a_delete_groups_by_its_key_columns_under_either_layout() -> None:
    # A delete renders its identity predicate alone, so its selection is the key
    # columns and the document members it happens to carry are invisible.
    person = entity(DOCUMENT, "Person")
    assert collapse_group_key(
        DOCUMENT, person, "delete", {"id": 1, "displayName": "Ada"}
    ) == collapse_group_key(DOCUMENT, person, "delete", {"id": 2, "score": 7})
