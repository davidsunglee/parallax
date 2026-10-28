from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from parallax.core.metamodel import (
    AttributeIdentity,
    MemberDefinition,
    MemberIdentity,
    Multiplicity,
    OccurrenceDefinition,
    ScalarDefinition,
    ValueObjectIdentity,
)
from parallax.core.write_plan.observe import occurrence_value

if TYPE_CHECKING:
    from parallax.core.inheritance import EntityMemberSelection

__all__ = [
    "ManagedRow",
    "RowSelection",
    "empty_row",
    "managed_row",
    "positional_occurrence",
    "projected_row",
]


@dataclass(frozen=True, slots=True)
class RowSelection:
    """One Entity's member selection beside the marker its accepted Entity
    State spells an omitted nested member with.

    Shared by every row of the Entity, so a row holds neither its selection's
    facts nor the marker itself.
    """

    members: EntityMemberSelection
    absent: object
    full_presence: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "full_presence", (1 << len(self.members.shape.members)) - 1)

    def position(self, member: MemberIdentity) -> int:
        return self.members.index[member]

    def name_position(self, name: str) -> int | None:
        return self.members.shape.position(name)


@dataclass(frozen=True, slots=True)
class ManagedRow:
    """The members one prepared write states, packed in member order.

    Bit ``i`` of ``presence`` is set exactly when member ``i`` is stated, an
    explicit null included, and ``cells`` holds the stated members' values in
    order, so ``len(cells) == presence.bit_count()``. A top-level cell is a
    managed value, ``None``, or a planned expression its role authorized; a
    nested occurrence keeps the read side's full-width positional form. An
    unstated member reads as ``selection.absent``.
    """

    selection: RowSelection
    cells: tuple[object, ...]
    presence: int

    def __post_init__(self) -> None:
        if self.presence < 0 or self.presence & ~self.selection.full_presence:
            raise ValueError("a Managed Row states only members of its selection")
        if len(self.cells) != self.presence.bit_count():
            raise ValueError("a Managed Row holds one cell per stated member")

    def stated(self, position: int) -> bool:
        return bool(self.presence >> position & 1)

    def at(self, position: int) -> object:
        """Member ``position``'s cell, or ``selection.absent`` when unstated."""
        presence = self.presence
        if not presence >> position & 1:
            return self.selection.absent
        if presence == self.selection.full_presence:
            return self.cells[position]
        return self.cells[(presence & ((1 << position) - 1)).bit_count()]

    def cell(self, member: MemberIdentity) -> object:
        """``member``'s cell, or ``selection.absent`` when unstated."""
        return self.at(self.selection.members.index[member])

    def positions(self) -> Iterator[int]:
        """The stated positions, ascending."""
        presence = self.presence
        position = 0
        while presence:
            if presence & 1:
                yield position
            presence >>= 1
            position += 1

    def stated_cells(self) -> Iterator[tuple[int, object]]:
        """Each stated position beside its cell, ascending."""
        return zip(self.positions(), self.cells, strict=True)

    def with_cell(self, position: int, value: object) -> ManagedRow:
        """This row stating ``value`` at ``position``."""
        return self.with_cells((position,), (value,))

    def with_cells(self, positions: tuple[int, ...], values: tuple[object, ...]) -> ManagedRow:
        """This row stating each of ``values`` at its aligned position."""
        assigned = dict(zip(positions, values, strict=True))
        presence = self.presence
        for position in positions:
            presence |= 1 << position
        cells = tuple(assigned.get(position, cell) for position, cell in _aligned(self, presence))
        return managed_row(self.selection, cells, presence)

    def with_members_of(self, other: ManagedRow) -> ManagedRow:
        """This row with every member ``other`` states replaced by its cell."""
        if other.selection is not self.selection and other.selection != self.selection:
            raise ValueError("an overlaid Managed Row states members of the same selection")
        if not other.presence:
            return self
        overlay = dict(other.stated_cells())
        presence = self.presence | other.presence
        cells = tuple(overlay.get(position, cell) for position, cell in _aligned(self, presence))
        return managed_row(self.selection, cells, presence)

    def without(self, positions: int) -> ManagedRow:
        """This row stating none of the members in the ``positions`` mask."""
        dropped = self.presence & positions
        if not dropped:
            return self
        presence = self.presence & ~positions
        cells = tuple(cell for position, cell in self.stated_cells() if presence >> position & 1)
        return managed_row(self.selection, cells, presence)

    @property
    def attributes(self) -> Mapping[AttributeIdentity, object]:
        """The stated scalar members by identity, a view over this row."""
        return _IdentityView[AttributeIdentity](self, 0, self.selection.members.attribute_count)

    @property
    def value_objects(self) -> Mapping[ValueObjectIdentity, object]:
        """The stated Value Object members by identity, each viewed by
        declared name, a view over this row."""
        members = self.selection.members
        return _IdentityView[ValueObjectIdentity](
            self, members.attribute_count, len(members.shape.members)
        )


