"""Caller-addressed patch and replacement of temporal objects through the public
verbs (scripted port).

A temporal target states its key, its Valid-Time window where its family has
one, and the Transaction-Time start its caller last observed. These tests grade
what each call puts on the wire and when: nothing at an Optimistic call and the
coverage read at flush, the Locking acquisition and its reuse, the start guard
that fails as the caller's precondition while a later row's loss retries, the
empty patch, bounds validation, the exact-window composition matrix with
observed writes, and the refusals that leave earlier work executable.
"""

from __future__ import annotations

import datetime as dt
import gc
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Literal, cast

import pytest

from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import MappingRow
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    OptimisticLockConflictError,
    RollbackOnlyError,
    WriteInstructionError,
    WritePreconditionError,
    WriteRejectedError,
)
from parallax.snapshot.handle import ScopedDatabase, Transaction, WriteEvidenceError
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    PortCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._transact_support import (
    BALANCE,
    FIXED,
    INFINITY_INSTANT,
    RATE,
    WHERE_POSITION_META,
    WherePosition,
    balance_row,
    db_for,
)

type _Concurrency = Literal["optimistic", "locking"]

_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _JUN, _AUG, _SEP, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3, 6, 8, 9, 12)
)


def _rectangle(
    start: dt.datetime, end: object, value: str = "100.00", tx_start: dt.datetime = _T0
) -> MappingRow:
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal(value),
        "from_z": start,
        "thru_z": end,
        "in_z": tx_start,
        "out_z": INFINITY_INSTANT,
    }


def _calls(port: ScriptedAdapter) -> list[PortCall]:
    return [call for call in port.calls if not isinstance(call, BeginCall | CommitCall)]


def _reads(port: ScriptedAdapter) -> list[ReadCall]:
    return [call for call in port.calls if isinstance(call, ReadCall)]


def _writes(port: ScriptedAdapter) -> list[WriteCall]:
    return [call for call in port.calls if isinstance(call, WriteCall)]


def _patch(tx: Transaction, *, tx_start: dt.datetime = _T0, **changes: object) -> None:
    tx.wire.update(
        "WherePosition",
        {"id": 1, **changes},
        valid_from=_MAR,
        until=_SEP,
        if_tx_start=tx_start,
    )


def _replace(tx: Transaction, *, typed: bool = False, value: str = "300.00") -> None:
    if typed:
        tx.replace(
            WherePosition(id=1, acct_num="Z", value=Decimal(value)),
            valid_from=_MAR,
            until=_SEP,
            if_tx_start=_T0,
        )
    else:
        tx.wire.replace(
            "WherePosition",
            {"id": 1, "acctNum": "Z", "value": value},
            valid_from=_MAR,
            until=_SEP,
            if_tx_start=_T0,
        )


def _db(port: ScriptedAdapter) -> ScopedDatabase:
    return db_for(WHERE_POSITION_META, port)


def _source(tx: Transaction, at: dt.datetime = _MAR) -> WherePosition:
    return tx.find(WherePosition.where(WherePosition.id == 1).as_of(valid_time=at)).result()


# --------------------------------------------------------------------------- #
# Optimistic: nothing at the call; the flush reads the coverage it reaches.   #
# --------------------------------------------------------------------------- #
def test_an_optimistic_transaction_time_target_reads_its_current_row_only_at_flush() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[balance_row(in_z=_T0)]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        tx.wire.update("Balance", {"id": 1, "value": "150.00"}, if_tx_start=_T0)
        assert _calls(port) == []

    db_for(BALANCE, port).transact(fn)
    (coverage,) = _reads(port)
    assert coverage.sql.endswith("from balance t0 where t0.bal_id = %s and t0.out_z = %s")
    close, opened = _writes(port)
    assert close.sql.endswith("where bal_id = %s and out_z = %s and in_z = %s")
    assert close.binds[1:] == (1, "infinity", _T0)
    assert opened.binds[:3] == (1, "A-1", Decimal("150.00"))


def test_an_optimistic_bitemporal_target_binds_every_interval_its_window_reaches() -> None:
    later = _rectangle(_JUN, INFINITY_INSTANT, "200.00", tx_start=_T1)
    port = ScriptedAdapter(Transact(Read(rows=[_rectangle(_JAN, _JUN), later]), Write(times=6)))

    def fn(tx: Transaction) -> None:
        _patch(tx, value="150.00")
        assert _calls(port) == []

    _db(port).transact(fn)
    (coverage,) = _reads(port)
    assert coverage.sql.endswith(
        "where t0.id = %s and t0.thru_z > %s and t0.from_z < %s and t0.out_z = %s"
    )
    assert coverage.binds == (1, _MAR, _SEP, "infinity")
    start, later_close, *opened = _writes(port)
    # The start's gate binds the caller's milestone, a later row's its own.
    assert (start.binds[2], start.binds[-1]) == (_JUN, _T0)
    assert (later_close.binds[2], later_close.binds[-1]) == ("infinity", _T1)
    assert [call.binds[2:5] for call in opened] == [
        (Decimal("100.00"), _JAN, _MAR),
        (Decimal("150.00"), _MAR, _JUN),
        (Decimal("150.00"), _JUN, _SEP),
        (Decimal("200.00"), _SEP, INFINITY_INSTANT),
    ]


