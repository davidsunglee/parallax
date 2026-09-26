from __future__ import annotations

from collections.abc import ItemsView, Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

from parallax.core.base import retain_document_value
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    DocumentMember,
    Leaf,
    MemberShape,
    Multiplicity,
    Occurrence,
    ValueObjectIdentity,
)

if TYPE_CHECKING:
    from parallax.core.inheritance import EntityMemberSelection

__all__ = [
    "EntityStateRow",
    "PredecessorRow",
    "TemporalObservation",
    "VersionObservation",
    "WriteObservation",
    "occurrence_value",
]


class _Selection(Protocol):
    @property
    def shape(self) -> MemberShape: ...


class EntityStateRow(Mapping[str, object]):
    """A read-only view of one already-decoded Entity State.

    The view retains either its source mapping or one positional member row by
    reference, so observation shares one state without rebuilding or detaching
    every member into another row-sized dictionary. A positional row is keyed by
    declared member name (:meth:`over_declared_members`): every canonical
    position is a key, an absent slot answers the absent marker rather than
    raising, and nested Value Objects are exposed through mapping views over the
    same positional state.
    """

    __slots__ = ("_absent", "_members", "_shape", "_values")

    _members: Mapping[str, object] | None
    _shape: MemberShape | None

    def __init__(self, members: Mapping[str, object]) -> None:
        self._members = members
        self._values: tuple[object, ...] = ()
        self._shape = None
        self._absent: object | None = None

    @classmethod
    def over_declared_members(
        cls, selection: _Selection, values: tuple[object, ...], *, absent: object
    ) -> EntityStateRow:
        """View one positional member row through its declared member names.

        The view is full-width: it holds one key per member of ``selection``'s
        canonical shape, and a position holding ``absent`` is a present key
        whose value is that marker.
        """
        shape = selection.shape
        if len(shape.members) != len(values):
            raise ValueError("an Entity State row selection must align with its member state")
        row = object.__new__(cls)
        row._members = None
        row._shape = shape
        row._values = values
        row._absent = absent
        return row

    def __getitem__(self, key: str) -> object:
        members = self._members
        if members is not None:
            return members[key]
        shape = cast("MemberShape", self._shape)
        position = shape.position(key)
        if position is None:
            raise KeyError(key)
        return _member_value(shape.members[position], self._values[position], self._absent)

    def __contains__(self, key: object) -> bool:
        shape = self._shape
        if shape is None:
            return super().__contains__(key)
        return shape.position(cast("str", key)) is not None

    def __iter__(self) -> Iterator[str]:
        members = self._members
        if members is not None:
            return iter(members)
        return (member.name for member in cast("MemberShape", self._shape).members)

    def __len__(self) -> int:
        members = self._members
        if members is not None:
            return len(members)
        return len(self._values)

    def items(self) -> ItemsView[str, object]:
        shape = self._shape
        if shape is None:
            return super().items()
        return _DeclaredItems(self, shape.members, self._values, self._absent)


class _EntityDocumentRow(Mapping[str, object]):
    """A mapping view over one positional Value Object member row.

    Keys are the shape's declared names; a position holding the absent marker
    is no key at all, so lookup raises and iteration omits it.
    """

    __slots__ = ("_absent", "_shape", "_values")

    def __init__(
        self, values: tuple[object, ...], shape: MemberShape, absent: object | None
    ) -> None:
        self._values = values
        self._shape = shape
        self._absent = absent

    def __getitem__(self, key: str) -> object:
        shape = self._shape
        position = shape.position(key)
        if position is None:
            raise KeyError(key)
        value = self._values[position]
        absent = self._absent
        if value is absent:
            raise KeyError(key)
        return _member_value(shape.members[position], value, absent)

    def __iter__(self) -> Iterator[str]:
        absent = self._absent
        return (
            member.name
            for member, value in zip(self._shape.members, self._values, strict=True)
            if value is not absent
        )

    def __len__(self) -> int:
        absent = self._absent
        return sum(1 for value in self._values if value is not absent)

    def items(self) -> ItemsView[str, object]:
        return _DocumentItems(self, self._shape.members, self._values, self._absent)

    def views(self, cell: object) -> bool:
        """Whether this view reads exactly ``cell``, the positional row given."""
        return self._values is cell


