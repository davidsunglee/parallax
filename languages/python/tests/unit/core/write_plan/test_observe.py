"""Entity State row views and Predecessor Rows (`parallax.core.write_plan.observe`).

The Mapping contract of the positional view over one decoded Entity State, keyed
by declared member name, and of the nested Value Object views it exposes, driven
directly through the Mapping interface over layouts whose declared and storage
names differ; and a Predecessor Row's identity-keyed reads and carried-cell test
over both a trusted positional row and a caller-supplied mapping.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import ItemsView, Mapping
from typing import cast

import pytest

from parallax.core import Entity, inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout, LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.temporal_read import Bitemporal, milestone_edge, valid_time_coverage
from parallax.core.write_plan import EntityStateRow, PredecessorRow
from parallax.core.write_plan.observe import AssignedComparison
from tests.unit import _predicate_acquisition_support as acquisition
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._document_layout_support import PERSON, columns_model, document_model
from tests.unit._positional_row_support import positional_row

_DOCUMENT_LAYOUT: EntityLayout = LayoutCatalog(document_model()).entity(PERSON)
_COLUMNS_LAYOUT: EntityLayout = LayoutCatalog(columns_model()).entity(PERSON)

# One Person row as a Page holds it: `id`, `displayName`, `score`, `joinedOn`,
# then `address` (city, geo(country)) and `tags` (label), positional throughout.
# `score` was not read, `joinedOn` is stored null, the address's `geo` was not
# stored, and the second tag's label is stored null.
_VALUES: tuple[object, ...] = (
    7,
    "Ada",
    ABSENT,
    None,
    ("Bergen", ABSENT),
    (("founder",), (None,)),
)
_DECLARED_NAMES = ("id", "displayName", "score", "joinedOn", "address", "tags")


def _declared(values: tuple[object, ...] = _VALUES) -> EntityStateRow:
    return EntityStateRow.over_declared_members(
        _DOCUMENT_LAYOUT.member_selection, values, absent=ABSENT
    )


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(nested) for key, nested in cast("Mapping[str, object]", value).items()}
    if isinstance(value, tuple):
        return tuple(_plain(nested) for nested in cast("tuple[object, ...]", value))
    return value


# --------------------------------------------------------------------------- #
# The declared-name row: full width over the canonical selection.             #
# --------------------------------------------------------------------------- #
def test_a_declared_row_answers_every_canonical_member_by_declared_name() -> None:
    row = _declared()

    assert row["id"] == 7
    assert row["displayName"] == "Ada"
    assert row["joinedOn"] is None
    assert list(row) == list(_DECLARED_NAMES)
    assert len(row) == len(_DECLARED_NAMES) == len(_DOCUMENT_LAYOUT.member_selection.bindings)
    with pytest.raises(KeyError):
        row["display_name"]
    with pytest.raises(KeyError):
        row["nope"]
    assert row.get("display_name") is None
    assert "display_name" not in row
    assert "nope" not in row


def test_a_declared_row_keeps_a_known_absent_slot_as_a_present_key() -> None:
    row = _declared()

    assert row["score"] is ABSENT
    assert row.get("score", "fallback") is ABSENT
    assert "score" in row
    assert "score" in list(row)
    assert ("score", ABSENT) in row.items()
    assert dict(row.items())["score"] is ABSENT


def test_a_declared_row_rejects_a_member_row_of_another_width() -> None:
    with pytest.raises(ValueError, match="align"):
        _declared(_VALUES[:-1])
    with pytest.raises(ValueError, match="align"):
        _declared((*_VALUES, "extra"))


def test_a_declared_row_preserves_null_and_empty_many_values() -> None:
    row = _declared((7, None, ABSENT, None, None, ()))

    assert row["displayName"] is None
    assert row["address"] is None
    assert row["tags"] == ()
    assert dict(row.items()) == {
        "id": 7,
        "displayName": None,
        "score": ABSENT,
        "joinedOn": None,
        "address": None,
        "tags": (),
    }


def test_a_declared_row_constructed_directly_is_owned_by_its_predecessor_row() -> None:
    row = _declared()
    predecessor = PredecessorRow(row)

    assert predecessor.members is not row
    assert _plain(dict(predecessor.members)) == _plain(dict(row))
    assert predecessor.member("displayName") == "Ada"
    assert predecessor.document is None


# --------------------------------------------------------------------------- #
# Nested Value Object views: shape-backed, absent slots are no key.            #
# --------------------------------------------------------------------------- #
def test_a_nested_one_occurrence_reads_through_its_declaration_shape() -> None:
    address = cast("Mapping[str, object]", _declared()["address"])

    assert address["city"] == "Bergen"
    assert list(address) == ["city"]
    assert len(address) == 1
    with pytest.raises(KeyError):
        address["geo"]
    assert address.get("geo", "fallback") == "fallback"
    assert "geo" not in address
    with pytest.raises(KeyError):
        address["nope"]
    assert list(address.items()) == [("city", "Bergen")]


def test_a_nested_occurrence_distinguishes_null_from_absent_at_every_depth() -> None:
    row = _declared((7, "Ada", ABSENT, None, (None, (None,)), ()))
    address = cast("Mapping[str, object]", row["address"])
    geo = cast("Mapping[str, object]", address["geo"])

    assert address["city"] is None
    assert "city" in address
    assert geo["country"] is None
    assert list(geo.items()) == [("country", None)]
    assert _plain(address) == {"city": None, "geo": {"country": None}}


def test_a_nested_many_occurrence_is_one_view_per_element_over_one_shape() -> None:
    tags = cast("tuple[Mapping[str, object], ...]", _declared()["tags"])

    assert len(tags) == 2
    assert tags[0]["label"] == "founder"
    assert tags[1]["label"] is None
    assert [dict(tag) for tag in tags] == [{"label": "founder"}, {"label": None}]
    assert [list(tag) for tag in tags] == [["label"], ["label"]]


def test_nested_views_are_built_per_access_and_never_cached() -> None:
    row = _declared()

    first = row["address"]
    second = row["address"]
    assert first is not second
    assert first == second
    assert _plain(first) == {"city": "Bergen"}
    assert row["tags"] is not row["tags"]
    assert row["tags"] == row["tags"]


# --------------------------------------------------------------------------- #
# Items views: re-iterable Mapping views, never one-shot generators.           #
# --------------------------------------------------------------------------- #
def test_a_declared_rows_items_view_is_a_re_iterable_mapping_view() -> None:
    row = _declared()
    items = row.items()

    assert isinstance(items, ItemsView)
    assert len(items) == len(row)
    assert ("displayName", "Ada") in items
    assert ("score", ABSENT) in items
    assert ("displayName", "Grace") not in items
    assert ("nope", "Ada") not in items
    first_pass = [(name, _plain(value)) for name, value in items]
    second_pass = [(name, _plain(value)) for name, value in items]
    assert first_pass == second_pass
    assert [name for name, _value in items] == list(_DECLARED_NAMES)
    one = iter(items)
    other = iter(items)
    assert next(one)[0] == "id"
    assert [name for name, _value in other] == list(_DECLARED_NAMES)
    assert [name for name, _value in one] == list(_DECLARED_NAMES)[1:]
    assert _plain(dict(items)) == {
        "id": 7,
        "displayName": "Ada",
        "score": ABSENT,
        "joinedOn": None,
        "address": {"city": "Bergen"},
        "tags": ({"label": "founder"}, {"label": None}),
    }


def test_a_nested_views_items_view_omits_absent_slots_and_stays_re_iterable() -> None:
    address = cast("Mapping[str, object]", _declared()["address"])
    items = address.items()

    assert isinstance(items, ItemsView)
    assert len(items) == 1
    assert ("city", "Bergen") in items
    assert ("geo", ABSENT) not in items
    assert list(items) == list(items) == [("city", "Bergen")]


def test_both_layout_twins_expose_one_positional_row_identically() -> None:
    columns_twin = EntityStateRow.over_declared_members(
        _COLUMNS_LAYOUT.member_selection, _VALUES, absent=ABSENT
    )

    assert _plain(dict(columns_twin.items())) == _plain(dict(_declared().items()))


# --------------------------------------------------------------------------- #
# The trusted Predecessor Row: one positional row adopted by reference.        #
# --------------------------------------------------------------------------- #
_SELECTION = _DOCUMENT_LAYOUT.member_selection
_ID, _DISPLAY_NAME, _SCORE, _JOINED_ON = (attribute.identity for attribute in _SELECTION.attributes)
_ADDRESS, _TAGS = (occurrence.identity for occurrence in _SELECTION.value_objects)


def _adopted(
    values: tuple[object, ...] = _VALUES, document: object | None = None
) -> PredecessorRow:
    return PredecessorRow.over_row(_SELECTION, values, document, ABSENT)


def test_a_trusted_predecessor_row_adopts_its_row_and_document_without_copying() -> None:
    document: dict[str, object] = {"displayName": "Ada", "unknown": [1]}
    predecessor = _adopted(document=document)

    assert predecessor.document is document
    assert _plain(dict(predecessor.members)) == _plain(dict(_declared()))
    assert predecessor.member("displayName") == "Ada"
    assert predecessor == PredecessorRow(_declared(), document=document)


def test_a_trusted_predecessor_row_reads_each_member_by_identity() -> None:
    predecessor = _adopted()

    assert [_plain(predecessor.cell(binding.identity)) for binding in _SELECTION.bindings] == [
        _plain(_declared()[name]) for name in _DECLARED_NAMES
    ]
    assert predecessor.axis_start(None, _ID) == 7
    assert predecessor.axis_start(None, AttributeIdentity(PERSON, "txStart")) is None


def test_identity_maps_hold_each_cell_and_view_each_occurrence_over_its_own_cell() -> None:
    predecessor = _adopted()

    attributes, value_objects = predecessor.identity_maps(_SELECTION)
    again, again_objects = predecessor.identity_maps(_SELECTION)

    assert list(attributes) == [_ID, _DISPLAY_NAME, _SCORE, _JOINED_ON]
    assert list(value_objects) == [_ADDRESS, _TAGS]
    assert all(attributes[member] is _VALUES[index] for index, member in enumerate(attributes))
    assert _plain(value_objects[_ADDRESS]) == {"city": "Bergen"}
    assert _plain(value_objects[_TAGS]) == ({"label": "founder"}, {"label": None})
    assert again is not attributes
    assert again_objects[_ADDRESS] is not value_objects[_ADDRESS]


def test_a_mapping_backed_predecessor_maps_its_own_stored_values() -> None:
    predecessor = PredecessorRow({"id": 7, "address": {"city": "Bergen"}})
    address = predecessor.member("address")

    attributes, value_objects = predecessor.identity_maps(_SELECTION)

    assert attributes == {_ID: 7}
    assert value_objects[_ADDRESS] is address
    assert predecessor.cell(_ID) == 7
    assert predecessor.cell(_ADDRESS) is address
    assert predecessor.axis_start(None, _ID) == 7


def test_a_predecessor_member_its_selection_lacks_is_a_broken_invariant() -> None:
    # Row construction and case ingress refuse an undeclared logical member, so
    # one reaching identity mapping is a defect, never an input to report.
    with pytest.raises(AssertionError, match="'nickname' is not a selection member"):
        PredecessorRow({"id": 7, "nickname": "Ada"}).identity_maps(_SELECTION)


def test_direct_predecessor_construction_owns_its_members_and_document() -> None:
    members: dict[str, object] = {"id": 1, "address": {"city": "Oslo"}}
    stored: dict[str, object] = {"title": "Ada", "manifest": {"cargo": "timber"}}
    predecessor = PredecessorRow(members, document=stored)

    cast("dict[str, object]", members["address"])["city"] = "Bergen"
    cast("dict[str, object]", stored["manifest"])["cargo"] = "ore"

    assert predecessor.member("address") == {"city": "Oslo"}
    assert predecessor.document == {"title": "Ada", "manifest": {"cargo": "timber"}}

    viewed: dict[str, object] = {"id": 1, "address": {"city": "Oslo"}}
    from_view = PredecessorRow(EntityStateRow(viewed))
    viewed["id"] = 2
    cast("dict[str, object]", viewed["address"])["city"] = "Bergen"

    assert from_view.member("id") == 1
    assert from_view.member("address") == {"city": "Oslo"}
    with pytest.raises(ValueError, match="complete state"):
        PredecessorRow({})


# --------------------------------------------------------------------------- #
# Axis ends and Valid-Time coverage, read from the row the predecessor holds.  #
# --------------------------------------------------------------------------- #
_BITEMPORAL_MODEL = model_of(acquisition.MODEL)
_VALID_FROM = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
_VALID_UNTIL = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
_OPENED = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
_BITEMPORAL_LAYOUTS = pytest.mark.parametrize(
    "entity",
    [acquisition.AcquisitionColumns, acquisition.AcquisitionDocument],
    ids=["columns", "document"],
)
_VALID_ENDS = pytest.mark.parametrize("valid_end", [_VALID_UNTIL, INFINITY], ids=["finite", "open"])
_TEMPORAL_MEMBERS = ("id", "validStart", "validEnd", "txStart", "txEnd")


def _valid_time(entity: type[Entity]) -> Bitemporal:
    shape = temporal_read.view(_BITEMPORAL_MODEL).shape(entity.identity)
    assert isinstance(shape, Bitemporal)
    return shape


def _milestone(entity: type[Entity], valid_end: object, *, adopted: bool) -> PredecessorRow:
    """One stored milestone of ``entity``, adopted positionally or held by name."""
    cells: dict[str, object] = {
        "id": 1,
        "title": "Ada",
        "validStart": _VALID_FROM,
        "validEnd": valid_end,
        "txStart": _OPENED,
        "txEnd": INFINITY,
        "address": {"city": "Oslo", "geo": {"country": "NO"}},
        "tags": [{"label": "founder"}],
    }
    if not adopted:
        return PredecessorRow({name: cells[name] for name in _TEMPORAL_MEMBERS})
    selection = LayoutCatalog(_BITEMPORAL_MODEL).entity(entity.identity).member_selection
    row = positional_row(selection.shape, cells, absent=ABSENT)
    return PredecessorRow.over_row(selection, row, None, ABSENT)


@_BITEMPORAL_LAYOUTS
@_VALID_ENDS
@pytest.mark.parametrize("adopted", [True, False], ids=["adopted", "by-name"])
def test_a_predecessor_rows_coverage_references_its_own_valid_time_cells(
    entity: type[Entity], valid_end: object, adopted: bool
) -> None:
    predecessor = _milestone(entity, valid_end, adopted=adopted)
    axis = _valid_time(entity).valid_time

    coverage = valid_time_coverage(_valid_time(entity), predecessor, None)

    assert predecessor.axis_end(None, axis.end_attribute) is valid_end
    assert coverage is not None
    assert coverage.start is _VALID_FROM
    assert coverage.end is valid_end


def test_a_predecessor_row_without_an_axis_end_member_answers_none_for_it() -> None:
    absent = AttributeIdentity(PERSON, "validEnd")

    assert _adopted().axis_end(None, absent) is None
    assert PredecessorRow({"id": 7}).axis_end(None, absent) is None


@_BITEMPORAL_LAYOUTS
@pytest.mark.parametrize("adopted", [True, False], ids=["adopted", "by-name"])
def test_a_predecessor_rows_edge_reads_no_axis_end(
    monkeypatch: pytest.MonkeyPatch, entity: type[Entity], adopted: bool
) -> None:
    def refuse(*_arguments: object) -> object:
        raise AssertionError("an edge read an axis end")

    predecessor = _milestone(entity, INFINITY, adopted=adopted)
    monkeypatch.setattr(PredecessorRow, "axis_end", refuse)

    edge = milestone_edge(_valid_time(entity), predecessor, None)

    assert (edge.valid_time, edge.tx_time) == (_VALID_FROM, _OPENED)


def test_a_predecessor_row_carrying_no_member_is_refused() -> None:
    # A Temporal Observation retains the whole predecessor or none of it: a
    # partial one would silently drop members temporal expansion carries forward.
    with pytest.raises(ValueError, match="complete state"):
        PredecessorRow(members={})


# --------------------------------------------------------------------------- #
# A scalar collection holds an assignment only element for element, in order.  #
# --------------------------------------------------------------------------- #
_COLLECTION_SELECTION = (
    inheritance.view(corpus_model("scalar-collection-layout-twin-columns"))
    .entity(EntityIdentity("parallax.compatibility", "CollectionTwinItem"))
    .member_selection  # pyright: ignore[reportOptionalMemberAccess] - the corpus declares it
)


def _collection_predecessor(tags: object, detail: object) -> PredecessorRow:
    # `id`, eleven empty collections around `tags`, then `detail` and `parts`.
    values = (1, (), (), (), (), (), (), tags, (), (), (), (), (), detail, ())
    return PredecessorRow.over_row(_COLLECTION_SELECTION, values, None, ABSENT)


@pytest.mark.parametrize(
    ("stored", "assigned", "held"),
    [
        (("b", "a", "b"), ("b", "a", "b"), True),
        (("b", "a", "b"), ["b", "a", "b"], True),
        (("b", "a", "b"), ("a", "b", "b"), False),
        (("b", "a", "b"), ("b", "a"), False),
        ((), (), True),
        ((), ("b",), False),
    ],
)
def test_a_top_level_collection_holds_only_its_own_elements_in_order(
    stored: tuple[str, ...], assigned: object, held: bool
) -> None:
    comparison = AssignedComparison(_COLLECTION_SELECTION, {"tags": assigned})

    assert _collection_predecessor(stored, None).holds(comparison) is held


@pytest.mark.parametrize(
    ("stored", "assigned", "held"),
    [
        ((("x", "y"),), {"labels": ("x", "y")}, True),
        ((("x", "y"),), {"labels": ("y", "x")}, False),
        ((ABSENT,), {"labels": ()}, True),
        ((ABSENT,), {}, True),
        ((("x",),), {}, False),
    ],
)
def test_a_nested_collection_holds_as_part_of_its_whole_occurrence(
    stored: tuple[object, ...], assigned: dict[str, object], held: bool
) -> None:
    comparison = AssignedComparison(_COLLECTION_SELECTION, {"detail": assigned})

    assert _collection_predecessor((), stored).holds(comparison) is held
