"""Predecessor Rows: a resolving read's aligned evidence, adopted by reference
(m-write-plan *Predecessor Row*).

Each judged positional row and raw document is retained as read, sealed in
bounded chunks with documents aligned, and read positionally — axis cells by
selection position, coverage row by row and only as far as a caller asks.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Iterator, Sequence
from typing import cast

import pytest

from parallax.core import Entity, temporal_read
from parallax.core.base import INFINITY
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.metamodel import AttributeIdentity, AttributeMetadata
from parallax.core.write_plan import (
    ChunkedColumnBuilder,
    PredecessorRow,
    PredecessorRows,
    PredecessorRowsBuilder,
    whole,
)
from parallax.core.write_plan.columns import (
    _CHUNK_SIZE,  # pyright: ignore[reportPrivateUsage] - bounded-chunking regression only
)
from tests.unit._document_layout_support import PERSON, document_model
from tests.unit.core import _milestone_rows_support as milestone_rows

_PERSON = LayoutCatalog(document_model()).entity(PERSON)


def _person_row(key: int) -> tuple[object, ...]:
    return (key, "Ada", ABSENT, None, ("Bergen", ("NO",)), (("founder",), (None,)))


def _person_rows(
    rows: Sequence[tuple[object, ...]], documents: Sequence[object] | None = None
) -> PredecessorRows:
    builder = PredecessorRowsBuilder(
        _PERSON.member_selection,
        key_position=_PERSON.primary_key[0],
        absent=ABSENT,
        documents=documents is not None,
    )
    for index, row in enumerate(rows):
        builder.append(row, None if documents is None else documents[index])
    sealed = builder.seal()
    assert sealed is not None
    return sealed


def test_predecessor_rows_retain_each_judged_row_and_raw_document_by_reference() -> None:
    first, second = _person_row(1), _person_row(2)
    stored: list[object] = [{"displayName": "Ada", "unknown": {"kept": True}}, {}]

    evidence = _person_rows([first, second], stored)
    predecessor = PredecessorRow.over_row(
        evidence.selection, evidence.rows[0], evidence.document(0), evidence.absent
    )

    assert len(evidence) == 2
    assert evidence.rows[0] is first
    assert evidence.rows[1] is second
    assert [evidence.key(0), evidence.key(1)] == [1, 2]
    assert evidence.document(0) is stored[0]
    assert predecessor.document is stored[0]
    assert predecessor.member("address") == {"city": "Bergen", "geo": {"country": "NO"}}
    assert predecessor.member("score") is ABSENT


def test_predecessor_rows_without_a_structured_column_answer_no_document() -> None:
    evidence = _person_rows([_person_row(1)])

    assert evidence.documents is None
    assert evidence.document(0) is None


def test_predecessor_rows_seal_bounded_chunks_and_keep_documents_aligned() -> None:
    count = _CHUNK_SIZE * 2 + 3
    rows = [_person_row(key) for key in range(count)]
    documents: list[object] = [{"row": key} for key in range(count)]

    evidence = _person_rows(rows, documents)

    assert [len(chunk) for chunk in evidence.rows.column.chunks] == [
        _CHUNK_SIZE,
        _CHUNK_SIZE,
        3,
    ]
    for index in (0, _CHUNK_SIZE - 1, _CHUNK_SIZE, count - 1):
        assert evidence.rows[index] is rows[index]
        assert evidence.key(index) == index
        assert evidence.document(index) is documents[index]


def test_predecessor_rows_read_an_axis_start_by_its_selection_position() -> None:
    evidence = _person_rows([_person_row(5)])
    key = cast("AttributeMetadata", _PERSON.member_selection.bindings[0]).identity

    assert evidence.axis_start(0, key) == 5
    assert evidence.axis_start(0, dataclasses.replace(key, name="txStart")) is None


_LAYOUTS = pytest.mark.parametrize(
    "entity", milestone_rows.LAYOUT_ENTITIES, ids=milestone_rows.LAYOUT_IDS
)
_JAN, _MAR, _APR, _JUN = (dt.datetime(2026, month, 1, tzinfo=dt.UTC) for month in (1, 3, 4, 6))


@_LAYOUTS
def test_predecessor_rows_cover_each_row_with_its_own_valid_time_cells(
    entity: type[Entity],
) -> None:
    evidence, shape = milestone_rows.milestones(entity, (_JAN, _MAR), (_MAR, INFINITY))

    first = temporal_read.valid_time_coverage(shape, evidence, 0)
    second = temporal_read.valid_time_coverage(shape, evidence, 1)

    assert evidence.axis_end(1, shape.valid_time.end_attribute) is INFINITY
    assert (
        evidence.axis_end(0, dataclasses.replace(shape.valid_time.end_attribute, name="none"))
        is None
    )
    assert first is not None
    assert second is not None
    assert (first.start, first.end, second.start, second.end) == (_JAN, _MAR, _MAR, INFINITY)
    assert first.start is _JAN
    assert first.end is _MAR
    assert second.end is INFINITY


class _RecordedRows:
    """A carrier's milestones, answered by delegation, recording each row read."""

    def __init__(self, rows: PredecessorRows) -> None:
        self._rows = rows
        self.read: list[int] = []

    def axis_start(self, at: int, attribute: AttributeIdentity, /) -> object:
        self.read.append(at)
        return self._rows.axis_start(at, attribute)

    def axis_end(self, at: int, attribute: AttributeIdentity, /) -> object:
        self.read.append(at)
        return self._rows.axis_end(at, attribute)


@_LAYOUTS
def test_group_coverage_is_read_lazily_and_only_until_a_gap_is_found(
    entity: type[Entity],
) -> None:
    evidence, shape = milestone_rows.milestones(
        entity, (_JAN, _MAR), (_APR, _JUN), (_JUN, INFINITY)
    )
    recorded = _RecordedRows(evidence)
    window = temporal_read.TimeInterval(_JAN, INFINITY)

    def coverage() -> Iterator[temporal_read.TimeInterval]:
        for index in range(len(evidence)):
            interval = temporal_read.valid_time_coverage(shape, recorded, index)
            assert interval is not None
            yield interval

    uncovered = window.first_uncovered(coverage())

    assert uncovered == _MAR
    assert recorded.read == [0, 0, 1, 1]


def test_predecessor_rows_refuse_misaligned_or_empty_evidence() -> None:
    evidence = _person_rows([_person_row(1)], [{}])
    two: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    two.append({})
    two.append({})
    empty = whole(ChunkedColumnBuilder[tuple[object, ...]]().build())

    with pytest.raises(ValueError, match="one raw document with each row"):
        dataclasses.replace(evidence, documents=whole(two.build()))
    with pytest.raises(ValueError, match="at least one row"):
        dataclasses.replace(evidence, rows=empty, documents=None)
    with pytest.raises(ValueError, match="key position"):
        dataclasses.replace(evidence, key_position=len(_PERSON.member_selection.bindings))


def test_a_predecessor_rows_builder_that_appended_nothing_seals_to_nothing() -> None:
    builder = PredecessorRowsBuilder(
        _PERSON.member_selection, key_position=0, absent=ABSENT, documents=True
    )

    assert builder.seal() is None