@pytest.mark.parametrize(
    "coverage",
    [
        pytest.param([], id="no-coverage"),
        pytest.param([_rectangle(_JUN, INFINITY_INSTANT)], id="a-gap-at-its-start"),
        pytest.param([_rectangle(_JAN, _JUN, tx_start=_T1)], id="another-revision"),
    ],
)
def test_an_optimistic_target_whose_start_moved_fails_before_any_write_and_never_retries(
    coverage: list[MappingRow],
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=coverage)))
    attempts = 0

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        _replace(tx)

    with raises_contextualized(WritePreconditionError) as failed:
        _db(port).transact(fn, retry_optimistic_conflicts=True)
    assert (dict(failed.value.key), failed.value.expected) == ({"id": 1}, _T0)
    assert attempts == 1
    assert _writes(port) == []
    assert isinstance(port.calls[-1], RollbackCall)


def test_a_lost_start_guard_is_the_callers_precondition_and_a_lost_later_row_retries() -> None:
    rows = [_rectangle(_JAN, _JUN), _rectangle(_JUN, INFINITY_INSTANT, "200.00")]
    lost_start = ScriptedAdapter(Transact(Read(rows=rows), Write(affected=0)))
    with raises_contextualized(WritePreconditionError):
        _db(lost_start).transact(
            lambda tx: _patch(tx, value="150.00"), retry_optimistic_conflicts=True
        )
    assert len(_writes(lost_start)) == 1
    lost_later = ScriptedAdapter(
        Transact(Read(rows=rows), Write(), Write(affected=0)),
        Transact(Read(rows=rows), Write(times=6)),
    )
    _db(lost_later).transact(lambda tx: _patch(tx, value="150.00"), retry_optimistic_conflicts=True)
    starts = [call for call in _writes(lost_later) if call.binds[2] == _JUN]
    assert [call.binds[-1] for call in starts] == [_T0, _T0]
    without_retry = ScriptedAdapter(Transact(Read(rows=rows), Write(), Write(affected=0)))
    with raises_contextualized(OptimisticLockConflictError):
        _db(without_retry).transact(lambda tx: _patch(tx, value="150.00"))


# --------------------------------------------------------------------------- #
# Locking: the start is read under the shared lock at the call, or reused.     #
# --------------------------------------------------------------------------- #
def test_a_locking_bitemporal_target_reads_its_start_at_the_call_and_writes_ungated() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)], times=2), Write(times=4))
    )

    def fn(tx: Transaction) -> None:
        _patch(tx, value="150.00")
        (acquired,) = _reads(port)
        assert acquired.sql.endswith(
            "where t0.id = %s and t0.from_z <= %s and t0.thru_z > %s and t0.out_z = %s "
            "for share of t0"
        )
        assert acquired.binds == (1, _MAR, _MAR, "infinity")

    _db(port).transact(fn, concurrency="locking")
    _acquired, coverage = _reads(port)
    assert coverage.sql.endswith("for share of t0")
    close, *_opened = _writes(port)
    assert close.sql.endswith("where id = %s and thru_z = %s and out_z = %s")


def test_a_locking_transaction_time_target_reads_its_current_row_under_the_shared_lock() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[balance_row(in_z=_T0)], times=2), Write(times=2)))
    db_for(BALANCE, port).transact(
        lambda tx: tx.replace(
            mm.Balance(id=1, acct_num="B", value=Decimal("7.00")), if_tx_start=_T0
        ),
        concurrency="locking",
    )
    acquired, coverage = _reads(port)
    assert acquired.sql.endswith("where t0.bal_id = %s and t0.out_z = %s for share of t0")
    assert coverage.sql == acquired.sql
    close, opened = _writes(port)
    assert close.sql.endswith("where bal_id = %s and out_z = %s")
    assert opened.binds[:3] == (1, "B", Decimal("7.00"))


@pytest.mark.parametrize(
    "stored",
    [[_rectangle(_JAN, INFINITY_INSTANT, tx_start=_T1)], []],
    ids=["another-revision", "no-row"],
)
def test_a_locking_target_refuses_a_stale_or_missing_start_at_the_call(
    stored: list[MappingRow],
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=stored), Write()))

    def fn(tx: Transaction) -> None:
        tx.insert(WherePosition(id=7, acct_num="N", value=Decimal("1.00")), valid_from=_JAN)
        with pytest.raises(WritePreconditionError) as refused:
            _patch(tx, value="150.00")
        assert (dict(refused.value.key), refused.value.expected) == ({"id": 1}, _T0)

    _db(port).transact(fn, concurrency="locking")
    (insert,) = _writes(port)
    assert insert.sql.startswith("insert into where_position")


def test_a_locking_target_reuses_a_held_read_of_exactly_its_start() -> None:
    # A read pinned at the rectangle's own start names the state the target's
    # start and stated milestone name, so it needs no acquisition; the flush
    # still reads the coverage the window reaches.
    held = _rectangle(_MAR, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Read(rows=[held], times=2), Write(times=3)))

    def fn(tx: Transaction) -> None:
        source = _source(tx)
        _patch(tx, value="150.00")
        assert len(_reads(port)) == 1
        assert source.value == Decimal("100.00")

    _db(port).transact(fn, concurrency="locking")
    assert len(_reads(port)) == 2


