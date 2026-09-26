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

import copy
import datetime as dt
from collections.abc import Mapping
from typing import Final, cast

import pytest

from parallax.core import storage_layout
from parallax.core.base import FrozenMap, retain_document_value
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import _managed as managed
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.sql_gen import LoweredStatement
from parallax.core.sql_gen._write import (
    _successor_patches,  # pyright: ignore[reportPrivateUsage] - patch-selection property only
    compile_write_step,
)
from parallax.core.storage_layout import DocumentResidentSelection
from parallax.core.unit_work import KeyedWrite, PredecessorRow
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.core.unit_work.observe import (
    _EntityDocumentRow as _EntityDocumentRowType,  # pyright: ignore[reportPrivateUsage] - comparison spy only
)
from parallax.core.unit_work.planned import (
    NEW_LINEAGE,
    CarriedFrom,
    ChangedFrom,
    InsertEntry,
    InsertOrigin,
    PlannedInsert,
    PlannedRow,
)
from parallax.snapshot.handle._keyed_sql import collapse_group_key
from tests._support.lowering_probes import lower_instruction
from tests.unit._document_layout_support import PERSON, columns_model, document_model, entity

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
    assert statement.binds == ("{tags}", JsonDocument(({"label": "member"},)), 1)


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
    assert _document(statement, 2) == ()
    assert _document(statement, 5) == ()


def test_a_delete_groups_by_its_key_columns_under_either_layout() -> None:
    # A delete renders its identity predicate alone, so its selection is the key
    # columns and the document members it happens to carry are invisible.
    person = entity(DOCUMENT, "Person")
    assert collapse_group_key(
        DOCUMENT, person, "delete", {"id": 1, "displayName": "Ada"}
    ) == collapse_group_key(DOCUMENT, person, "delete", {"id": 2, "score": 7})


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


_SELECTION = LayoutCatalog(DOCUMENT).entity(PERSON).member_selection


def _successor_maps(
    predecessor: PredecessorRow, changes: Mapping[str, object]
) -> tuple[dict[AttributeIdentity, object], dict[ValueObjectIdentity, object]]:
    """A changed successor's complete row as temporal expansion composes one:
    the predecessor's own cells, with ``changes`` overlaid as authored values."""
    attributes, value_objects = predecessor.identity_maps(_SELECTION)
    for name, value in changes.items():
        binding = _SELECTION.binding(name)
        assert binding is not None
        if isinstance(binding, AttributeMetadata):
            attributes[binding.identity] = value
        else:
            value_objects[binding.identity] = retain_document_value(value)
    return attributes, value_objects


def _opened(
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
    origin: InsertOrigin,
) -> object:
    step = PlannedInsert(
        entity=PERSON,
        entries=(
            InsertEntry(
                row=PlannedRow(attributes=attributes, value_objects=value_objects),
                origin=origin,
            ),
        ),
    )
    return _document(compile_write_step(step, DOCUMENT, POSTGRES))


def _successor(
    changes: Mapping[str, object],
    *,
    document: object | None,
    origin: type[CarriedFrom] | type[ChangedFrom] | None,
    observed: Mapping[str, object] = _DECODED,
) -> object:
    """The Structured Column one opened row binds, given the milestone it succeeds
    and the members it changed."""
    predecessor = PredecessorRow(observed, document=document)
    attributes, value_objects = _successor_maps(predecessor, changes)
    return _opened(
        attributes, value_objects, NEW_LINEAGE if origin is None else origin(predecessor)
    )


def test_a_successor_patches_the_retained_document_so_an_unknown_key_survives() -> None:
    # The whole reason a successor is patched rather than re-encoded: `charterCode`
    # reaches no member, so a document rebuilt from the members this model declares
    # would have destroyed it.
    assert _successor({"displayName": "Dagny"}, document=_STORED, origin=ChangedFrom) == {
        "displayName": "Dagny",
        "score": 7,
        "charterCode": "NB-118",
        "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": "S-4021"},
        "tags": [{"label": "founder"}],
    }