class _AlignedItems(ItemsView[str, object]):
    __slots__ = ("_absent", "_aligned", "_members")

    def __init__(
        self,
        mapping: Mapping[str, object],
        members: tuple[DocumentMember, ...],
        values: tuple[object, ...],
        absent: object | None,
    ) -> None:
        super().__init__(mapping)
        self._members = members
        self._aligned = values
        self._absent = absent


class _DeclaredItems(_AlignedItems):
    __slots__ = ()

    def __iter__(self) -> Iterator[tuple[str, object]]:
        absent = self._absent
        for member, value in zip(self._members, self._aligned, strict=True):
            yield member.name, _member_value(member, value, absent)


class _DocumentItems(_AlignedItems):
    __slots__ = ()

    def __iter__(self) -> Iterator[tuple[str, object]]:
        absent = self._absent
        for member, value in zip(self._members, self._aligned, strict=True):
            if value is not absent:
                yield member.name, _member_value(member, value, absent)


def _member_value(member: DocumentMember, value: object, absent: object | None) -> object:
    if isinstance(member, Leaf):
        return value
    return occurrence_value(value, member, absent)


def occurrence_value(value: object, declared: Occurrence, absent: object | None) -> object:
    """View one positional Value Object cell by declared name without copying it.

    A One cell answers one mapping view and a Many cell a tuple of them; ``None``
    and ``absent`` pass through unchanged.
    """
    if value is None or value is absent:
        return value
    shape = declared.shape
    if declared.multiplicity is Multiplicity.MANY:
        if not isinstance(value, tuple):  # pragma: no cover - accepted Page state is positional
            raise TypeError("a Many Value Object Entity State is positional")
        rows = cast("tuple[object, ...]", value)
        if any(  # pragma: no cover - accepted Page state is positional
            not isinstance(item, tuple) for item in rows
        ):
            raise TypeError("a Many Value Object Entity State is positional")
        return tuple(
            _EntityDocumentRow(cast("tuple[object, ...]", item), shape, absent) for item in rows
        )
    if not isinstance(value, tuple):  # pragma: no cover - accepted Page state is positional
        raise TypeError("a Value Object Entity State is positional")
    return _EntityDocumentRow(cast("tuple[object, ...]", value), shape, absent)


@dataclass(frozen=True, slots=True)
class VersionObservation:
    """The optimistic-lock version a versioned Non-Temporal row was read at."""

    observed_version: int