def test_a_held_read_of_a_rectangle_its_start_lies_inside_is_no_exact_hit() -> None:
    held = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Read(rows=[held], times=3), Write(times=4)))

    def fn(tx: Transaction) -> None:
        source = _source(tx, _FEB)
        _patch(tx, value="150.00")
        assert len(_reads(port)) == 2
        assert source.value == Decimal("100.00")

    _db(port).transact(fn, concurrency="locking")


def test_a_locking_target_reuses_a_pending_observed_write_of_its_start() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]), Write(times=4))
    )

    def fn(tx: Transaction) -> None:
        source = _source(tx)
        tx.update(source.edit(acct_num="B"), until=_SEP)
        del source
        gc.collect()
        _patch(tx, value="150.00")
        assert len(_reads(port)) == 1

    _db(port).transact(fn, concurrency="locking")
    assert len(_reads(port)) == 1
    _close, head, middle, tail = _writes(port)
    assert middle.binds[1:5] == ("B", Decimal("150.00"), _MAR, _SEP)
    assert (head.binds[1:3], tail.binds[1:3]) == (("A", Decimal("100.00")),) * 2


# --------------------------------------------------------------------------- #
# Empty patches and bounds: validated, then nothing.                           #
# --------------------------------------------------------------------------- #
@_STRATEGIES
def test_an_identity_only_temporal_patch_reads_writes_and_checks_nothing(
    concurrency: _Concurrency,
) -> None:
    transaction_time = ScriptedAdapter(Transact())
    db_for(BALANCE, transaction_time).transact(
        lambda tx: tx.wire.update("Balance", {"id": 1}, if_tx_start=_T0), concurrency=concurrency
    )
    bitemporal = ScriptedAdapter(Transact())
    _db(bitemporal).transact(
        lambda tx: tx.wire.update("WherePosition", {"id": 1}, valid_from=_MAR, if_tx_start=_T0),
        concurrency=concurrency,
    )
    assert _calls(transaction_time) == _calls(bitemporal) == []


_BALANCE_REFUSALS: dict[str, tuple[Callable[[Transaction], None], str]] = {
    "until": (
        lambda tx: tx.wire.update("Balance", {"id": 1}, until=_SEP, if_tx_start=_T0),
        "takes no until",
    ),
    "valid-from": (
        lambda tx: tx.wire.update("Balance", {"id": 1}, valid_from=_MAR, if_tx_start=_T0),
        "takes no valid_from",
    ),
    "a-version": (
        lambda tx: tx.wire.update("Balance", {"id": 1}, if_version=3),
        "takes if_tx_start, not if_version",
    ),
    "no-revision": (
        lambda tx: tx.replace(mm.Balance(id=1, acct_num="B", value=Decimal("1.00"))),
        "requires if_tx_start",
    ),
}
_POSITION_REFUSALS: dict[str, tuple[Callable[[Transaction], None], str]] = {
    "explicit-none": (
        lambda tx: tx.wire.update(
            "WherePosition",
            {"id": 1},
            valid_from=_MAR,
            until=cast("dt.datetime", None),
            if_tx_start=_T0,
        ),
        "until is absent",
    ),
    "until-not-after-start": (
        lambda tx: tx.wire.replace(
            "WherePosition",
            {"id": 1, "acctNum": "Z", "value": "1.00"},
            valid_from=_MAR,
            until=_MAR,
            if_tx_start=_T0,
        ),
        "valid_from < until",
    ),
    "no-start": (
        lambda tx: tx.wire.update("WherePosition", {"id": 1}, if_tx_start=_T0),
        "requires valid_from",
    ),
    "no-revision": (
        lambda tx: tx.wire.update("WherePosition", {"id": 1}, valid_from=_MAR),
        "requires if_tx_start",
    ),
}
_REFUSALS = [
    pytest.param(BALANCE, *refusal, id=f"transaction-time-{name}")
    for name, refusal in _BALANCE_REFUSALS.items()
] + [
    pytest.param(WHERE_POSITION_META, *refusal, id=f"bitemporal-{name}")
    for name, refusal in _POSITION_REFUSALS.items()
]


@pytest.mark.parametrize(("model", "verb", "match"), _REFUSALS)
def test_a_temporal_targets_window_and_revision_are_judged_before_an_empty_patch_drops(
    model: Any, verb: Callable[[Transaction], None], match: str
) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteInstructionError, match=match):
            verb(tx)

    db_for(model, port).transact(fn, concurrency="locking")
    assert _calls(port) == []


