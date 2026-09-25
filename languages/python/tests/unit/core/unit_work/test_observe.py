"""Entity State row views (`parallax.core.unit_work.observe`).

The Mapping contract of the positional view over one decoded Entity State, keyed
by declared member name, and of the nested Value Object views it exposes, driven
directly through the Mapping interface over layouts whose declared and storage
names differ.
"""

from __future__ import annotations

from collections.abc import ItemsView, Mapping
from typing import cast

import pytest

from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout, LayoutCatalog
from parallax.core.unit_work import EntityStateRow, PredecessorRow
from tests.unit._document_layout_support import PERSON, columns_model, document_model

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


def test_a_declared_row_is_retained_by_a_predecessor_row_as_itself() -> None:
    row = _declared()
    predecessor = PredecessorRow(row)

    assert predecessor.members is row
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