def test_a_carried_occurrence_keeps_the_unknown_keys_inside_its_own_subtree() -> None:
    # A changed successor carries every member it did not change as its
    # predecessor's own cell, so `address` is never rebuilt and `sealNumber`
    # rides forward with it.
    successor = _successor({"score": 21}, document=_STORED, origin=ChangedFrom)
    assert successor == {**_STORED, "score": 21}


def test_a_carried_occurrence_rides_forward_however_its_observation_spelled_it() -> None:
    # The two observation paths spell one occurrence differently — a materializing
    # resolve retains the stored subtree, a real find the members materialized out of
    # it — and either way the successor carries the observation's own cell, so
    # `address` is carried and `sealNumber` rides forward even where no observed
    # member names it.
    successor = _successor(
        {"score": 21}, document=_STORED, origin=ChangedFrom, observed=_MATERIALIZED
    )
    assert successor == {**_STORED, "score": 21}


def test_a_restated_equal_value_is_a_change_because_carrying_is_identity() -> None:
    # Lowering never compares values: a member the successor holds as anything
    # but its predecessor's own cell was changed by its producer, so an equal
    # but distinct `address` replaces the stored subtree and `sealNumber` with it.
    successor = _successor(
        {"address": {"city": "Oslo", "geo": {"country": "NO"}}},
        document=_STORED,
        origin=ChangedFrom,
        observed=_MATERIALIZED,
    )
    assert successor == {**_STORED, "address": {"city": "Oslo", "geo": {"country": "NO"}}}


def test_an_assigned_one_replaces_its_subtree_while_the_root_carries_forward() -> None:
    # The unit of replacement is the assigned occurrence, not the row. `address` was
    # authored complete, so the omitted `geo` and the undeclared `sealNumber` inside
    # it are both gone — while `charterCode`, which sits OUTSIDE it and was never
    # mentioned, rides forward with the rest of the retained document.
    successor = _successor({"address": {"city": "Alta"}}, document=_STORED, origin=ChangedFrom)
    assert successor == {
        "displayName": "Ada",
        "score": 7,
        "charterCode": "NB-118",
        "address": {"city": "Alta"},
        "tags": [{"label": "founder"}],
    }


def test_an_assigned_many_replaces_the_predecessors_array() -> None:
    successor = _successor({"tags": [{"label": "member"}]}, document=_STORED, origin=ChangedFrom)
    assert successor == {**_STORED, "tags": [{"label": "member"}]}


def test_a_carried_successor_binds_the_retained_document_itself() -> None:
    # A Bitemporal head or tail carries its predecessor's state unchanged, so it has
    # nothing to patch and the document it binds is the one the closed row held.
    retained = retain_document_value(_STORED)
    assert _successor({}, document=retained, origin=CarriedFrom) is retained


def test_a_changed_successor_that_carries_every_cell_binds_the_retained_document() -> None:
    retained = retain_document_value(_STORED)
    assert _successor({}, document=retained, origin=ChangedFrom) is retained


def test_a_successor_whose_observation_retained_no_document_composes_from_members() -> None:
    # Without a retained document there is nothing to preserve, so the row's own
    # complete member set composes the document exactly as a new lineage's does.
    assert _successor({}, document=None, origin=ChangedFrom) == _successor(
        {}, document=None, origin=None
    )


# --------------------------------------------------------------------------- #
# Patches over a trusted positional predecessor: shared cells, identity only. #
# --------------------------------------------------------------------------- #
_POSITIONAL: Final[tuple[object, ...]] = (
    1,
    "Ada",
    7,
    ABSENT,
    ("Oslo", ("NO",)),
    (("founder",), ("member",)),
)
_STORED_ROW: Final[dict[str, object]] = {
    "displayName": "Ada",
    "score": 7,
    "charterCode": "NB-118",
    "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": "S-4021"},
    "tags": [{"label": "founder"}, {"label": "member"}],
}
_CHANGES: Final[tuple[tuple[str, object], ...]] = (
    ("displayName", "Dagny"),
    ("score", 7),
    ("score", 8),
    ("joinedOn", dt.date(2026, 1, 15)),
    ("joinedOn", None),
    ("address", {"city": "Oslo", "geo": {"country": "NO"}}),
    ("address", None),
    ("tags", ({"label": "founder"}, {"label": "member"})),
    ("tags", ()),
)


