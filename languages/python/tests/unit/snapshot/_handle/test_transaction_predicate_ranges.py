"""A Bitemporal ``amend_where`` through the public transaction over a scripted
port (`m-unit-work` *Materialized Write Groups*, `m-temporal-write`): its
membership selected at ``valid_from``, its later coverage read when its flush
reaches it, batch by batch, every batch executed before the next is read, and
the group reported once after the last — or not at all."""

from __future__ import annotations

import datetime as dt
import gc
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, Bitemporal, DomainModel, attr
from parallax.core.base import INFINITY, DocumentValue, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import JsonDocument, MappingRow
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    Concurrency,
    MaterializedWriteGroup,
    OptimisticLockConflictError,
    WriteEvidenceError,
)
from parallax.core.unit_work import acquisition as acquisition_module
from parallax.core.unit_work import ranges as ranges_module
from parallax.core.unit_work.uow import UnitOfWork
from parallax.core.write_plan import PredecessorRows
from parallax.core.write_plan.plan import UnitEffects
from parallax.snapshot import Database, Transaction
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    CommitCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.root_ownership import own_root
from tests.unit._where_position_model import WHERE_POSITION_META, WherePosition

_JAN, _FEB, _APR, _MAY, _JUN, _JUL = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 4, 5, 6, 7)
)
_FIXED: Final = dt.datetime(2024, 10, 1, tzinfo=dt.UTC)


def _row(key: int, start: dt.datetime, end: object, value: str) -> MappingRow:
    return {
        "id": key,
        "acct_num": "A",
        "value": Decimal(value),
        "from_z": start,
        "thru_z": end,
        "in_z": _JAN,
        "out_z": INFINITY,
    }


def _transact(port: ScriptedAdapter, *, concurrency: Concurrency, fn: Any) -> None:
    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(_FIXED))
    ).using_database_login().transact(fn, concurrency=concurrency)


def _amend(tx: Transaction, *, to: str = "150.00") -> None:
    tx.amend_where(
        WherePosition.where(WherePosition.value == Decimal("150.00")),
        WherePosition.value.set(Decimal(to)),
        valid_from=_FEB,
        until=_JUN,
    )


def _kinds(port: ScriptedAdapter) -> list[str]:
    kinds: list[str] = []
    for call in port.calls:
        if isinstance(call, ReadCall):
            kinds.append("read")
        elif isinstance(call, WriteCall):
            kinds.append("insert" if call.sql.startswith("insert") else "update")
        elif isinstance(call, CommitCall | RollbackCall):
            kinds.append(type(call).__name__)
    return kinds


def test_membership_is_selected_at_valid_from_and_no_match_buffers_nothing() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[])))
    _transact(port, concurrency="optimistic", fn=_amend)
    (selection,) = [call for call in port.calls if isinstance(call, ReadCall)]
    assert "t0.from_z <= %s and t0.thru_z > %s" in selection.sql
    assert selection.binds.count(_FEB) == 2
    assert not [call for call in port.calls if isinstance(call, WriteCall)]


def test_a_start_equal_object_still_amends_the_later_coverage_it_reaches() -> None:
    # February already holds 150 and April holds 200, which no longer matches
    # the predicate: the starting milestone is kept under the shared lock, and
    # April's coverage is read at the flush and amended through June.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_row(1, _JAN, _APR, "150.00")]),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(times=3),
        )
    )
    _transact(port, concurrency="locking", fn=_amend)
    reads = [call for call in port.calls if isinstance(call, ReadCall)]
    assert len(reads) == 2
    coverage = reads[1]
    assert coverage.binds[:3] == (1, _APR, _JUN)
    assert coverage.sql.endswith(" for share of t0")
    close, changed, carried = [call for call in port.calls if isinstance(call, WriteCall)]
    assert close.sql.startswith("update") and _JUL in close.binds
    assert (changed.binds[2], changed.binds[3:5]) == (Decimal("150.00"), (_APR, _JUN))
    assert (carried.binds[2], carried.binds[3:5]) == (Decimal("200.00"), (_JUN, _JUL))


