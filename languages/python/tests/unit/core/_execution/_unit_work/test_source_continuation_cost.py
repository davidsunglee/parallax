"""What a writable attempt keeps of the sources its reads publish.

A Non-Temporal source's authority continues through the attempt's own
completed writes, and ends with a completed deletion of its object, so a read
of an object deleted and inserted again registers its evidence with the
attempt. The registration is weak and refers to the evidence alone: it keeps
nothing of the values the read published, which the collector shows, and
nothing once no value or write reaches the evidence, which only bytes can show.

A temporal source registers nothing: a read holds nothing for continuation, and
a completed write holds the rows it produced only for the observations it
changed, until those are collected. Each byte reading is a DIFFERENCE between
two row counts or two arms, so everything a transaction costs that does not
grow with them cancels, and an equality says nothing grows.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
import weakref
from collections.abc import Callable
from typing import Any, Final

from parallax.conformance.scripted_clock import FixedClock
from parallax.core._execution._unit_work._write_ownership import (
    _HeldCurrentRows,  # pyright: ignore[reportPrivateUsage] - what a reachability count names
    _Origin,  # pyright: ignore[reportPrivateUsage] - what a reachability count names
)
from parallax.snapshot import connect
from parallax.snapshot._inspection import snapshot_state_of
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests.unit._stream_page_support import paged_reads
from tests.unit._transact_support import FIXED, PERSON
from tests.unit._where_position_model import WHERE_POSITION_META, WherePosition
from tests.unit.core._execution._unit_work._source_continuation_scenarios import (
    BATCH,
    people_rows,
    position_rows,
)
from tests.unit.memory_instruments import (
    Seam,
    in_a_child_interpreter,
    retained,
    retained_increment,
    serve_one_measurement,
    tracked_objects,
)

_FEW: Final = 8
_MANY: Final = 40

_ROWS: Final = {count: people_rows(count) for count in (_FEW, _MANY)}
"""Every row a reading reads, built before any window opens, so the bytes of a
row's own values are never what a window sees."""


def _after_reinsertion(count: int, body: Callable[[Any], None], *reads: Read) -> None:
    """``body`` inside a writable transaction that deleted ``count`` people and
    inserted them again, both completed, so every value its reads publish of
    them registers its evidence."""
    rows = _ROWS[count]
    port = ScriptedAdapter(
        Transact(
            Read(rows=rows),
            Write(affected=count),
            Read(rows=[]),
            Write(affected=count),
            Read(rows=[]),
            *reads,
        )
    )

    def delete_all(tx: Any) -> None:
        for person in tx.find(mm.Person.where(mm.Person.id >= 1)).results():
            tx.delete(person)

    def run(tx: Any) -> None:
        delete_all(tx)
        tx.find(mm.Person.where(mm.Person.id == -1)).results()
        for row in rows:
            tx.insert(mm.Person(**row))
        tx.find(mm.Person.where(mm.Person.id == -1)).results()
        body(tx)

    with connect(port, PERSON, clock=FixedClock(FIXED)) as root:
        root.using_database_login().transact(run)


def _released(count: int, *, keeping: bool = False) -> Seam:
    """What a second round of publishing ``count`` sources and releasing them
    leaves behind once a first round has — or, ``keeping``, what the second
    round's sources cost while they are still held."""
    kept: list[object] = []

    def publish_and_release(tx: Any, *, keep: bool) -> None:
        held = tx.find(mm.Person.where(mm.Person.id >= 1)).results()
        assert len(held) == count
        if keep:
            kept.append(held)
        del held
        gc.collect()

    def seam(sample: Callable[[], None]) -> None:
        def body(tx: Any) -> None:
            publish_and_release(tx, keep=False)
            sample()
            publish_and_release(tx, keep=keeping)
            sample()
            kept.clear()

        rows = _ROWS[count]
        _after_reinsertion(count, body, Read(rows=rows), Read(rows=rows))

    return seam


def _reading(measure: Callable[[], int]) -> int:
    tracemalloc.start()
    try:
        return measure()
    finally:
        tracemalloc.stop()


@in_a_child_interpreter
def test_releasing_published_sources_leaves_nothing_of_their_registrations() -> None:
    # Once nothing reaches a source, its registration goes with it, promptly
    # and without another transaction operation: publishing and releasing many
    # sources again leaves exactly what publishing and releasing a few again
    # does.
    few = _reading(lambda: retained_increment(_released(_FEW)))
    many = _reading(lambda: retained_increment(_released(_MANY)))
    assert many == few
    # The reading sees the sources while they are held.
    kept_few = _reading(lambda: retained_increment(_released(_FEW, keeping=True)))
    kept_many = _reading(lambda: retained_increment(_released(_MANY, keeping=True)))
    assert kept_many - kept_few > kept_few - few > 0


def _evidence_of(value: object) -> object:
    state = snapshot_state_of(value)
    assert state is not None and state.read_evidence is not None
    return state.read_evidence


def test_a_registration_keeps_none_of_the_values_its_read_published() -> None:
    # Registration refers to evidence alone, and an unversioned source's
    # evidence carries only its key: once the published values are released,
    # none of them is alive, though every source's evidence still is.
    def body(tx: Any) -> None:
        published = tx.find(mm.Person.where(mm.Person.id >= 1)).results()
        evidence = [_evidence_of(value) for value in published]
        alive = [weakref.ref(value) for value in published]
        del published
        gc.collect()
        assert all(reference() is None for reference in alive)
        assert len(evidence) == _MANY

    _after_reinsertion(_MANY, body, Read(rows=_ROWS[_MANY]))


