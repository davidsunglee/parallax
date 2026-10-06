from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from parallax.core.base import retain_document_value

__all__ = [
    "ChunkedColumnBuilder",
    "ColumnSlice",
    "freeze_retained_value",
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

    def __len__(self) -> int:
        return self._length

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
    return retain_document_value(value)