def test_an_unchanged_start_is_proven_by_a_guard_under_optimistic_concurrency() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_row(1, _JAN, _APR, "150.00")]),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(times=4),
        )
    )
    _transact(port, concurrency="optimistic", fn=_amend)
    guard, close, *_openings = [call for call in port.calls if isinstance(call, WriteCall)]
    assert "set in_z = in_z" in guard.sql
    assert _APR in guard.binds and _JAN in guard.binds
    assert "set out_z" in close.sql and _JUL in close.binds


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_an_object_selected_by_two_starting_rows_is_cardinality_corruption(
    concurrency: Concurrency,
) -> None:
    # Object 1's overlapping [January, April) and [February, May) both hold
    # February; object 2 between them in resolution order does not hide it.
    port = ScriptedAdapter(
        Transact(
            Read(
                rows=[
                    _row(1, _JAN, _APR, "100.00"),
                    _row(2, _JAN, _APR, "100.00"),
                    _row(1, _FEB, _MAY, "100.00"),
                ]
            ),
            Read(rows=[_row(1, _MAY, _JUL, "100.00")]),
            Write(times=12),
        )
    )
    with raises_contextualized(CardinalityCorruptionError) as raised:
        _transact(port, concurrency=concurrency, fn=_amend)
    assert (raised.value.expected, raised.value.actual) == (1, 2)
    assert raised.value.target.key_values == ((1,),)
    assert _kinds(port) == ["read", "RollbackCall"]


def _two_objects() -> list[MappingRow]:
    return [_row(key, _JAN, _APR, "100.00") for key in (1, 2)]


def test_each_batch_executes_before_the_next_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    port = ScriptedAdapter(
        Transact(
            Read(rows=_two_objects()),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(times=5),
            Read(rows=[_row(2, _APR, _JUL, "200.00")]),
            Write(times=5),
        )
    )
    _transact(port, concurrency="locking", fn=_amend)
    # Each object's two closes, its head, its two equal changed parts as one
    # row, and its tail.
    batch = ["read", "update", "update", "insert", "insert", "insert"]
    assert _kinds(port) == ["read", *batch, *batch, "CommitCall"]


def test_a_later_batchs_failure_rolls_back_what_earlier_batches_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    failure = DatabaseError(category=None, native_code=None, message="coverage read refused")
    port = ScriptedAdapter(
        Transact(
            Read(rows=_two_objects()),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(times=5),
            Read(raises=failure),
        )
    )
    with raises_contextualized(DatabaseError) as raised:
        _transact(port, concurrency="locking", fn=_amend)
    assert raised.value is failure
    assert _kinds(port) == [
        "read",
        "read",
        "update",
        "update",
        "insert",
        "insert",
        "insert",
        "read",
        "RollbackCall",
    ]


def test_a_shortfall_in_one_batch_prepares_no_later_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_row(key, _JAN, _APR, "100.00") for key in (1, 2)]),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(affected=0),
        )
    )
    with raises_contextualized(OptimisticLockConflictError):
        _transact(port, concurrency="optimistic", fn=_amend)
    assert _kinds(port) == ["read", "read", "update", "RollbackCall"]


class _CleanupFailedError(RuntimeError):
    pass


def test_a_cleanup_failure_alone_refuses_the_groups_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(self: object) -> None:
        del self
        raise _CleanupFailedError

    monkeypatch.setattr(ranges_module.GroupContinuation, "close", failing)
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_row(1, _JAN, _APR, "100.00")]),
            Read(rows=[]),
            Write(times=3),
        )
    )
    with raises_contextualized(_CleanupFailedError):
        _transact(port, concurrency="locking", fn=_amend)
    assert _kinds(port)[-1] == "RollbackCall"