_RELEASED: Final = (_FEW // 2, _FEW)
"""The source counts a release reading amends every one of, few enough that
each amendment's successors open in one insert."""
_POSITIONS: Final = {count: position_rows(count) for count in (*_RELEASED, _MANY)}
_WRITTEN: Final = 2
_CURRENT: Final = WherePosition.where(WherePosition.id >= 1).as_of(valid_time=FIXED)
_NOTHING: Final = WherePosition.where(WherePosition.id == -1).as_of(valid_time=FIXED)


def _positions_read(count: int, body: Callable[[Any, list[Any]], None], *script: Any) -> None:
    """``body`` inside a writable transaction, handed the ``count`` Bitemporal
    positions its first read published, followed by ``script``."""
    port = ScriptedAdapter(Transact(Read(rows=_POSITIONS[count]), *script))

    def run(tx: Any) -> None:
        body(tx, tx.find(_CURRENT).results())

    with connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)) as root:
        root.using_database_login().transact(run)


def _amended(tx: Any, values: list[Any]) -> None:
    """Each of ``values`` amended, then flushed by a read."""
    for value in values:
        tx.amend(value.edit(acct_num="B"))
    tx.find(_NOTHING).results()


def _amending(count: int) -> tuple[Any, ...]:
    """What the port answers :func:`_amended` of ``count`` values with: each
    one's row closed, the parts they leave opened in one insert, then the
    read."""
    return (Write(times=count), Write(), Read(rows=[])) if count else (Read(rows=[]),)


def _held_for_continuation() -> tuple[int, int]:
    gc.collect()
    objects = tracked_objects()
    return (
        sum(1 for held in objects if isinstance(held, _Origin)),
        sum(1 for held in objects if isinstance(held, _HeldCurrentRows)),
    )


def _temporal_read_holds_nothing_for_continuation(delivery: str) -> None:
    rows = _POSITIONS[_MANY]
    reads = [Read(rows=rows)] if delivery == "eager" else paged_reads(rows, size=BATCH)
    port = ScriptedAdapter(Transact(*reads, *_amending(_WRITTEN)))
    held: list[tuple[int, int]] = []

    def run(tx: Any) -> None:
        if delivery == "eager":
            published = tx.find(_CURRENT).results()
        else:
            with tx.stream(_CURRENT, batch_size=BATCH) as stream:
                published = list(stream)
        held.append(_held_for_continuation())
        _amended(tx, published[:_WRITTEN])
        held.append(_held_for_continuation())

    with connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)) as root:
        root.using_database_login().transact(run)
    # Each written object's changed state has one origin, and the rows its
    # write produced are held for it alone.
    assert held == [(0, 0), (_WRITTEN, _WRITTEN)]


@in_a_child_interpreter
def test_a_temporal_read_holds_nothing_for_continuation_until_a_write_changes_its_state() -> None:
    for delivery in ("eager", "stream"):
        _temporal_read_holds_nothing_for_continuation(delivery)


def _writing_a_few(count: int) -> Seam:
    """What amending a few of ``count`` held Bitemporal sources keeps."""

    def seam(sample: Callable[[], None]) -> None:
        def body(tx: Any, published: list[Any]) -> None:
            sample()
            _amended(tx, published[:_WRITTEN])
            sample()

        _positions_read(count, body, *_amending(_WRITTEN))

    return seam


def _holding(count: int) -> Seam:
    """What ``count`` held Bitemporal sources cost, read and written nothing."""

    def seam(sample: Callable[[], None]) -> None:
        def body(tx: Any, published: list[Any]) -> None:
            assert len(published) == count
            sample()

        _positions_read(count, body)

    return seam


@in_a_child_interpreter
def test_writing_a_few_of_many_temporal_sources_keeps_state_for_those_alone() -> None:
    # The rows a write produced are held only for the observations it changed,
    # so writing the same few keeps what it does however many were read: the
    # readings differ by less than one more held source costs.
    few = _reading(lambda: retained_increment(_writing_a_few(_FEW)))
    many = _reading(lambda: retained_increment(_writing_a_few(_MANY)))
    per_source = (
        _reading(lambda: retained(_holding(_MANY))) - _reading(lambda: retained(_holding(_FEW)))
    ) // (_MANY - _FEW)
    assert few > 0
    assert abs(many - few) < per_source


def _releasing(count: int, *, writing: bool) -> Seam:
    """What releasing ``count`` held Bitemporal sources releases once a flush
    completed — every one of them amended where ``writing`` — as a negative
    increment."""

    def seam(sample: Callable[[], None]) -> None:
        def body(tx: Any, published: list[Any]) -> None:
            _amended(tx, published if writing else [])
            sample()
            published.clear()
            gc.collect()
            sample()

        _positions_read(count, body, *_amending(count if writing else 0))

    return seam


@in_a_child_interpreter
def test_releasing_written_temporal_sources_releases_the_rows_held_for_them() -> None:
    # Releasing the sources a write changed also releases what the attempt
    # held for them, at once and in proportion to how many there were; a
    # read-only arm releases the sources alone.
    released = {
        (count, writing): _reading(
            lambda count=count, writing=writing: retained_increment(
                _releasing(count, writing=writing)
            )
        )
        for count in _RELEASED
        for writing in (False, True)
    }
    fewer, more = (released[count, False] - released[count, True] for count in _RELEASED)
    assert more > fewer > 0


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