def managed_row(selection: RowSelection, cells: tuple[object, ...], presence: int) -> ManagedRow:
    """Adopt ``cells`` as a row of ``selection`` without copying or checking it."""
    row = object.__new__(ManagedRow)
    object.__setattr__(row, "selection", selection)
    object.__setattr__(row, "cells", cells)
    object.__setattr__(row, "presence", presence)
    return row


def empty_row(selection: RowSelection) -> ManagedRow:
    """The row of ``selection`` stating no member."""
    return managed_row(selection, (), 0)


def projected_row(selection: RowSelection, row: Mapping[str, object]) -> ManagedRow:
    """The already-judged name-keyed ``row`` as a Managed Row of ``selection``.

    Structural only: each stated value is kept as it is, and a nested
    occurrence document becomes its full-width positional form. ``row`` names
    only members of ``selection``.
    """
    members = selection.members.shape.members
    absent = selection.absent
    cells: list[object] = []
    presence = 0
    for position, member in enumerate(members):
        if member.name not in row:
            continue
        value = row[member.name]
        cells.append(
            value
            if isinstance(member, ScalarDefinition)
            else positional_occurrence(value, member, absent)
        )
        presence |= 1 << position
    if len(cells) != len(row):
        raise ValueError("a projected row names only members of its selection")
    return managed_row(selection, tuple(cells), presence)


def positional_occurrence(value: object, declared: OccurrenceDefinition, absent: object) -> object:
    """One already-managed occurrence document as its full-width positional
    form; a positional occurrence, a null, and ``absent`` are kept as they are."""
    if value is None or value is absent:
        return value
    if declared.multiplicity is Multiplicity.MANY:
        return tuple(
            _positional_document(element, declared, absent)
            for element in cast("tuple[object, ...]", value)
        )
    return _positional_document(value, declared, absent)


def _positional_document(value: object, declared: OccurrenceDefinition, absent: object) -> object:
    if isinstance(value, tuple):
        return cast("tuple[object, ...]", value)
    document = cast("Mapping[str, object]", value)
    return tuple(
        _positional_member(member, document.get(member.name, absent), absent)
        for member in declared.shape.members
    )


def _positional_member(member: MemberDefinition, value: object, absent: object) -> object:
    if isinstance(member, ScalarDefinition):
        return value
    return positional_occurrence(value, member, absent)


def _aligned(row: ManagedRow, presence: int) -> Iterator[tuple[int, object]]:
    """Each position ``presence`` states beside ``row``'s cell there, which is
    ``row.selection.absent`` where ``row`` states none."""
    position = 0
    remaining = presence
    while remaining:
        if remaining & 1:
            yield position, row.at(position)
        remaining >>= 1
        position += 1


class _IdentityView[K: MemberIdentity](Mapping[K, object]):
    __slots__ = ("_end", "_row", "_start")

    def __init__(self, row: ManagedRow, start: int, end: int) -> None:
        self._row = row
        self._start = start
        self._end = end

    def _position(self, key: object) -> int | None:
        position = self._row.selection.members.index.get(cast("K", key))
        if position is None or not self._start <= position < self._end:
            return None
        return position if self._row.stated(position) else None

    def __getitem__(self, key: object) -> object:
        position = self._position(key)
        if position is None:
            raise KeyError(key)
        return self._value(position)

    def __contains__(self, key: object) -> bool:
        return self._position(key) is not None

    def __iter__(self) -> Iterator[K]:
        identities = self._row.selection.members.identities
        return (cast("K", identities[position]) for position in self._stated())

    def __len__(self) -> int:
        return sum(1 for _ in self._stated())

    def _stated(self) -> Iterator[int]:
        return (
            position for position in self._row.positions() if self._start <= position < self._end
        )

    def _value(self, position: int) -> object:
        row = self._row
        cell = row.at(position)
        if position < row.selection.members.attribute_count:
            return cell
        declared = cast("OccurrenceDefinition", row.selection.members.shape.members[position])
        return occurrence_value(cell, declared, row.selection.absent)
