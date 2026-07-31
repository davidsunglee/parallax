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

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Final

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
    """

    shape: PredecessorShape
    attribute_columns: tuple[ColumnSlice[object], ...]
    value_object_columns: tuple[ColumnSlice[object], ...] = ()
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
        lengths = {len(column) for column in (*self.attribute_columns, *self.value_object_columns)}
        if len(lengths) > 1:
            raise ValueError("Predecessor Columns' member columns share one positive row count")
        length = next(iter(lengths), 0)
        if length == 0:
            raise ValueError("Predecessor Columns carries at least one row")
        object.__setattr__(self, "length", length)

    def row(self, index: int) -> dict[str, object]:
        """The complete member map one resolved row's Predecessor Row wraps."""
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
        return members