def test_a_typed_replacement_selects_its_bounded_form_by_until_alone() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]), Write(times=3)),
        Transact(Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]), Write(times=4)),
    )

    def unbounded(tx: Transaction) -> None:
        tx.replace(
            WherePosition(id=1, acct_num="Z", value=Decimal("3.00")),
            valid_from=_MAR,
            if_tx_start=_T0,
        )

    _db(port).transact(unbounded)
    _db(port).transact(lambda tx: _replace(tx, typed=True))
    inserts = [call for call in _writes(port) if call.sql.startswith("insert")]
    assert [call.binds[3:5] for call in inserts] == [
        (_JAN, _MAR),
        (_MAR, "infinity"),
        (_JAN, _MAR),
        (_MAR, _SEP),
        (_SEP, INFINITY_INSTANT),
    ]


# --------------------------------------------------------------------------- #
# The attempt-wide refusal of an object the attempt inserted.                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("flushed", [False, True], ids=["pending", "after-a-helper-read"])
@pytest.mark.parametrize("representation", ["typed", "wire"])
def test_a_temporal_target_of_an_object_this_attempt_inserted_is_refused(
    flushed: bool, representation: str
) -> None:
    port = ScriptedAdapter(Transact(Write(), Read(rows=[])) if flushed else Transact(Write()))

    def fn(tx: Transaction) -> None:
        tx.insert(WherePosition(id=1, acct_num="A", value=Decimal("1.00")), valid_from=_JAN)
        if flushed:
            tx.find(WherePosition.where(WherePosition.id == 2).as_of(valid_time=_MAR))
        with pytest.raises(WriteEvidenceError, match="write-evidence-inserted"):
            if representation == "typed":
                _replace(tx, typed=True)
            else:
                _patch(tx, value="2.00")
        _patch(tx)

    _db(port).transact(fn, concurrency="locking")
    assert len(_writes(port)) == 1


# --------------------------------------------------------------------------- #
# Exact-window composition with observed writes of the starting rectangle.     #
# --------------------------------------------------------------------------- #
# Every sequence reads the rectangle [March, infinity) at March first, so its
# observed writes start where the targets do, and a Locking target finds that
# read as the exact state it starts from.
_HELD = _rectangle(_MAR, INFINITY_INSTANT)

type _Step = Callable[[Transaction, WherePosition], WherePosition]


def _p(tx: Transaction, source: WherePosition) -> WherePosition:
    _patch(tx, value="150.00")
    return source


def _r(tx: Transaction, source: WherePosition) -> WherePosition:
    _replace(tx)
    return source


def _o(tx: Transaction, source: WherePosition) -> WherePosition:
    edited = source.edit(acct_num="O" if source.acct_num != "O" else "Q")
    tx.update(edited, until=_SEP)
    return edited


def _d(tx: Transaction, source: WherePosition) -> WherePosition:
    tx.terminate(source, until=_SEP)
    return source


_STEPS: dict[str, _Step] = {"P": _p, "R": _r, "O": _o, "D": _d}

# The piece [March, September) each sequence leaves, or None where it destroys
# the window: (acct_num, value).
_MATRIX: dict[str, tuple[str, str] | None] = {
    "P-P": ("A", "150.00"),
    "P-R": ("Z", "300.00"),
    "R-P": ("Z", "150.00"),
    "R-R": ("Z", "300.00"),
    "P-O": ("O", "150.00"),
    "O-P": ("O", "150.00"),
    "R-O": ("O", "300.00"),
    "O-R": ("Z", "300.00"),
    "P-D": None,
    "R-D": None,
    "P-O-O": ("Q", "150.00"),
    "R-O-P": ("O", "150.00"),
    "O-R-D": None,
}


def _reads_coverage(sequence: str) -> bool:
    """Whether the composed range reads its coverage at flush: only where no
    observed write of the object brings the rectangle it starts from."""
    return not ({"O", "D"} & set(sequence.split("-")))


@pytest.mark.parametrize("sequence", list(_MATRIX), ids=list(_MATRIX))
@_STRATEGIES
def test_exact_window_target_and_observed_writes_compose_into_one_range(
    sequence: str, concurrency: _Concurrency
) -> None:
    middle = _MATRIX[sequence]
    coverage = [Read(rows=[_HELD])] if _reads_coverage(sequence) else []
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_HELD]),
            *coverage,
            Write(times=3 if middle is not None else 2),
            Read(rows=[]),
        )
    )

    def fn(tx: Transaction) -> None:
        source = _source(tx)
        for step in sequence.split("-"):
            source = _STEPS[step](tx, source)
        assert len(_reads(port)) == 1
        tx.find(WherePosition.where(WherePosition.id == 2).as_of(valid_time=_MAR))
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.update(source.edit(acct_num="again"))

    _db(port).transact(fn, concurrency=concurrency)
    close, *opened = _writes(port)
    gated = concurrency == "optimistic"
    assert close.sql.endswith("and in_z = %s" if gated else "and out_z = %s")
    if gated:
        assert close.binds[-1] == _T0
    windows = [(call.binds[1], call.binds[2], call.binds[3], call.binds[4]) for call in opened]
    tail = ("A", Decimal("100.00"), _SEP, INFINITY_INSTANT)
    if middle is None:
        assert windows == [tail]
    else:
        assert windows == [(middle[0], Decimal(middle[1]), _MAR, _SEP), tail]


