"""Compact private column storage beneath write-plan evidence (m-write-plan).

Bounded chunk construction, Column Slice sharing, and the recursive ownership a
retained value takes once.
"""

from __future__ import annotations

from typing import cast

import pytest

from parallax.core.base import FrozenMap
from parallax.core.write_plan import ChunkedColumnBuilder, whole
from parallax.core.write_plan.columns import (
    _CHUNK_SIZE,  # pyright: ignore[reportPrivateUsage] - bounded-chunking regression only
    ChunkedColumn,
    ColumnSlice,
    freeze_retained_value,
)


# --------------------------------------------------------------------------- #
# Chunked Column / Column Slice: bounded construction and structural sharing. #
# --------------------------------------------------------------------------- #
def test_retained_tuple_freezes_nested_mutable_values_without_copying_immutable_peers() -> None:
    immutable = ("stable",)

    frozen = freeze_retained_value((immutable, [1, {"nested": [2]}]))

    assert frozen == (immutable, (1, FrozenMap({"nested": (2,)})))
    assert cast("tuple[object, ...]", frozen)[0] is immutable


def test_a_chunked_column_seals_bounded_chunks_as_it_builds() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    count = _CHUNK_SIZE * 2 + 7
    for value in range(count):
        builder.append(value)
    column = builder.build()
    assert len(column) == count
    assert [len(chunk) for chunk in column.chunks] == [_CHUNK_SIZE, _CHUNK_SIZE, 7]
    assert column[0] == 0
    assert column[_CHUNK_SIZE] == _CHUNK_SIZE
    assert column[-1] == count - 1
    assert list(column) == list(range(count))


def test_a_chunked_column_refuses_a_declared_length_disagreeing_with_its_chunks() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    builder.append(1)
    column = builder.build()
    with pytest.raises(ValueError, match="declared length"):
        ChunkedColumn(chunks=column.chunks, length=2)


def test_a_chunked_column_refuses_an_out_of_range_index() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    builder.append(1)
    column = builder.build()
    with pytest.raises(IndexError):
        column[1]
    with pytest.raises(IndexError):
        column[-2]


def test_a_column_slice_shares_its_backing_column_without_copying() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    for value in range(10):
        builder.append(value)
    column = builder.build()
    left = ColumnSlice(column, 0, 5)
    right = ColumnSlice(column, 5, 10)
    assert list(left) == [0, 1, 2, 3, 4]
    assert list(right) == [5, 6, 7, 8, 9]
    assert left.column is right.column  # ONE backing column, two independent views
    # Two independently constructed slices over equal ranges of an equal
    # (not merely identical) column compare equal by structure.
    other = ColumnSlice(whole(builder.build()).column, 0, 5)
    assert left == other
    assert left is not other


def test_a_column_slice_refuses_an_invalid_range() -> None:
    column = whole(ChunkedColumnBuilder[int]().build())
    with pytest.raises(ValueError, match="Column Slice"):
        ColumnSlice(column.column, 1, 0)


def test_a_column_slice_refuses_an_out_of_range_index() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    builder.append(1)
    builder.append(2)
    sliced = ColumnSlice(builder.build(), 0, 1)
    with pytest.raises(IndexError):
        sliced[1]
    with pytest.raises(IndexError):
        sliced[-2]