def _residents() -> DocumentResidentSelection:
    view = storage_layout.view(DOCUMENT).entity(PERSON)
    assert view is not None
    resident = view.document_residents
    assert resident is not None
    return resident


def _positional_predecessor(document: object) -> PredecessorRow:
    return PredecessorRow.over_row(_SELECTION, _POSITIONAL, document, ABSENT)


def _patch_paths(
    predecessor: PredecessorRow,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> list[tuple[str, ...]]:
    resident = _residents()
    return [
        patch.path for patch in _successor_patches(resident, attributes, value_objects, predecessor)
    ]


def test_patches_are_exactly_the_resident_members_the_predecessor_does_not_carry() -> None:
    # Every combination of changes, equal restatements included, over both a
    # trusted positional predecessor and a caller-supplied mapping.
    for selected in range(1 << len(_CHANGES)):
        _assert_patches_follow_carrying(
            dict(change for index, change in enumerate(_CHANGES) if selected & (1 << index))
        )


def _assert_patches_follow_carrying(changes: Mapping[str, object]) -> None:
    for predecessor in (
        _positional_predecessor(_STORED_ROW),
        PredecessorRow(
            {"id": 1, "displayName": "Ada", "score": 7, "address": {"city": "Oslo"}, "tags": ()},
            document=_STORED_ROW,
        ),
    ):
        attributes, value_objects = _successor_maps(predecessor, changes)
        resident = _residents()
        expected = [
            placement.path
            for position, placement in zip(resident.positions, resident.placements, strict=True)
            for binding in (_SELECTION.bindings[position],)
            for values in (
                cast(
                    "Mapping[object, object]",
                    attributes if isinstance(binding, AttributeMetadata) else value_objects,
                ),
            )
            if binding.identity in values
            and not predecessor.carries(binding.identity, values[binding.identity])
        ]
        assert _patch_paths(predecessor, attributes, value_objects) == expected
        assert set(expected) <= {
            placement.path
            for placement, name in zip(
                resident.placements,
                (_SELECTION.shape.members[position].name for position in resident.positions),
                strict=True,
            )
            if name in changes
        }


def test_lowering_a_changed_successor_compares_no_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A changed successor's patches come from identity alone: lowering calls no
    # equality between mapping carriers and no codec comparison.
    def compared(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("lowering compared a successor's values")

    predecessor = _positional_predecessor(_STORED_ROW)
    attributes, value_objects = _successor_maps(
        predecessor, {"score": 8, "address": {"city": "Alta"}}
    )
    monkeypatch.setattr(FrozenMap, "__eq__", compared)
    monkeypatch.setattr(_EntityDocumentRowType, "__eq__", compared)
    monkeypatch.setattr(managed, "_structurally_equal", compared)
    monkeypatch.setattr(managed, "_canonical_member", compared)
    monkeypatch.setattr(managed, "classify_effective_change", compared)
    opened = _opened(attributes, value_objects, ChangedFrom(predecessor))
    monkeypatch.undo()
    assert opened == {
        **_STORED_ROW,
        "score": 8,
        "address": {"city": "Alta"},
    }


def test_lowering_leaves_the_retained_document_as_it_found_it() -> None:
    stored = copy.deepcopy(_STORED_ROW)
    predecessor = _positional_predecessor(stored)
    attributes, value_objects = _successor_maps(
        predecessor, {"score": 8, "tags": [{"label": "member"}], "address": None}
    )
    _opened(attributes, value_objects, ChangedFrom(predecessor))
    _opened(*predecessor.identity_maps(_SELECTION), CarriedFrom(predecessor))
    assert stored == _STORED_ROW
    assert predecessor.document is stored