def _refused(*steps: Callable[[Transaction, WherePosition], object]) -> _Step:
    def sequence(tx: Transaction, source: WherePosition) -> WherePosition:
        *earlier, last = steps
        for step in earlier:
            step(tx, source)
        with pytest.raises(WriteEvidenceError, match="write-evidence-already-claimed"):
            last(tx, source)
        return source

    return sequence


# Each sequence's refused last write, and whether the earlier writes left still
# read their coverage at flush.
_REFUSED: dict[str, tuple[_Step, bool]] = {
    "D-P": (_refused(_d, _p), False),
    "D-R": (_refused(_d, _r), False),
    "P-D-O": (_refused(_p, _d, _o), False),
    "P-another-start": (_refused(_p, lambda tx, _s: _patch(tx, tx_start=_T1, value="1.00")), True),
    "O-unequal-window-P": (_refused(lambda tx, s: tx.update(s.edit(acct_num="O")), _p), False),
    "P-unequal-window-O": (_refused(_p, lambda tx, s: tx.update(s.edit(acct_num="O"))), True),
}


@pytest.mark.parametrize("sequence", list(_REFUSED), ids=list(_REFUSED))
@_STRATEGIES
def test_a_write_that_cannot_share_a_targets_window_or_start_is_refused_atomically(
    sequence: str, concurrency: _Concurrency
) -> None:
    refused, reads_coverage = _REFUSED[sequence]
    coverage = [Read(rows=[_HELD])] if reads_coverage else []
    port = ScriptedAdapter(Transact(Read(rows=[_HELD]), *coverage, Write(times=2), Write(times=1)))

    def fn(tx: Transaction) -> None:
        refused(tx, _source(tx))
        assert len(_reads(port)) == 1

    _db(port).transact(fn, concurrency=concurrency)
    assert len(_reads(port)) == 1 + reads_coverage
    assert _writes(port)


def test_a_target_after_an_observed_write_of_another_revision_is_refused() -> None:
    # The source observed the rectangle at a later revision than the one the
    # caller states, so the two cannot start from one state.
    port = ScriptedAdapter(
        Transact(Read(rows=[_rectangle(_MAR, INFINITY_INSTANT, tx_start=_T1)]), Write(times=3))
    )

    def fn(tx: Transaction) -> None:
        tx.update(_source(tx).edit(acct_num="O"), until=_SEP)
        with pytest.raises(WriteEvidenceError, match="write-evidence-already-claimed"):
            _patch(tx, value="150.00")

    _db(port).transact(fn)
    assert len(_writes(port)) == 3


# --------------------------------------------------------------------------- #
# Revision intent, failure precedence, isolation and subtype routing.          #
# --------------------------------------------------------------------------- #
def test_an_equal_valued_temporal_patch_still_chains_its_milestone() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]), Write(times=4))
    )
    _db(port).transact(lambda tx: _patch(tx, value="100.00"))
    close, *opened = _writes(port)
    assert close.sql.startswith("update where_position set out_z")
    assert [call.binds[2] for call in opened] == [Decimal("100.00")] * 3


@_STRATEGIES
def test_a_temporal_target_runs_at_the_configured_isolation_level(
    concurrency: _Concurrency,
) -> None:
    reads = [Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)])] * (
        2 if concurrency == "locking" else 1
    )
    port = ScriptedAdapter(Transact(*reads, Write(times=4)))
    _db(port).transact(lambda tx: _patch(tx, value="150.00"), concurrency=concurrency)
    assert port.calls[0] == BeginCall(isolation="read_committed")


def test_an_invariant_failure_of_the_start_outranks_the_callers_precondition() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]), Write(affected=2))
    )
    with raises_contextualized(CardinalityCorruptionError):
        _db(port).transact(lambda tx: _patch(tx, value="150.00"))


@_STRATEGIES
def test_two_current_rows_at_the_start_are_corruption_before_any_write(
    concurrency: _Concurrency,
) -> None:
    overlapping = [_rectangle(_JAN, INFINITY_INSTANT), _rectangle(_FEB, _JUN, tx_start=_T1)]
    port = ScriptedAdapter(Transact(Read(rows=overlapping)))
    attempts = 0

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        _patch(tx, value="150.00")

    with raises_contextualized(CardinalityCorruptionError) as corrupt:
        _db(port).transact(fn, concurrency=concurrency, retry_optimistic_conflicts=True)
    assert (corrupt.value.expected, corrupt.value.actual) == (1, 2)
    assert attempts == 1
    assert _writes(port) == []


def test_a_locked_observation_and_a_flush_read_row_both_at_the_start_are_corruption() -> None:
    # Under Locking the observed rectangle is held under the shared lock, so the
    # row the flush reads beyond it is a second current row at the start.
    held = _rectangle(_JAN, _JUN)
    inserted = _rectangle(_FEB, _DEC, tx_start=_T1)
    port = ScriptedAdapter(Transact(Read(rows=[held]), Read(rows=[inserted])))

    def fn(tx: Transaction) -> None:
        tx.update(_source(tx).edit(acct_num="B"), until=_SEP)
        _patch(tx, value="150.00")

    with raises_contextualized(CardinalityCorruptionError) as corrupt:
        _db(port).transact(fn, concurrency="locking")
    assert (corrupt.value.expected, corrupt.value.actual) == (1, 2)
    assert _writes(port) == []


