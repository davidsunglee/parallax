"""What a writable attempt keeps of the Non-Temporal sources its reads publish
(`cost` class for the byte reading).

A source's authority continues through the attempt's own completed writes, and
ends with a completed deletion of its object, so a read of an object deleted and
inserted again registers its evidence with the attempt. The
registration is weak and refers to the evidence alone: it keeps nothing of the
values the read published, which the collector shows, and nothing once no
value or write reaches the evidence, which only bytes can show. That reading
is a DIFFERENCE between two row counts, so everything a transaction costs that
does not grow with them cancels, and an equality says nothing grows.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
from collections.abc import Callable
from typing import Any, Final

from parallax.conformance.scripted_clock import FixedClock
from parallax.snapshot import connect
from parallax.snapshot._inspection import snapshot_state_of
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests.unit._transact_support import FIXED, PERSON
from tests.unit.core._execution._unit_work._source_continuation_scenarios import people_rows
from tests.unit.memory_instruments import (
    Seam,
    in_a_child_interpreter,
    retained_increment,
    serve_one_measurement,
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
        del published
        gc.collect()
        assert not any(isinstance(held, mm.Person) for held in gc.get_objects())
        assert len(evidence) == _MANY

    _after_reinsertion(_MANY, body, Read(rows=_ROWS[_MANY]))


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