@dataclass(frozen=True, slots=True)
class PredecessorRow:
    """The complete, immutable persisted state a Temporal Observation retains.

    ``members`` holds every applicable member of the observed row by its declared
    name — every scalar Attribute, every complete Value Object occurrence, the
    complete primary key, every temporal bound, and every audit value — and no
    generated-value expression. Completeness is required because temporal
    expansion carries members the authored mutation never mentioned, and because
    a later decorator must tell carried state from changed state without a second
    read.

    ``document`` is the raw Structured Column document the observing read
    returned, retained beside the member state and never as an entry in it, so a
    successor is built by patching what the row actually held rather than by
    re-encoding the members this model happens to declare. It is **absent** — not
    empty — under `Columns` layout, where the row has no Structured Column, and
    absent likewise for an observation whose source read no row; the member map
    stays purely logical either way, so a consumer iterating members can never
    surface the document as a result field or an Entity member.

    Direct construction owns what its caller supplies: a mapping of members and
    the document are both retained in frozen form. :meth:`over_row` instead
    adopts a trusted reader's positional member row and decoded document by
    reference. That document may be mutable host containers; it stays logically
    immutable because the reader transferred exclusive ownership, nothing reads
    it except to copy it (``apply_patches``), and no caller can reach it.
    """

    members: EntityStateRow | Mapping[str, object]
    document: object | None = None
    _selection: EntityMemberSelection | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _row: tuple[object, ...] = field(default=(), init=False, repr=False, compare=False)
    _absent: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        members = self.members
        if not isinstance(members, EntityStateRow):
            owned = retain_document_value(members)
            if not isinstance(owned, Mapping):  # pragma: no cover - mappings stay mappings
                raise TypeError("predecessor members must be a mapping")
            object.__setattr__(self, "members", EntityStateRow(cast("Mapping[str, object]", owned)))
        object.__setattr__(self, "document", retain_document_value(self.document))
        if not self.members:
            raise ValueError("a Predecessor Row carries the observed row's complete state")

    @classmethod
    def over_row(
        cls,
        selection: EntityMemberSelection,
        row: tuple[object, ...],
        document: object | None,
        absent: object,
    ) -> PredecessorRow:
        """Adopt one judged positional member row, aligned to ``selection``, and
        its transferred raw document without copying either."""
        predecessor = object.__new__(cls)
        object.__setattr__(
            predecessor,
            "members",
            EntityStateRow.over_declared_members(selection, row, absent=absent),
        )
        object.__setattr__(predecessor, "document", document)
        object.__setattr__(predecessor, "_selection", selection)
        object.__setattr__(predecessor, "_row", row)
        object.__setattr__(predecessor, "_absent", absent)
        return predecessor

    def member(self, name: str) -> object:
        """The observed value of one member, by its declared name."""
        return self.members[name]

    def cell(self, member: AttributeIdentity | ValueObjectIdentity) -> object:
        """The observed value of one member, by its identity."""
        selection = self._selection
        if selection is None:
            return self.members[_member_name(member)]
        position = selection.index[member]
        return _member_value(selection.shape.members[position], self._row[position], self._absent)

    def axis_start(self, at: None, attribute: AttributeIdentity, /) -> object:
        """The observed value of one As-Of Axis start, or ``None`` when the row
        carries no such member; ``at`` is ``None`` because a Predecessor Row
        holds one milestone."""
        del at
        selection = self._selection
        if selection is None:
            return self.members.get(attribute.name)
        position = selection.index.get(attribute)
        return None if position is None else self._row[position]

    def identity_maps(
        self, selection: EntityMemberSelection
    ) -> tuple[dict[AttributeIdentity, object], dict[ValueObjectIdentity, object]]:
        """One fresh pair of this row's members keyed by ``selection``'s
        identities, each value the row's own cell or a view over it."""
        attributes: dict[AttributeIdentity, object] = {}
        value_objects: dict[ValueObjectIdentity, object] = {}
        if self._selection is selection:
            row = self._row
            for attribute, value in zip(selection.attributes, row, strict=False):
                attributes[attribute.identity] = value
            members = selection.shape.members
            absent = self._absent
            for position, occurrence in enumerate(
                selection.value_objects, selection.attribute_count
            ):
                value_objects[occurrence.identity] = occurrence_value(
                    row[position], cast("Occurrence", members[position]), absent
                )
            return attributes, value_objects
        for name, value in self.members.items():
            binding = selection.binding(name)
            if binding is None:
                raise ValueError(f"predecessor member {name!r} is not a member of the selection")
            if isinstance(binding, AttributeMetadata):
                attributes[binding.identity] = value
            else:
                value_objects[binding.identity] = value
        return attributes, value_objects

    def carries(self, member: AttributeIdentity | ValueObjectIdentity, value: object) -> bool:
        """Whether ``value`` is this row's own cell for ``member``, or the view
        :meth:`identity_maps` builds over it — identity, never equality."""
        selection = self._selection
        if selection is None:
            name = _member_name(member)
            members = self.members
            return name in members and members[name] is value
        position = selection.index[member]
        cell = self._row[position]
        if value is cell:
            return True
        declared = selection.shape.members[position]
        if isinstance(declared, Leaf) or cell is None or cell is self._absent:
            return False
        if declared.multiplicity is not Multiplicity.MANY:
            return isinstance(value, _EntityDocumentRow) and value.views(cell)
        items = cast("tuple[object, ...]", cell)
        return (
            isinstance(value, tuple)
            and len(cast("tuple[object, ...]", value)) == len(items)
            and all(
                isinstance(view, _EntityDocumentRow) and view.views(item)
                for view, item in zip(cast("tuple[object, ...]", value), items, strict=True)
            )
        )


def _member_name(member: AttributeIdentity | ValueObjectIdentity) -> str:
    return member.name if isinstance(member, AttributeIdentity) else member.path[-1]


@dataclass(frozen=True, slots=True)
class TemporalObservation:
    """The predecessor milestone a temporal close addresses, gates on, and
    carries state forward from.

    Transaction-Time-Only and Bitemporal entities have identical observation
    requirements; the accepted Temporal Facet, not a variant per temporal flavor,
    decides which topology applies.
    """

    predecessor: PredecessorRow


type WriteObservation = VersionObservation | TemporalObservation
"""The closed algebra of database evidence a write against existing state
retains."""