def test_an_optimistic_observation_a_flush_read_row_overlaps_is_left_to_its_gate() -> None:
    # Under Optimistic the observation may be stale, so the row the flush reads
    # is no second current row beside it: the start's own gate decides.
    held = _rectangle(_JAN, _JUN)
    rewritten = _rectangle(_JAN, _DEC, tx_start=_T1)
    port = ScriptedAdapter(Transact(Read(rows=[held]), Read(rows=[rewritten]), Write(affected=0)))

    def fn(tx: Transaction) -> None:
        tx.update(_source(tx).edit(acct_num="B"), until=_SEP)
        _patch(tx, value="150.00")

    with raises_contextualized(WritePreconditionError):
        _db(port).transact(fn)
    (close,) = _writes(port)
    assert close.sql.endswith("and in_z = %s") and close.binds[-1] == _T0


def test_a_database_error_at_the_start_is_the_databases_not_the_callers() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]),
            Write(
                raises=DatabaseError(category="uniqueViolation", native_code="23505", message="dup")
            ),
        )
    )
    with raises_contextualized(DatabaseError):
        _db(port).transact(lambda tx: _patch(tx, value="150.00"))


def test_a_caught_temporal_precondition_failure_still_rolls_the_attempt_back() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_rectangle(_JAN, INFINITY_INSTANT, tx_start=_T1)])))

    def fn(tx: Transaction) -> str:
        _patch(tx, value="150.00")
        with pytest.raises(WritePreconditionError):
            tx.find(WherePosition.where(WherePosition.id == 2).as_of(valid_time=_MAR))
        return "withheld"

    with raises_contextualized(RollbackOnlyError):
        _db(port).transact(fn)
    assert RollbackCall() in port.calls
    assert _writes(port) == []


def test_a_temporal_target_of_a_subtype_writes_its_own_table_and_refuses_a_sibling_member() -> None:
    row = {
        "id": 4,
        "amount": Decimal("1.00"),
        "grade": "A",
        "from_z": _JAN,
        "thru_z": INFINITY_INSTANT,
        "in_z": _T0,
        "out_z": INFINITY_INSTANT,
    }
    port = ScriptedAdapter(Transact(Read(rows=[row]), Write(times=3)))

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteRejectedError):
            tx.wire.update(
                "DepositRate", {"id": 4, "spread": "1.00"}, valid_from=_MAR, if_tx_start=_T0
            )
        tx.wire.update("DepositRate", {"id": 4, "grade": "B"}, valid_from=_MAR, if_tx_start=_T0)

    db_for(RATE, port).transact(fn)
    (coverage,) = _reads(port)
    assert " from deposit_rate t0 " in coverage.sql
    assert all("deposit_rate" in call.sql for call in _writes(port))