def test_a_cleanup_failure_after_another_keeps_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(self: object) -> None:
        del self
        raise _CleanupFailedError

    monkeypatch.setattr(ranges_module.GroupContinuation, "close", failing)
    failure = DatabaseError(category=None, native_code=None, message="coverage read refused")
    port = ScriptedAdapter(
        Transact(Read(rows=[_row(1, _JAN, _APR, "100.00")]), Read(raises=failure))
    )
    with raises_contextualized(DatabaseError) as raised:
        _transact(port, concurrency="locking", fn=_amend)
    assert raised.value is failure
    assert any("_CleanupFailedError" in note for note in failure.__notes__)


def test_an_interruption_between_batches_closes_the_group_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    pull, close = ranges_module.GroupContinuation.pull, ranges_module.GroupContinuation.close
    pulled: list[object] = []
    closed: list[object] = []

    def interrupted(self: ranges_module.GroupContinuation) -> object:
        pulled.append(self)
        if len(pulled) == 2:
            raise KeyboardInterrupt
        return pull(self)

    def recorded(self: ranges_module.GroupContinuation) -> None:
        closed.append(self)
        close(self)

    monkeypatch.setattr(ranges_module.GroupContinuation, "pull", interrupted)
    monkeypatch.setattr(ranges_module.GroupContinuation, "close", recorded)
    port = ScriptedAdapter(
        Transact(
            Read(rows=_two_objects()),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(times=6),
        )
    )
    with pytest.raises(KeyboardInterrupt):
        _transact(port, concurrency="locking", fn=_amend)
    assert closed == pulled[:1]
    assert _kinds(port)[-1] == "RollbackCall"


def test_the_group_completes_once_after_its_last_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    completed: list[UnitEffects] = []
    complete = UnitOfWork._complete  # pyright: ignore[reportPrivateUsage]

    def counting(self: UnitOfWork, unit: Any, effects: Any, allocated: Any) -> None:
        completed.append(effects)
        complete(self, unit, effects, allocated)

    monkeypatch.setattr(UnitOfWork, "_complete", counting)
    port = ScriptedAdapter(
        Transact(
            Read(rows=_two_objects()),
            Read(rows=[]),
            Write(times=3),
            Read(rows=[]),
            Write(times=3),
        )
    )
    _transact(port, concurrency="locking", fn=_amend)
    (effects,) = completed
    assert len(list(effects.changed)) == 2


def _alive(kind: type) -> int:
    gc.collect()
    return sum(isinstance(value, kind) for value in gc.get_objects())


def test_planning_hands_the_selected_rows_over_and_each_batch_releases_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Once planning succeeds nothing keeps the group: when the second batch's
    # coverage is read, neither the group nor the rows selection or the first
    # batch read survive.
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    seen: list[tuple[int, int]] = []
    consume = acquisition_module.consume_coverage

    def observed(*args: Any) -> Any:
        seen.append((_alive(MaterializedWriteGroup), _alive(PredecessorRows)))
        return consume(*args)

    monkeypatch.setattr(ranges_module, "consume_coverage", observed)
    alive = (_alive(MaterializedWriteGroup), _alive(PredecessorRows))
    port = ScriptedAdapter(
        Transact(
            Read(rows=_two_objects()),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(times=5),
            Read(rows=[_row(2, _APR, _JUL, "200.00")]),
            Write(times=5),
        )
    )
    _transact(port, concurrency="locking", fn=_amend)
    assert seen == [alive, alive]


def test_a_later_write_observing_another_state_of_a_selected_object_is_refused() -> None:
    # The pending amendment reaches the April rectangle when its flush reaches
    # it, so a write observing that rectangle would settle against coverage
    # the group changes first.
    refusals: list[WriteEvidenceError] = []

    def fn(tx: Transaction) -> None:
        april = tx.find(WherePosition.where(WherePosition.id == 1).as_of(valid_time=_APR)).result()
        _amend(tx)
        try:
            tx.amend(april.edit(acct_num="B"))
        except WriteEvidenceError as refused:
            refusals.append(refused)

    port = ScriptedAdapter(
        Transact(
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Read(rows=[_row(1, _JAN, _APR, "150.00")]),
            Read(rows=[_row(1, _APR, _JUL, "200.00")]),
            Write(times=3),
        )
    )
    _transact(port, concurrency="locking", fn=fn)
    (refused,) = refusals
    assert refused.code == "write-evidence-already-claimed"


