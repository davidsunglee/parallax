"""Compact private column storage for write planning (m-unit-work).

A materializing predicate write's resolving read produces a number of rows
that scales with the addressed data, not with anything the planner controls.
Rather than wrapping each resolved row in an independently allocated object,
this module gives the write path a bounded, immutable columnar backing —
:class:`ChunkedColumn`, its :class:`ChunkedColumnBuilder`, and the windowed
:class:`ColumnSlice` view over one sealed column — following
:mod:`parallax.core.storage_layout._facet`'s interned-shape-plus-materialize-
on-demand precedent. :class:`PredecessorColumns` stores complete predecessor
state this way; :class:`~parallax.core.unit_work.observe.PredecessorRow`
remains the logical complete-state contract, and a view over one row is built
only when a consumer asks for it.

Every value here is immutable once sealed. A :class:`ChunkedColumnBuilder`
appends one value at a time and seals each fixed-size chunk as it fills,
so building a column never holds one full-size list alongside the growing
column itself, and no full-size list-to-tuple copy happens at the end.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, cast

from parallax.core.unit_work.observe import PredecessorRow

__all__ = [
    "ChunkedColumn",
    "ChunkedColumnBuilder",
    "ColumnSlice",
    "PredecessorColumns",
    "PredecessorShape",
    "whole",
]

# The bound one sealed chunk holds. Private and internal: no consumer observes
# chunk boundaries, only the logical column they compose.
_CHUNK_SIZE: Final[int] = 1024
_EMPTY_PROXY: Mapping[object, object] = MappingProxyType({})
_IMMUTABLE_MAPPING: type[object] = type(_EMPTY_PROXY)


@dataclass(frozen=True, slots=True)
class ChunkedColumn[T]:
    """An immutable column of ``T`` backed by bounded, already-sealed chunks.

    Every chunk but the last holds exactly :data:`_CHUNK_SIZE` values; the last
    may be smaller. A column is never transposed or copied into a second
    full-size collection — indexing computes its chunk and offset directly.
    """

    chunks: tuple[tuple[T, ...], ...]
    length: int

    def __post_init__(self) -> None:
        if sum(len(chunk) for chunk in self.chunks) != self.length:
            raise ValueError("a Chunked Column's declared length must match its chunks' own sizes")

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, index: int) -> T:
        position = index if index >= 0 else index + self.length
        if not 0 <= position < self.length:
            raise IndexError(index)
        chunk_index, offset = divmod(position, _CHUNK_SIZE)
        return self.chunks[chunk_index][offset]

    def __iter__(self) -> Iterator[T]:
        for chunk in self.chunks:
            yield from chunk


class ChunkedColumnBuilder[T]:
    """A bounded builder that seals each :data:`_CHUNK_SIZE` run once it fills.

    ``append`` never re-copies a prior chunk; only the current, still-open
    chunk grows, and it is sealed into an immutable tuple the moment it
    reaches the bound.
    """

    __slots__ = ("_chunks", "_current", "_length")

    def __init__(self) -> None:
        self._chunks: list[tuple[T, ...]] = []
        self._current: list[T] = []
        self._length = 0

    def append(self, value: T) -> None:
        self._current.append(value)
        self._length += 1
        if len(self._current) == _CHUNK_SIZE:
            self._chunks.append(tuple(self._current))
            self._current = []

    def build(self) -> ChunkedColumn[T]:
        """Seal the builder into its immutable column. Idempotent to call once."""
        chunks = (*self._chunks, tuple(self._current)) if self._current else tuple(self._chunks)
        return ChunkedColumn(chunks=chunks, length=self._length)


@dataclass(frozen=True, slots=True)
class ColumnSlice[T]:
    """A stable, immutable view over one half-open range of a Chunked Column.

    Slices let later stages share one column's backing chunks rather than
    copying a sub-range into a second collection; two slices over the same
    column and range compare equal by structure, never by identity.
    """

    column: ChunkedColumn[T]
    start: int
    stop: int

    def __post_init__(self) -> None:
        if not 0 <= self.start <= self.stop <= self.column.length:
            raise ValueError(
                "a Column Slice's range must be a valid half-open range of its column: "
                f"got [{self.start}, {self.stop}) over a column of length {self.column.length}"
            )

    def __len__(self) -> int:
        return self.stop - self.start

    def __getitem__(self, index: int) -> T:
        position = index if index >= 0 else index + len(self)
        if not 0 <= position < len(self):
            raise IndexError(index)
        return self.column[self.start + position]

    def __iter__(self) -> Iterator[T]:
        for position in range(self.start, self.stop):
            yield self.column[position]


def whole[T](column: ChunkedColumn[T]) -> ColumnSlice[T]:
    """The Column Slice spanning ``column`` end to end."""
    return ColumnSlice(column=column, start=0, stop=column.length)


def freeze_retained_value(value: object) -> object:
    """Own mutable containers once and retain already-frozen trees by identity."""
    if isinstance(value, _IMMUTABLE_MAPPING):
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        frozen = {key: freeze_retained_value(nested) for key, nested in mapping.items()}
        return cast("Mapping[object, object]", MappingProxyType(frozen))
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        frozen = tuple(freeze_retained_value(nested) for nested in items)
        return items if all(a is b for a, b in zip(frozen, items, strict=True)) else frozen
    if isinstance(value, list):
        return tuple(freeze_retained_value(nested) for nested in cast("list[object]", value))
    return value


def _freeze_column(column: ColumnSlice[object]) -> ColumnSlice[object]:
    builder: ChunkedColumnBuilder[object] | None = None
    for index, value in enumerate(column):
        frozen = freeze_retained_value(value)
        if builder is None:
            if frozen is value:
                continue
            builder = ChunkedColumnBuilder()
            for prior in range(index):
                builder.append(column[prior])
        builder.append(frozen)
    return column if builder is None else whole(builder.build())


@dataclass(frozen=True, slots=True)
class PredecessorShape:
    """The member-name shape one resolving read's Predecessor Rows share.

    One Materialized Write Group's rows come from one resolving read against
    one Entity, so every row shares the same declared member set; the shape is
    retained once rather than once per row.
    """

    attributes: tuple[str, ...]
    value_objects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PredecessorColumns:
    """Complete predecessor state stored columnarly, one column per member.

    :class:`~parallax.core.unit_work.observe.PredecessorRow` stays the logical
    complete-state contract; :meth:`row` builds one only when a consumer asks.

    ``documents`` is the aligned raw Structured Column of each resolved row,
    carried beside the decoded member columns rather than among them, so a
    logical Predecessor Row view over columnar storage exposes the raw document
    without a second per-row carrier. It is absent — not a column of nulls —
    where the resolving read projected no Structured Column.
    """

    shape: PredecessorShape
    attribute_columns: tuple[ColumnSlice[object], ...]
    value_object_columns: tuple[ColumnSlice[object], ...] = ()
    documents: ColumnSlice[object] | None = None
    length: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.attribute_columns) != len(self.shape.attributes):
            raise ValueError(
                "Predecessor Columns carries one column per attribute the shape names: "
                f"expected {len(self.shape.attributes)}, got {len(self.attribute_columns)}"
            )
        if len(self.value_object_columns) != len(self.shape.value_objects):
            raise ValueError(
                "Predecessor Columns carries one column per value object the shape names: "
                f"expected {len(self.shape.value_objects)}, got {len(self.value_object_columns)}"
            )
        aligned = (
            *self.attribute_columns,
            *self.value_object_columns,
            *(() if self.documents is None else (self.documents,)),
        )
        lengths = {len(column) for column in aligned}
        if len(lengths) > 1:
            raise ValueError("Predecessor Columns' member columns share one positive row count")
        length = next(iter(lengths), 0)
        if length == 0:
            raise ValueError("Predecessor Columns carries at least one row")
        object.__setattr__(
            self,
            "value_object_columns",
            tuple(_freeze_column(column) for column in self.value_object_columns),
        )
        if self.documents is not None:
            object.__setattr__(self, "documents", _freeze_column(self.documents))
        object.__setattr__(self, "length", length)

    def row(self, index: int) -> PredecessorRow:
        """The complete Predecessor Row one resolved row's columns compose.

        Building it here rather than handing back a member map is what keeps the
        retained document aligned with the members it was decoded from: the two
        leave this class together or not at all.
        """
        members: dict[str, object] = {
            name: column[index]
            for name, column in zip(self.shape.attributes, self.attribute_columns, strict=True)
        }
        members.update(
            (name, column[index])
            for name, column in zip(
                self.shape.value_objects, self.value_object_columns, strict=True
            )
        )
        return PredecessorRow(
            members, document=None if self.documents is None else self.documents[index]
        )