@_STRATEGIES
def test_a_transaction_time_target_composes_with_an_observed_write_of_its_row(
    concurrency: _Concurrency,
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[balance_row(in_z=_T0)]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.update(source.edit(acct_num="B"))
        tx.wire.update("Balance", {"id": 1, "value": "150.00"}, if_tx_start=_T0)

    db_for(BALANCE, port).transact(fn, concurrency=concurrency)
    assert len(_reads(port)) == 1
    close, opened = _writes(port)
    assert close.binds[-1] == (_T0 if concurrency == "optimistic" else "infinity")
    assert opened.binds[:3] == (1, "B", Decimal("150.00"))


# --------------------------------------------------------------------------- #
# Disjoint operations and the ordering barriers between them.                  #
# --------------------------------------------------------------------------- #
class WhereTag(Entity, table="where_tag", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_BARRIERED = DomainModel(WherePosition, WhereTag)
_FEB_APR, _JUN_AUG = (_FEB, dt.datetime(2024, 4, 1, tzinfo=dt.UTC)), (_JUN, _AUG)
_APR = _FEB_APR[1]


def _window_patch(
    tx: Transaction, window: tuple[dt.datetime, dt.datetime], value: str, **stated: Any
) -> None:
    start, until = window
    tx.wire.update(
        "WherePosition",
        {"id": 1, "value": value},
        valid_from=start,
        until=until,
        if_tx_start=stated.get("tx_start", _T0),
    )


def _barriered(port: ScriptedAdapter) -> ScopedDatabase:
    return db_for(_BARRIERED, port)


def _barrier(tx: Transaction) -> None:
    tx.update_where(WhereTag.where(WhereTag.id == 1), WhereTag.label.set("q"))


def _owned(start: dt.datetime, value: str = "100.00", acct_num: str = "A") -> MappingRow:
    """A row an earlier execution unit of the same attempt opened."""
    return {**_rectangle(start, INFINITY_INSTANT, value, tx_start=FIXED), "acct_num": acct_num}


def _sql_kinds(port: ScriptedAdapter) -> list[str]:
    kinds: list[str] = []
    for call in _calls(port):
        if not isinstance(call, ReadCall | WriteCall):
            continue
        sql = call.sql
        if isinstance(call, ReadCall):
            kinds.append("read")
        elif sql.startswith("insert"):
            kinds.append("insert")
        elif sql.startswith("update where_tag"):
            kinds.append("barrier")
        elif " set out_z = " in sql:
            kinds.append("close")
        else:
            kinds.append("revise")
    return kinds


@_STRATEGIES
def test_disjoint_targets_of_one_rectangle_close_it_once_and_open_each_piece(
    concurrency: _Concurrency,
) -> None:
    whole = _rectangle(_JAN, INFINITY_INSTANT)
    acquisitions = [Read(rows=[whole], times=2)] if concurrency == "locking" else []
    port = ScriptedAdapter(Transact(*acquisitions, Read(rows=[whole]), Write(times=6)))

    def fn(tx: Transaction) -> None:
        _window_patch(tx, _FEB_APR, "150.00")
        _window_patch(tx, _JUN_AUG, "175.00")
        # Under Locking each start is read at its own call; neither call runs
        # the other's pending write.
        assert _writes(port) == []
        assert len(_reads(port)) == (2 if concurrency == "locking" else 0)

    _barriered(port).transact(fn, concurrency=concurrency)
    coverage = _reads(port)[-1]
    assert coverage.binds == (1, _FEB, _AUG, "infinity")
    close, *opened = _writes(port)
    if concurrency == "optimistic":
        assert close.binds[-1] == _T0
    assert [call.binds[2:5] for call in opened] == [
        (Decimal("100.00"), _JAN, _FEB),
        (Decimal("150.00"), _FEB, _APR),
        (Decimal("100.00"), _APR, _JUN),
        (Decimal("175.00"), _JUN, _AUG),
        (Decimal("100.00"), _AUG, INFINITY_INSTANT),
    ]


@_STRATEGIES
@pytest.mark.parametrize("first", ["target", "observed"])
def test_a_barrier_keeps_each_disjoint_operation_on_its_own_side(
    concurrency: _Concurrency, first: str
) -> None:
    whole = _rectangle(_JAN, INFINITY_INSTANT)
    # Before the flush: the observed source, or each Locking acquisition; then
    # the first unit's coverage unless its observation already holds it.
    reads = {
        ("target", "optimistic"): 1,
        ("target", "locking"): 3,
        ("observed", "optimistic"): 1,
        ("observed", "locking"): 2,
    }[first, concurrency]
    port = ScriptedAdapter(
        Transact(
            Read(rows=[whole], times=reads),
            Write(times=4),
            Write(),
            Read(rows=[_owned(_APR)]),
            Write(times=3),
        )
    )

    def fn(tx: Transaction) -> None:
        if first == "target":
            _window_patch(tx, _FEB_APR, "150.00")
        else:
            tx.update(_source(tx, _FEB).edit(value=Decimal("150.00")), until=_APR)
        _barrier(tx)
        _window_patch(tx, _JUN_AUG, "175.00")

    _barriered(port).transact(fn, concurrency=concurrency)
    assert _sql_kinds(port)[-9:] == [
        "close",
        "insert",
        "insert",
        "insert",
        "barrier",
        "read",
        "revise",
        "insert",
        "insert",
    ]
    later_read = _reads(port)[-1]
    assert later_read.binds == (1, _JUN, _AUG, "infinity")
    # The later operation's start now stands at a row the first unit derived
    # from the original the caller stated, which proves the caller's start:
    # its own row is revised in place, gated on nothing the caller stated.
    revision, *opened = _writes(port)[-3:]
    assert _T0 not in revision.binds
    assert [call.binds[2:5] for call in opened] == [
        (Decimal("100.00"), _APR, _JUN),
        (Decimal("175.00"), _JUN, _AUG),
    ]


def test_an_exact_window_write_after_a_barrier_carries_the_values_the_first_unit_left() -> None:
    whole = _rectangle(_JAN, INFINITY_INSTANT)
    middle = {**_rectangle(_FEB, _APR, "150.00", tx_start=FIXED)}
    port = ScriptedAdapter(
        Transact(
            Read(rows=[whole], times=2),
            Write(times=4),
            Write(),
            Read(rows=[middle]),
            Write(),
            Read(rows=[]),
        )
    )

    def fn(tx: Transaction) -> None:
        source = _source(tx, _FEB)
        _window_patch(tx, _FEB_APR, "150.00")
        _barrier(tx)
        tx.update(source.edit(acct_num="O"), until=_APR)
        tx.find(WherePosition.where(WherePosition.id == 2).as_of(valid_time=_MAR))
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.update(source.edit(acct_num="again"), until=_APR)

    _barriered(port).transact(fn)
    revision = _writes(port)[-1]
    # The observed write assigns its member over the row the first unit left,
    # whose other values are the target's, not the ones its source observed.
    assert revision.sql.startswith("update where_position set acct_num = %s where")
    assert revision.binds[0] == "O"
    assert Decimal("100.00") not in revision.binds


@_STRATEGIES
def test_a_proof_never_outlives_its_flush_so_a_later_call_restates_its_start(
    concurrency: _Concurrency,
) -> None:
    whole = _rectangle(_JAN, INFINITY_INSTANT)
    acquisition = [Read(rows=[whole])] if concurrency == "locking" else []
    later = [Read(rows=[_owned(_APR)])]
    port = ScriptedAdapter(
        Transact(*acquisition, Read(rows=[whole]), Write(times=4), Read(rows=[]), *later)
    )

    def fn(tx: Transaction) -> None:
        _window_patch(tx, _FEB_APR, "150.00")
        # A public read flushes the first write; the original the second
        # caller states is gone, and no proof survives that flush.
        tx.find(WherePosition.where(WherePosition.id == 2).as_of(valid_time=_MAR))
        _window_patch(tx, _JUN_AUG, "175.00")

    with raises_contextualized(WritePreconditionError) as failed:
        _barriered(port).transact(fn, concurrency=concurrency)
    assert failed.value.expected == _T0
    assert len(_writes(port)) == 4


def test_a_lost_first_unit_runs_nothing_after_it_and_a_lost_later_one_rolls_back() -> None:
    whole = _rectangle(_JAN, INFINITY_INSTANT)
    lost_first = ScriptedAdapter(Transact(Read(rows=[whole]), Write(affected=0)))

    def fn(tx: Transaction) -> None:
        _window_patch(tx, _FEB_APR, "150.00")
        _barrier(tx)
        _window_patch(tx, _JUN_AUG, "175.00")

    with raises_contextualized(WritePreconditionError):
        _barriered(lost_first).transact(fn, retry_optimistic_conflicts=True)
    assert _sql_kinds(lost_first) == ["read", "close"]
    lost_later = ScriptedAdapter(
        Transact(
            Read(rows=[whole]),
            Write(times=4),
            Write(),
            Read(rows=[_owned(_APR)]),
            Write(affected=0),
        )
    )
    with raises_contextualized(OptimisticLockConflictError):
        _barriered(lost_later).transact(fn)
    assert isinstance(lost_later.calls[-1], RollbackCall)


def test_a_chain_across_two_barriers_carries_the_original_through_the_middle_unit() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]),
            Write(times=4),
            Write(),
            Read(rows=[_owned(_APR)]),
            Write(times=3),
            Write(),
            # The middle unit revised the tail it read into [August, infinity).
            Read(rows=[_owned(_AUG)]),
            Write(times=3),
        )
    )

    def fn(tx: Transaction) -> None:
        _window_patch(tx, _FEB_APR, "150.00")
        _barrier(tx)
        _window_patch(tx, _JUN_AUG, "175.00")
        _barrier(tx)
        _window_patch(tx, (_SEP, _DEC), "200.00")

    _barriered(port).transact(fn)
    assert _sql_kinds(port)[-4:] == ["read", "revise", "insert", "insert"]
    *_earlier, revision, gap, last = _writes(port)
    assert _T0 not in revision.binds
    assert [call.binds[2:5] for call in (gap, last)] == [
        (Decimal("100.00"), _AUG, _SEP),
        (Decimal("200.00"), _SEP, _DEC),
    ]