def test_a_batchs_objects_share_one_coverage_read() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=_two_objects()),
            Read(rows=[_row(1, _APR, _JUL, "200.00"), _row(2, _APR, _JUL, "200.00")]),
            Write(times=12),
        )
    )
    _transact(port, concurrency="locking", fn=_amend)
    _selection, coverage = [call for call in port.calls if isinstance(call, ReadCall)]
    assert "((t0.id = %s and t0.thru_z > %s and t0.from_z < %s) or (t0.id = %s" in coverage.sql
    assert coverage.binds[:6] == (1, _APR, _JUN, 2, _APR, _JUN)


# --------------------------------------------------------------------------- #
# A scalar collection moves none of the group's gates: it is selected at       #
# valid_from, refused for two starting rows before buffering, and reaches its  #
# later coverage at the flush, its equal start kept.                           #
# --------------------------------------------------------------------------- #
class WhereTagged(Bitemporal, table="where_tagged", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()


_WHERE_TAGGED_META: Final = DomainModel(WhereTagged)


def _tagged(key: int, start: dt.datetime, end: object, tags: list[DocumentValue]) -> MappingRow:
    return {
        "id": key,
        "tags": PresentDocument(tags),
        "from_z": start,
        "thru_z": end,
        "in_z": _JAN,
        "out_z": INFINITY,
    }


def _tag(tx: Transaction) -> None:
    tx.amend_where(
        WhereTagged.where(WhereTagged.id <= 2),
        WhereTagged.tags.set(("z", "z")),
        valid_from=_FEB,
        until=_JUN,
    )


def _transact_tagged(port: ScriptedAdapter, *, concurrency: Concurrency) -> None:
    own_root(
        Database.connect(port, _WHERE_TAGGED_META, clock=FixedClock(_FIXED))
    ).using_database_login().transact(_tag, concurrency=concurrency)


def test_a_collection_amendment_keeps_an_equal_start_and_reads_later_coverage_at_its_flush() -> (
    None
):
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_tagged(1, _JAN, _APR, ["z", "z"])]),
            Read(rows=[_tagged(1, _APR, _JUL, ["y"])]),
            Write(times=3),
        )
    )
    _transact_tagged(port, concurrency="locking")
    selection, coverage = [call for call in port.calls if isinstance(call, ReadCall)]
    assert selection.binds.count(_FEB) == 2
    # Only the uncovered April onwards is read, and only when the flush reaches it.
    assert coverage.binds[:3] == (1, _APR, _JUN)
    assert _kinds(port) == ["read", "read", "update", "insert", "insert", "CommitCall"]
    _close, changed, carried = [call for call in port.calls if isinstance(call, WriteCall)]
    assert JsonDocument(("z", "z")) in changed.binds
    assert JsonDocument(("y",)) in carried.binds


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_an_object_whose_collection_starts_twice_is_refused_before_buffering(
    concurrency: Concurrency,
) -> None:
    port = ScriptedAdapter(
        Transact(
            Read(
                rows=[
                    _tagged(1, _JAN, _APR, ["a"]),
                    _tagged(2, _JAN, _APR, ["a"]),
                    _tagged(1, _FEB, _MAY, ["b"]),
                ]
            ),
            Read(rows=[]),
            Write(times=12),
        )
    )
    with raises_contextualized(CardinalityCorruptionError) as raised:
        _transact_tagged(port, concurrency=concurrency)
    assert raised.value.target.key_values == ((1,),)
    assert _kinds(port) == ["read", "RollbackCall"]
