"""The positional Managed Row: packed stated cells, a presence mask, and
copy-with-change operations that move only what a stamp or overlay changes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

import pytest

from parallax.core import inheritance
from parallax.core.base import FrozenMap
from parallax.core.metamodel import AttributeIdentity, ValueObjectIdentity
from parallax.core.write_plan.managed_row import (
    ManagedRow,
    RowSelection,
    empty_row,
    managed_row,
    projected_row,
)
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

_ABSENT: Final = object()
_MODEL = corpus_model("branch")
_BRANCH = entity_of(_MODEL, "Branch")
_VIEW = inheritance.view(_MODEL).entity(_BRANCH.identity)
assert _VIEW is not None
_SELECTION = RowSelection(_VIEW.member_selection, _ABSENT)
_NAMES = tuple(member.name for member in _SELECTION.members.shape.members)
_ID = _NAMES.index("id")
_NAME = _NAMES.index("name")
_ADDRESS = _NAMES.index("address")


def _identity(name: str) -> AttributeIdentity:
    return AttributeIdentity(_BRANCH.identity, name)


def _row(**stated: object) -> ManagedRow:
    positions = sorted(_NAMES.index(name) for name in stated)
    presence = sum(1 << position for position in positions)
    return ManagedRow(_SELECTION, tuple(stated[_NAMES[p]] for p in positions), presence)


def test_a_row_packs_only_its_stated_members() -> None:
    row = _row(id=7, address=None)

    assert row.cells == (7, None)
    assert row.presence == 1 << _ID | 1 << _ADDRESS
    assert row.at(_ID) == 7
    assert row.at(_ADDRESS) is None
    assert row.at(_NAME) is _ABSENT
    assert row.cell(_identity("id")) == 7
    assert list(row.positions()) == [_ID, _ADDRESS]


def test_a_full_row_reads_each_cell_by_its_position() -> None:
    cells = tuple(range(len(_NAMES)))
    row = ManagedRow(_SELECTION, cells, _SELECTION.full_presence)

    assert [row.at(position) for position in range(len(_NAMES))] == list(cells)


@pytest.mark.parametrize(
    ("cells", "presence"),
    [((1,), 0), ((), 1), ((1,), 1 << 40)],
)
def test_a_row_refuses_cells_its_presence_does_not_state(
    cells: tuple[object, ...], presence: int
) -> None:
    with pytest.raises(ValueError, match="Managed Row"):
        ManagedRow(_SELECTION, cells, presence)


def test_an_empty_row_states_nothing_and_still_compares() -> None:
    assert empty_row(_SELECTION).presence == 0
    assert empty_row(_SELECTION) == ManagedRow(_SELECTION, (), 0)


def test_with_cell_replaces_or_inserts_at_the_members_rank() -> None:
    row = _row(id=7, address=None)

    assert row.with_cell(_ID, 8) == _row(id=8, address=None)
    assert row.with_cell(_NAME, "Oslo") == _row(id=7, name="Oslo", address=None)
    assert row.with_cell(_NAME, "Oslo").selection is _SELECTION


def test_with_cells_stamps_several_positions_in_one_copy() -> None:
    stamped = _row(id=7).with_cells((_ADDRESS, _NAME), (None, "Oslo"))

    assert stamped == _row(id=7, name="Oslo", address=None)


def test_with_members_of_lets_the_overlay_win() -> None:
    base = _row(id=7, name="Ada")
    overlay = _row(id=7, address=None)

    assert base.with_members_of(overlay) == _row(id=7, name="Ada", address=None)
    assert base.with_members_of(empty_row(_SELECTION)) is base


def test_without_drops_stated_members() -> None:
    assert _row(id=7, name="Ada").without(1 << _ID) == _row(name="Ada")
    row = _row(name="Ada")
    assert row.without(1 << _ID) is row


def test_identity_views_read_over_the_cells() -> None:
    nested = ("Main", None, _ABSENT, ())
    row = _row(id=7, address=nested)

    assert dict(row.attributes) == {_identity("id"): 7}
    (occurrence,) = row.value_objects
    assert occurrence == ValueObjectIdentity(_BRANCH.identity, ("address",))
    viewed = cast("Mapping[str, object]", row.value_objects[occurrence])
    assert dict(viewed) == {"street": "Main", "city": None, "phones": ()}
    assert _identity("name") not in row.attributes


def test_a_projected_row_moves_occurrence_documents_to_positional_form() -> None:
    document = FrozenMap({"street": "Main", "phones": (FrozenMap({"number": "1"}),)})

    row = projected_row(_SELECTION, {"name": "Ada", "id": 7, "address": document})

    assert row == _row(id=7, name="Ada", address=("Main", _ABSENT, _ABSENT, ((_ABSENT, "1"),)))


def test_a_projected_row_refuses_an_undeclared_member() -> None:
    with pytest.raises(ValueError, match="only members"):
        projected_row(_SELECTION, {"id": 7, "undeclared": 1})


def test_a_trusted_row_adopts_its_cells_by_reference() -> None:
    cells = (7,)

    assert managed_row(_SELECTION, cells, 1 << _ID).cells is cells
