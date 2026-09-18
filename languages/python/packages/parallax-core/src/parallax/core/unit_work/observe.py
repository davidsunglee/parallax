"""The closed Write Observation algebra (m-unit-work).

A Write Observation is the database evidence a surviving write against existing
state retains. Absence is **structural**: an insert and an unversioned
Non-Temporal write carry no observation value at all, rather than a null one, so
there is no ``NoObservation``, no nullable observation flowing downstream, and no
representable "a version *and* a predecessor" or "neither" state. A required
observation that is missing is a planning error, raised while the step is being
settled, in **both** concurrency modes.
"""

from __future__ import annotations

from collections.abc import ItemsView, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from parallax.core.base import adopt_frozen_map, retain_document_value
from parallax.core.metamodel import (
    AttributeMetadata,
    DocumentMember,
    Leaf,
    MemberShape,
    Multiplicity,
    Occurrence,
    ValueObjectMetadata,
)

__all__ = [
    "EntityStateRow",
    "PredecessorRow",
    "TemporalObservation",
    "VersionObservation",
    "WriteObservation",
]


class _Layout(Protocol):
    @property
    def attributes(self) -> Sequence[AttributeMetadata]: ...

    @property
    def occurrences(self) -> Sequence[ValueObjectMetadata]: ...


class _Selection(Protocol):
    @property
    def shape(self) -> MemberShape: ...


class EntityStateRow(Mapping[str, object]):
    """A read-only view of one already-decoded Entity State.

    The view retains either its source mapping or one positional member row by
    reference. It exists so observation and publication can share one state
    without rebuilding or detaching every member into another row-sized
    dictionary. Nested Value Objects are exposed through mapping views over the
    same positional state.

    A positional row is keyed one of two ways, fixed at construction: by each
    member's physical storage name (:meth:`over_members`), where iteration omits
    absent slots, or by its declared name (:meth:`over_declared_members`), where
    every canonical position is a key and an absent slot answers the absent
    marker rather than raising.
    """

    __slots__ = ("_absent", "_layout", "_members", "_shape", "_values")

    _layout: _Layout | None
    _members: Mapping[str, object] | None
    _shape: MemberShape | None

    def __init__(self, members: Mapping[str, object]) -> None:
        self._members = members
        self._values: tuple[object, ...] = ()
        self._layout = None
        self._shape = None
        self._absent: object | None = None

    @classmethod
    def over_members(
        cls, layout: _Layout, values: tuple[object, ...], *, absent: object
    ) -> EntityStateRow:
        """View one positional member row through its physical storage keys."""
        attributes = layout.attributes
        occurrences = layout.occurrences
        if len(attributes) + len(occurrences) != len(values):
            raise ValueError("an Entity State row layout must align with its member state")
        row = object.__new__(cls)
        row._members = None
        row._layout = layout
        row._shape = None
        row._values = values
        row._absent = absent
        return row

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
        row._layout = None
        row._shape = shape
        row._values = values
        row._absent = absent
        return row

    @classmethod
    def remap(
        cls,
        members: Mapping[str, tuple[str, bool]],
        state: Mapping[str, object],
    ) -> EntityStateRow:
        """View physical state keys through their logical member names."""
        return cls(_RemappedMembers(members, state))

    def __getitem__(self, key: str) -> object:
        members = self._members
        if members is not None:
            return members[key]
        shape = self._shape
        if shape is not None:
            position = shape.position(key)
            if position is None:
                raise KeyError(key)
            return _member_value(shape.members[position], self._values[position], self._absent)
        layout = cast("_Layout", self._layout)
        attributes = layout.attributes
        position = next(
            (
                index
                for index, member in enumerate((*attributes, *layout.occurrences))
                if member.storage.name == key
            ),
            None,
        )
        if position is None:
            raise KeyError(key)
        value = self._values[position]
        if position < len(attributes):
            return value
        declared = layout.occurrences[position - len(attributes)]
        return _occurrence_value(value, declared.definition, self._absent)

    def __contains__(self, key: object) -> bool:
        shape = self._shape
        if shape is None:
            return super().__contains__(key)
        return shape.position(cast("str", key)) is not None

    def __iter__(self) -> Iterator[str]:
        members = self._members
        if members is not None:
            return iter(members)
        shape = self._shape
        if shape is not None:
            return (member.name for member in shape.members)
        layout = cast("_Layout", self._layout)
        return (
            member.storage.name
            for member, value in zip(
                (*layout.attributes, *layout.occurrences), self._values, strict=True
            )
            if value is not self._absent
        )

    def __len__(self) -> int:
        members = self._members
        if members is not None:
            return len(members)
        if self._shape is not None:
            return len(self._values)
        return sum(1 for _key in self)

    def items(self) -> ItemsView[str, object]:
        shape = self._shape
        if shape is None:
            return super().items()
        return _DeclaredItems(self, shape.members, self._values, self._absent)


class _RemappedMembers(Mapping[str, object]):
    __slots__ = ("_members", "_state")

    def __init__(
        self,
        members: Mapping[str, tuple[str, bool]],
        state: Mapping[str, object],
    ) -> None:
        self._members = members
        self._state = state

    def __getitem__(self, key: str) -> object:
        column, _is_value_object = self._members[key]
        return self._state[column]

    def __iter__(self) -> Iterator[str]:
        return (
            name
            for name, (column, _is_value_object) in self._members.items()
            if column in self._state
        )

    def __len__(self) -> int:
        return sum(1 for _name in self)


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
    return _occurrence_value(value, member, absent)


def _occurrence_value(value: object, declared: Occurrence, absent: object | None) -> object:
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
    re-encoding the members this model happens to declare. The value is the read's
    own, unchanged, retained by reference to the immutable provider-normalized
    carrier. It is **absent** — not empty — under `Columns`
    layout, where the row has no Structured Column, and absent likewise for an
    observation whose source read no row; the member map stays purely logical
    either way, so a consumer iterating members can never surface the document as
    a result field or an Entity member.
    """

    members: EntityStateRow | Mapping[str, object]
    document: object | None = None

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

    def member(self, name: str) -> object:
        """The observed value of one member, by its declared name."""
        return self.members[name]


def adopt_predecessor_row(
    members: dict[str, object], *, document: object | None = None
) -> PredecessorRow:
    """Adopt trusted final predecessor storage without another traversal."""
    row = object.__new__(PredecessorRow)
    object.__setattr__(row, "members", EntityStateRow(adopt_frozen_map(members)))
    object.__setattr__(row, "document", retain_document_value(document))
    if not row.members:
        raise ValueError("a Predecessor Row carries the observed row's complete state")
    return row


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
