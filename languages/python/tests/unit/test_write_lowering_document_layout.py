"""Writes to a Relational Document Layout Entity (m-storage-layout, m-dialect).

Two properties are under test, and they are the write-side halves of the one the
read suite pins. First, every document-resident member the statement touches
reaches the SAME shared Structured Column: an opening statement fills it with one
complete document and a revising one writes only the paths it assigns, so an
unassigned key — a model member the step left alone as much as a key a newer
application version wrote — survives, while an assigned occurrence's path takes
its whole subtree and nothing inside the replaced one does. Second, what lands
there is the CODEC's spelling of each value rather than the carrier the write
input happened to hold.

The model is the read suite's own (`_document_layout_support`), so the two
suites' claims are about one declaration seen from both sides.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Final, cast

import pytest
from _document_layout_support import PERSON, columns_model, document_model, entity

from _support.lowering_probes import lower_instruction
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.unit_work import KeyedWrite, PredecessorRow, WriteInstruction
from parallax.core.unit_work.planned import (
    NEW_LINEAGE,
    CarriedFrom,
    ChangedFrom,
    InsertEntry,
    PlannedInsert,
    PlannedRow,
)
from parallax.snapshot.handle._keyed_sql import collapse_group_key
from parallax.snapshot.handle._write_inputs import is_no_op_assignment

DOCUMENT = document_model()
COLUMNS = columns_model()


def _lower(instruction: WriteInstruction, model: Metamodel = DOCUMENT) -> list[LoweredStatement]:
    return lower_instruction(instruction, model)


def _document(statement: LoweredStatement, index: int = -1) -> object:
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
                    "joinedOn": dt.date(2026, 1, 15),
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
    # `joinedOn` is a managed `date`; the document stores the codec's portable
    # spelling, which for a date contains the same calendar characters —
    # what matters is that the value went THROUGH the encoding table rather than to a
    # serializer, which is what a `decimal` or `bytes` leaf would expose.
    (statement,) = _lower(
        KeyedWrite("insert", "Person", ({"id": 4, "joinedOn": dt.date(2026, 1, 15), "tags": []},))
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


def test_assigning_a_one_occurrence_binds_its_whole_subtree_at_its_own_path() -> None:
    # One path, one composite value, and no type test: the author stated a complete
    # `address`, so the statement writes that document rather than reaching inside the
    # stored one. `geo` is not named, and after this write the row does not hold it.
    (statement,) = _lower(KeyedWrite("update", "Person", ({"id": 1, "address": {"city": "Bodo"}},)))
    assert statement.sql == (
        "update person set payload = jsonb_set(payload, ?, cast(? as jsonb)) where id = ?"
    )
    assert statement.binds == ("{address}", JsonDocument({"city": "Bodo"}), 1)


def test_assigning_null_to_a_one_occurrence_writes_json_null() -> None:
    (statement,) = _lower(KeyedWrite("update", "Person", ({"id": 1, "address": None},)))
    assert statement.binds == ("{address}", "null", 1)


def test_assigning_a_many_occurrence_replaces_its_array_whole() -> None:
    (statement,) = _lower(
        KeyedWrite("update", "Person", ({"id": 1, "tags": [{"label": "member"}]},))
    )
    assert statement.binds == ("{tags}", JsonDocument([{"label": "member"}]), 1)


def test_one_and_many_assignments_render_the_identical_statement_shape() -> None:
    # The whole collapse in one assertion: cardinality selects no arm, so the two
    # occurrence kinds emit the same expression over their own paths and differ only
    # in the document each binds.
    (one,) = _lower(KeyedWrite("update", "Person", ({"id": 1, "address": {"city": "Bodo"}},)))
    (many,) = _lower(KeyedWrite("update", "Person", ({"id": 1, "tags": []},)))
    assert one.sql == many.sql


def test_a_nested_occurrence_rides_inside_the_document_its_parent_binds() -> None:
    # A nested occurrence is never independently assignable, so naming one inside an
    # authored `address` contributes a key to the ONE document that path binds rather
    # than a second path of its own.
    (statement,) = _lower(
        KeyedWrite(
            "update",
            "Person",
            ({"id": 1, "address": {"geo": {"country": "NO"}}},),
        )
    )
    assert statement.binds == ("{address}", JsonDocument({"geo": {"country": "NO"}}), 1)


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


def test_same_membered_rows_collapse_into_one_multi_row_insert() -> None:
    # The collapse the shared shape below admits: one column list and one value
    # tuple per row, each binding that row's own complete document.
    (statement,) = _lower(
        KeyedWrite(
            "insert", "Person", ({"id": 1, "displayName": "Ada"}, {"id": 2, "displayName": "Bo"})
        )
    )
    assert statement.sql == "insert into person(id, payload) values (?, ?), (?, ?)"
    assert _document(statement, 1) == {"displayName": "Ada", "tags": []}
    assert _document(statement, 3) == {"displayName": "Bo", "tags": []}


def test_two_rows_naming_different_document_members_do_not_share_one_statement() -> None:
    # Both rows select the same two columns — the Structured Column is NOT NULL and
    # binds on every insert — so under this layout the column list alone no longer
    # separates them. The Document Path is what does, and it must: every entry of
    # one Planned Insert has the same canonical member set (m-unit-work), so a run
    # answered same-shaped here is one the planner then refuses.
    person = entity(DOCUMENT, "Person")
    display_name = collapse_group_key(DOCUMENT, person, "insert", {"id": 1, "displayName": "Ada"})
    score = collapse_group_key(DOCUMENT, person, "insert", {"id": 2, "score": 7})
    same = collapse_group_key(DOCUMENT, person, "insert", {"id": 3, "displayName": "Bo"})
    assert display_name != score
    assert display_name == same
    with pytest.raises(ValueError, match="same members"):
        _lower(
            KeyedWrite("insert", "Person", ({"id": 1, "displayName": "Ada"}, {"id": 2, "score": 7}))
        )


def test_an_unnamed_many_occurrence_shares_a_statement_with_one_that_names_it() -> None:
    # The contrast with the split above: these two rows do NOT name different
    # members. Absence and the empty array are one logical zero state, so a row that
    # never mentions `tags` has said it holds none, and both rows write the same
    # document at the same column. Membership is what one Planned Insert's entries
    # must share, so a row whose zero state stayed implicit would fail that rule over
    # a statement it is byte-identical in.
    (statement,) = _lower(
        KeyedWrite(
            "insert",
            "Person",
            ({"id": 1, "displayName": "Ada", "tags": []}, {"id": 2, "displayName": "Bo"}),
        )
    )
    assert statement.sql == "insert into person(id, payload) values (?, ?), (?, ?)"
    assert _document(statement, 1) == {"displayName": "Ada", "tags": []}
    assert _document(statement, 3) == {"displayName": "Bo", "tags": []}


def test_the_columns_layout_twin_shares_a_statement_the_same_way() -> None:
    # The zero state is the model's, not the layout's: under `Columns` the occurrence
    # holds a Column of its own, and an insert binds `[]` there whether the row named
    # it or not — so the same two rows share one statement here too.
    (statement,) = _lower(
        KeyedWrite(
            "insert",
            "Person",
            ({"id": 1, "displayName": "Ada", "tags": []}, {"id": 2, "displayName": "Bo"}),
        ),
        COLUMNS,
    )
    assert statement.sql == (
        "insert into person(id, display_name, tags) values (?, ?, ?), (?, ?, ?)"
    )
    assert _document(statement, 2) == []
    assert _document(statement, 5) == []


def test_a_delete_groups_by_its_key_columns_under_either_layout() -> None:
    # A delete renders its identity predicate alone, so its selection is the key
    # columns and the document members it happens to carry are invisible.
    person = entity(DOCUMENT, "Person")
    assert collapse_group_key(
        DOCUMENT, person, "delete", {"id": 1, "displayName": "Ada"}
    ) == collapse_group_key(DOCUMENT, person, "delete", {"id": 2, "score": 7})


def test_a_no_op_occurrence_is_the_one_the_write_would_store_unchanged() -> None:
    # An assigned occurrence is compared whole, because the write it stands for
    # replaces the subtree whole. Naming only `city` is therefore a CHANGE against a
    # row holding `geo` — issuing it removes `geo`, so eliminating it would leave
    # stored state the assignment says is gone.
    person = entity(DOCUMENT, "Person")
    occurrences = {
        occurrence.identity.path[-1]: occurrence for occurrence in person.declared_value_objects
    }
    columns = {"address": ("address", True), "tags": ("tags", True)}
    row: dict[str, object] = {
        "address": {"city": "Bergen", "geo": {"country": "NO"}},
        "tags": [{"label": "founder"}],
    }

    assert is_no_op_assignment(
        columns,
        {"address": {"city": "Bergen", "geo": {"country": "NO"}}, "tags": [{"label": "founder"}]},
        row,
        occurrences,
    )
    assert not is_no_op_assignment(columns, {"address": {"city": "Bergen"}}, row, occurrences)
    assert not is_no_op_assignment(columns, {"address": {"city": "Oslo"}}, row, occurrences)
    assert not is_no_op_assignment(columns, {"tags": []}, row, occurrences)


# --------------------------------------------------------------------------- #
# A successor's Structured Column: patched from the predecessor's own retained #
# document rather than re-encoded from the members this model declares.        #
# --------------------------------------------------------------------------- #
_STORED: Final[dict[str, object]] = {
    "displayName": "Ada",
    "score": 7,
    "charterCode": "NB-118",
    "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": "S-4021"},
    "tags": [{"label": "founder"}],
}
"""One stored document carrying two keys `_document_layout_support` declares
nowhere — `charterCode` at the root and `sealNumber` inside the `address`
occurrence — which is what a newer version of an application writing this table
leaves behind."""


_DECODED: Final[dict[str, object]] = {
    "id": 1,
    "displayName": "Ada",
    "score": 7,
    "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": "S-4021"},
    "tags": [{"label": "founder"}],
}
"""The members a MATERIALIZING resolve observes over `_STORED`: its fan-out reads
each member through the codec, so an occurrence answers with the stored subtree as
it is, unknown keys included, while a key no member declares reaches no member at
all (`m-document-codec`)."""


_MATERIALIZED: Final[dict[str, object]] = {
    **_DECODED,
    "address": {"city": "Oslo", "geo": {"country": "NO"}},
}
"""The members a real `find` observes over the same row: materialization rebuilds
each occurrence from the members the model declares, so `sealNumber` is not among
them even though the stored subtree still carries it."""


def _successor(
    members: Mapping[str, object],
    *,
    document: object | None,
    origin: type[CarriedFrom] | type[ChangedFrom] | None,
    observed: Mapping[str, object] = _DECODED,
) -> object:
    """The Structured Column one opened row binds, given the milestone it succeeds.

    ``members`` is the successor's own complete row, exactly as temporal expansion
    composes one: ``observed`` with the mutation's changes overlaid.
    """
    person = entity(DOCUMENT, "Person")
    attributes = {
        attribute.identity: members[attribute.identity.name]
        for attribute in person.declared_attributes
        if attribute.identity.name in members
    }
    value_objects = {
        occurrence.identity: members[occurrence.identity.path[-1]]
        for occurrence in person.declared_value_objects
        if occurrence.identity.path[-1] in members
    }
    predecessor = PredecessorRow(observed, document=document)
    step = PlannedInsert(
        entity=PERSON,
        entries=(
            InsertEntry(
                row=PlannedRow(attributes=attributes, value_objects=value_objects),
                origin=NEW_LINEAGE if origin is None else origin(predecessor),
            ),
        ),
    )
    return _document(compile_write_step(step, DOCUMENT, POSTGRES))


def test_a_successor_patches_the_retained_document_so_an_unknown_key_survives() -> None:
    # The whole reason a successor is patched rather than re-encoded: `charterCode`
    # reaches no member, so a document rebuilt from the members this model declares
    # would have destroyed it.
    assert _successor(
        {**_DECODED, "displayName": "Dagny"}, document=_STORED, origin=ChangedFrom
    ) == {
        "displayName": "Dagny",
        "score": 7,
        "charterCode": "NB-118",
        "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": "S-4021"},
        "tags": [{"label": "founder"}],
    }


def test_a_carried_occurrence_keeps_the_unknown_keys_inside_its_own_subtree() -> None:
    # A successor's row restates every member, changed or not, so what tells a
    # carried occurrence from an assigned one is whether its value differs from the
    # observed one. `address` does not, so its subtree is never rebuilt and
    # `sealNumber` rides forward with it.
    successor = _successor({**_DECODED, "score": 21}, document=_STORED, origin=ChangedFrom)
    assert successor == {**_STORED, "score": 21}


def test_a_carried_occurrence_rides_forward_however_its_observation_spelled_it() -> None:
    # The two observation paths spell one occurrence differently — a materializing
    # resolve retains the stored subtree, a real find the members materialized out of
    # it — and a successor's carried half is copied out of whichever map its own
    # observation held. Carrying is decided against that same map, so `address` is
    # carried on both paths and `sealNumber` rides forward even where no observed
    # member names it.
    successor = _successor(
        {**_MATERIALIZED, "score": 21},
        document=_STORED,
        origin=ChangedFrom,
        observed=_MATERIALIZED,
    )
    assert successor == {**_STORED, "score": 21}


def test_an_assigned_one_replaces_its_subtree_while_the_root_carries_forward() -> None:
    # The unit of replacement is the assigned occurrence, not the row. `address` was
    # authored complete, so the omitted `geo` and the undeclared `sealNumber` inside
    # it are both gone — while `charterCode`, which sits OUTSIDE it and was never
    # mentioned, rides forward with the rest of the retained document.
    successor = _successor(
        {**_DECODED, "address": {"city": "Alta"}}, document=_STORED, origin=ChangedFrom
    )
    assert successor == {
        "displayName": "Ada",
        "score": 7,
        "charterCode": "NB-118",
        "address": {"city": "Alta"},
        "tags": [{"label": "founder"}],
    }


def test_an_assigned_many_replaces_the_predecessors_array() -> None:
    successor = _successor(
        {**_DECODED, "tags": [{"label": "member"}]}, document=_STORED, origin=ChangedFrom
    )
    assert successor == {**_STORED, "tags": [{"label": "member"}]}


def test_a_successor_that_changes_nothing_binds_the_retained_document_itself() -> None:
    # A Bitemporal head or tail carries its predecessor's state unchanged, so it has
    # nothing to patch and the document it binds is the one the closed row held.
    assert _successor(_DECODED, document=_STORED, origin=CarriedFrom) == _STORED


def test_a_successor_whose_observation_retained_no_document_composes_from_members() -> None:
    # Without a retained document there is nothing to preserve, so the row's own
    # complete member set composes the document exactly as a new lineage's does.
    assert _successor(_DECODED, document=None, origin=ChangedFrom) == _successor(
        _DECODED, document=None, origin=None
    )