def test_a_destruction_of_the_same_window_after_a_barrier_removes_what_the_first_opened() -> None:
    whole = _rectangle(_JAN, INFINITY_INSTANT)
    middle = _rectangle(_FEB, _APR, "150.00", tx_start=FIXED)
    port = ScriptedAdapter(
        Transact(
            Read(rows=[whole], times=2),
            Write(times=4),
            Write(),
            Read(rows=[middle]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        source = _source(tx, _FEB)
        _window_patch(tx, _FEB_APR, "150.00")
        _barrier(tx)
        tx.terminate(source, until=_APR)

    _barriered(port).transact(fn)
    removal = _writes(port)[-1]
    assert removal.sql.startswith("delete from where_position where id = %s and thru_z = %s")


def test_a_transaction_time_target_after_a_barrier_revises_the_row_the_first_opened() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[balance_row(in_z=_T0)]),
            Write(times=2),
            Write(),
            Read(rows=[{**balance_row(in_z=FIXED), "val": Decimal("150.00")}]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        tx.wire.update("Balance", {"id": 1, "value": "150.00"}, if_tx_start=_T0)
        _barrier(tx)
        tx.wire.update("Balance", {"id": 1, "acctNum": "B"}, if_tx_start=_T0)

    db_for(DomainModel(mm.Balance, WhereTag), port).transact(fn)
    revision = _writes(port)[-1]
    assert revision.sql.startswith("update balance set acct_num = %s where bal_id = %s")


def test_a_transaction_time_target_restating_the_row_the_first_opened_writes_nothing() -> None:
    owned = {**balance_row(in_z=FIXED), "val": Decimal("150.00")}
    port = ScriptedAdapter(
        Transact(Read(rows=[balance_row(in_z=_T0)]), Write(times=2), Write(), Read(rows=[owned]))
    )

    def fn(tx: Transaction) -> None:
        tx.wire.update("Balance", {"id": 1, "value": "150.00"}, if_tx_start=_T0)
        _barrier(tx)
        tx.wire.update("Balance", {"id": 1, "acctNum": owned["acct_num"]}, if_tx_start=_T0)

    db_for(DomainModel(mm.Balance, WhereTag), port).transact(fn)
    assert _sql_kinds(port) == ["read", "close", "insert", "barrier", "read"]
    assert isinstance(port.calls[-1], CommitCall)
