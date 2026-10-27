"""Overlapping temporal history refused by PostgreSQL storage, and retried.

A generated temporal table carries an exclusion that no two rows of one key
overlap on every axis at once (`m-storage-layout` *Temporal history
constraints*). A statement that violates the exclusion of the table it writes
is a recoverable conflict (`m-auto-retry`): the attempt rolls back and a new
attempt plans again at a fresh instant. Retried or not, the failure a caller
sees is the original ``DatabaseError(constraintViolation)``. Every other
database failure keeps its category's policy.

Each proof drives the public Typed and Wire verbs under both storage layouts
and both concurrency strategies and reads back every stored row. Every
``Database`` connects with a scripted clock, so every instant is known in
advance; a concurrent writer is a raw second session whose commit the test
orders.
"""

from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable, Sequence
from typing import Any, Final, Literal

import pytest

from parallax.conformance import concurrency_runner
from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, TxTemporal, attr, storage_layout
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import (
    AttemptCommitted,
    AttemptRolledBack,
    DatabaseCallFailed,
    DatabaseCallFinished,
    TransactionAttemptFinished,
)
from parallax.core.metamodel import Table
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root

_NAMESPACE: Final = "temporal.exclusion"


class ColumnsLog(TxTemporal, table="te_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class DocumentLog(TxTemporal, table="te_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class ColumnsSpan(Bitemporal, table="te_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


class DocumentSpan(Bitemporal, table="te_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


_MODEL: Final = DomainModel(ColumnsLog, DocumentLog, ColumnsSpan, DocumentSpan)
_TABLES: Final[dict[type[Any], str]] = {
    ColumnsLog: "te_columns_log",
    DocumentLog: "te_document_log",
    ColumnsSpan: "te_columns_span",
    DocumentSpan: "te_document_span",
}
_LOGS: Final = (ColumnsLog, DocumentLog)
_SPANS: Final = (ColumnsSpan, DocumentSpan)

_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL, _SEP, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3, 4, 5, 6, 7, 9, 12)
)

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]
type _Isolation = Literal["read_committed", "repeatable_read", "serializable"]

_REPRESENTATIONS: tuple[_Representation, ...] = ("typed", "wire")
_CONCURRENCIES: tuple[_Concurrency, ...] = ("optimistic", "locking")


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], name: str) -> str:
    return f"payload->>'{name}'" if entity in (DocumentLog, DocumentSpan) else name


def _exclusion(entity: type[Any]) -> str:
    layout = storage_layout.view(model_of(_MODEL)).table(Table(_TABLES[entity]))
    assert layout is not None and layout.temporal_constraints is not None
    return layout.temporal_constraints.exclusion_name


def _db(
    profile_run: Any,
    instants: Sequence[dt.datetime],
    provider: RecordingLifecycleProvider | None = None,
) -> ScopedDatabase:
    return own_root(
        connect(
            profile_run.port,
            _MODEL,
            clock=ScriptedClock(list(instants)),
            lifecycle_provider=provider,
        )
    ).using_database_login()


def _log_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_member(entity, 'label')} from {_TABLES[entity]} order by in_z, out_z"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _span_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        "case when thru_z = 'infinity' then null else thru_z end, "
        f"({_member(entity, 'amount')})::int from {_TABLES[entity]} order by in_z, out_z, from_z"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _overlaps(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    """Every pair of one key's rows overlapping on every axis at once."""
    valid = (
        " and tstzrange(a.from_z, a.thru_z) && tstzrange(b.from_z, b.thru_z)"
        if entity in _SPANS
        else ""
    )
    table = _TABLES[entity]
    sql = (
        f"select a.id from {table} a join {table} b on a.id = b.id and a.ctid < b.ctid "
        f"and tstzrange(a.in_z, a.out_z) && tstzrange(b.in_z, b.out_z){valid}"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _insert(
    tx: TxnContext,
    entity: type[Any],
    representation: _Representation,
    value: object,
    *,
    valid_from: dt.datetime = _JAN,
    until: dt.datetime | None = None,
) -> None:
    member = "label" if entity in _LOGS else "amount"
    window: dict[str, Any] = {}
    if entity in _SPANS:
        window["valid_from"] = valid_from
        if until is not None:
            window["until"] = until
    if representation == "typed":
        tx.insert(entity(id=1, **{member: value}), **window)
    else:
        tx.wire.insert(_name(entity), {"id": 1, member: value}, **window)


def _find(
    tx: TxnContext, entity: type[Any], representation: _Representation, at: dt.datetime = _JAN
) -> Any:
    if representation == "typed":
        query = entity.where(entity.id == 1)
        return tx.find(query if entity in _LOGS else query.as_of(valid_time=at)).result()
    name = _name(entity)
    temporal: dict[str, object] = {"transaction-time": {"asOf": "latest"}}
    if entity in _SPANS:
        temporal["valid-time"] = {"asOf": f"{at:%Y-%m-%dT%H:%M:%S.%fZ}"}
    return tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"path": f"{name}.id", "value": 1}},
            "temporal": temporal,
        }
    ).result()


def _terminate(tx: TxnContext, observed: Any, representation: _Representation) -> None:
    if representation == "typed":
        tx.terminate(observed)
    else:
        tx.wire.terminate(observed)


def _replace(
    tx: TxnContext, observed: Any, representation: _Representation, amount: int, until: dt.datetime
) -> None:
    if representation == "typed":
        tx.replace(observed.edit(amount=amount), until=until)
    else:
        tx.wire.replace(observed, {"id": 1, "amount": amount}, until=until)


def _refused(failure: pytest.ExceptionInfo[ExecutionFailure]) -> DatabaseError:
    cause = failure.value.cause
    assert isinstance(cause, DatabaseError)
    return cause


# --------------------------------------------------------------------------- #
# A reinsertion behind a terminated milestone is retried at a fresh instant.  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", (*_LOGS, *_SPANS))
def test_a_reinsertion_behind_a_terminated_milestone_is_retried_at_a_fresh_instant(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    # The object was known from January until its termination in May. A clock
    # at March would reopen it inside that history; the retry reopens it in June.
    profile_run.reset(model_of(_MODEL), {})
    seeded = _db(profile_run, [_JAN, _MAY])
    seeded.transact(lambda tx: _insert(tx, entity, "typed", "seeded" if entity in _LOGS else 100))
    seeded.transact(lambda tx: _terminate(tx, _find(tx, entity, "typed"), "typed"))
    provider = RecordingLifecycleProvider()
    attempts: list[None] = []

    def reopen(tx: TxnContext) -> None:
        attempts.append(None)
        _insert(tx, entity, representation, "again" if entity in _LOGS else 200)

    _db(profile_run, [_MAR, _JUN], provider).transact(reopen, concurrency=concurrency)

    assert len(attempts) == 2
    (refused, committed) = _attempts(provider)
    assert isinstance(refused.outcome, AttemptRolledBack)
    assert refused.outcome.failure.retry_eligible
    assert isinstance(committed.outcome, AttemptCommitted)
    if entity in _LOGS:
        assert _log_rows(profile_run, entity) == [(_JAN, _MAY, "seeded"), (_JUN, None, "again")]
    else:
        assert _span_rows(profile_run, entity) == [
            (_JAN, _MAY, _JAN, None, 100),
            (_JUN, None, _JAN, None, 200),
        ]


def _attempts(provider: RecordingLifecycleProvider) -> list[TransactionAttemptFinished]:
    return [
        event
        for root in provider.roots
        for event in root.events
        if isinstance(event, TransactionAttemptFinished)
    ]


# --------------------------------------------------------------------------- #
# A permanent overlap exhausts the bound and surfaces the original error.     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("retries", [0, 2])
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _SPANS)
def test_an_insert_partly_over_current_coverage_exhausts_its_bound_as_the_original_error(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
    retries: int,
) -> None:
    # [June, December) ends elsewhere than the stored [March, September), so
    # only the exclusion refuses it, and every attempt is refused again.
    profile_run.reset(model_of(_MODEL), {})
    _db(profile_run, [_JAN]).transact(
        lambda tx: _insert(tx, entity, "typed", 100, valid_from=_MAR, until=_SEP)
    )
    attempts: list[None] = []

    def overlap(tx: TxnContext) -> None:
        attempts.append(None)
        _insert(tx, entity, representation, 200, valid_from=_JUN, until=_DEC)

    with pytest.raises(ExecutionFailure) as failed:
        _db(profile_run, [_FEB, _MAR, _APR]).transact(
            overlap, concurrency=concurrency, max_retries=retries
        )

    assert len(attempts) == retries + 1
    error = _refused(failed)
    assert (error.category, error.native_code) == ("constraintViolation", "23P01")
    assert error.constraint_name == _exclusion(entity)
    assert not error.is_retriable
    assert error.__notes__ == [
        f"bounded retry exhausted after {retries + 1} attempts (retries={retries})"
    ]
    assert _span_rows(profile_run, entity) == [(_JAN, None, _MAR, _SEP, 100)]


# --------------------------------------------------------------------------- #
# Every other database failure keeps its category's policy.                    #
# --------------------------------------------------------------------------- #
def _attempted_once(
    profile_run: Any, entity: type[Any], work: Callable[[TxnContext], None]
) -> tuple[DatabaseError, int]:
    attempts: list[None] = []

    def counted(tx: TxnContext) -> None:
        attempts.append(None)
        work(tx)

    with pytest.raises(ExecutionFailure) as failed:
        _db(profile_run, [_FEB, _MAR, _APR]).transact(counted, max_retries=2)
    return _refused(failed), len(attempts)


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _LOGS)
def test_a_duplicate_current_insert_is_a_key_violation_never_retried(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    _db(profile_run, [_JAN]).transact(lambda tx: _insert(tx, entity, "typed", "seeded"))
    error, attempts = _attempted_once(
        profile_run, entity, lambda tx: _insert(tx, entity, representation, "again")
    )
    assert (error.category, error.native_code, attempts) == ("uniqueViolation", "23505", 1)
    assert not hasattr(error, "__notes__")
    assert _log_rows(profile_run, entity) == [(_JAN, None, "seeded")]


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _LOGS)
def test_a_check_violation_is_never_retried(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    control = profile_run.control()
    try:
        control.execute_write(
            f"alter table {_TABLES[entity]} add constraint te_label_check "
            f"check (({_member(entity, 'label')}) <> 'refused')",
            [],
        )
    finally:
        control.close()
    error, attempts = _attempted_once(
        profile_run, entity, lambda tx: _insert(tx, entity, representation, "refused")
    )
    assert (error.category, error.native_code, attempts) == ("constraintViolation", "23514", 1)
    assert error.constraint_name == "te_label_check"
    assert _log_rows(profile_run, entity) == []


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _LOGS)
def test_another_exclusions_violation_is_never_retried(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    # A second exclusion on the same table reports the same native kind under
    # a name the table's layout never compiled.
    profile_run.reset(model_of(_MODEL), {})
    control = profile_run.control()
    try:
        control.execute_write(
            f"alter table {_TABLES[entity]} add constraint te_one_current_label "
            f"exclude using gist (({_member(entity, 'label')}) with =, "
            "tstzrange(in_z, out_z) with &&)",
            [],
        )
        control.execute_write(
            f"insert into {_TABLES[entity]} (id, {_label_column(entity)}, in_z, out_z) "
            f"values (2, {_label_value(entity)}, '{_JAN.isoformat()}', 'infinity')",
            [],
        )
    finally:
        control.close()
    error, attempts = _attempted_once(
        profile_run, entity, lambda tx: _insert(tx, entity, representation, "shared")
    )
    assert (error.category, error.native_code, attempts) == ("constraintViolation", "23P01", 1)
    assert error.constraint_name == "te_one_current_label"


def _label_column(entity: type[Any]) -> str:
    return "payload" if entity is DocumentLog else "label"


def _label_value(entity: type[Any]) -> str:
    return """'{"label": "shared"}'""" if entity is DocumentLog else "'shared'"


# --------------------------------------------------------------------------- #
# A derived opening racing a concurrent insert is recovered.                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _SPANS)
def test_a_replacement_racing_an_insert_into_its_gap_is_retried_over_it(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    # The stored [January, March) leaves a gap the replacement through June
    # opens. A peer's uncommitted [April, May) is invisible to the replacement's
    # read, so its opening waits on the peer and is refused once the peer
    # commits; the retry reads the peer's row and replaces it too.
    profile_run.reset(model_of(_MODEL), {})
    _db(profile_run, [_JAN]).transact(
        lambda tx: _insert(tx, entity, "typed", 100, valid_from=_JAN, until=_MAR)
    )
    peer = profile_run.control(autocommit=False)
    observer = profile_run.control()
    attempts: list[None] = []
    finished: list[BaseException | None] = []

    def replace(tx: TxnContext) -> None:
        attempts.append(None)
        _replace(tx, _find(tx, entity, representation, at=_FEB), representation, 150, _JUN)

    db = _db(profile_run, [_MAR, _JUL])

    def run() -> None:
        try:
            db.transact(replace, concurrency=concurrency, isolation="read_committed")
        except BaseException as failure:  # re-raised on the test's thread below
            finished.append(failure)
        else:
            finished.append(None)

    try:
        peer.execute_write(_raw_span_insert(entity, 300, _APR, _MAY, _FEB), [])
        thread = threading.Thread(target=run)
        thread.start()
        waits = concurrency_runner.lock_waits_on(observer)
        _await(lambda: waits() > 0 or not thread.is_alive())
        peer.execute("commit", [])
        thread.join(timeout=30.0)
        assert not thread.is_alive()
    finally:
        peer.close()
        observer.close()
    (outcome,) = finished
    if outcome is not None:
        raise outcome
    assert len(attempts) == 2
    assert _overlaps(profile_run, entity) == []
    current = [row[2:] for row in _span_rows(profile_run, entity) if row[1] is None]
    assert sorted(current, key=lambda row: str(row[0])) == [
        (_JAN, _FEB, 100),
        (_FEB, _JUN, 150),
    ]


def _raw_span_insert(
    entity: type[Any], amount: int, valid_from: dt.datetime, until: dt.datetime, known: dt.datetime
) -> str:
    member, value = (
        ("payload", f"""'{{"amount": {amount}}}'""")
        if entity is DocumentSpan
        else ("amount", str(amount))
    )
    return (
        f"insert into {_TABLES[entity]} (id, {member}, from_z, thru_z, in_z, out_z) values "
        f"(1, {value}, '{valid_from.isoformat()}', '{until.isoformat()}', "
        f"'{known.isoformat()}', 'infinity')"
    )


def _await(ready: Callable[[], bool]) -> None:
    deadline = threading.Event()
    for _ in range(300):
        if ready():
            return
        deadline.wait(0.02)
    raise AssertionError("the concurrent writer never waited")


# --------------------------------------------------------------------------- #
# Two writers racing over one object's coverage.                               #
# --------------------------------------------------------------------------- #
type _Work = Callable[[TxnContext], None]


def _race(
    profile_run: Any,
    isolation: _Isolation,
    first: _Work,
    second: _Work,
) -> tuple[list[BaseException | None], list[tuple[str | None, str | None]]]:
    """Run ``first`` and ``second`` as two Databases' transactions whose first
    attempts both read before either writes, each retried under the default
    policy; answer each one's escaping failure, if any, and every database
    call failure either attempt met, as (category, native code)."""
    provider = RecordingLifecycleProvider()
    barrier = threading.Barrier(2, timeout=10.0)
    outcomes: list[BaseException | None] = [None, None]

    def run(index: int, work: _Work, db: ScopedDatabase) -> None:
        attempts: list[None] = []

        def attempt(tx: TxnContext) -> None:
            attempts.append(None)
            work(tx)
            if len(attempts) == 1:
                barrier.wait()

        try:
            db.transact(attempt, isolation=isolation, max_retries=3)
        except BaseException as failure:  # inspected on the test's thread
            outcomes[index] = failure

    instants = [_FEB, _MAR, _APR, _MAY]
    threads = [
        threading.Thread(target=run, args=(0, first, _db(profile_run, instants, provider))),
        threading.Thread(target=run, args=(1, second, _db(profile_run, instants, provider))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60.0)
        assert not thread.is_alive()
    failures = [
        (event.outcome.diagnostic.category, event.outcome.diagnostic.native_code)
        for root in provider.roots
        for event in root.events
        if isinstance(event, DatabaseCallFinished) and isinstance(event.outcome, DatabaseCallFailed)
    ]
    return outcomes, failures


_ALLOWED: Final = {"constraintViolation", "deadlock", "lockWaitTimeout"}
_RACE_ISOLATIONS: Final = pytest.mark.parametrize("isolation", ["read_committed", "serializable"])


def _settled(outcomes: list[BaseException | None], *, permanent: bool) -> None:
    """Each writer committed, or — where its write can never succeed — surfaced
    a refusal the retry policy explains."""
    for outcome in outcomes:
        if outcome is None:
            continue
        assert permanent, outcome
        assert isinstance(outcome, ExecutionFailure)
        cause = outcome.cause
        assert isinstance(cause, DatabaseError)
        assert cause.category in _ALLOWED, cause


def _two_ranges(profile_run: Any, *, split: bool = False) -> None:
    """Span 1 stored over [January, March) and [May, December), with [March,
    May) a gap; ``split`` stores the first range as [January, February) and
    [February, March)."""
    profile_run.reset(model_of(_MODEL), {})
    ranges = [(_JAN, _FEB), (_FEB, _MAR)] if split else [(_JAN, _MAR)]
    control = profile_run.control()
    try:
        for valid_from, until in (*ranges, (_MAY, _DEC)):
            control.execute_write(_raw_span_insert(ColumnsSpan, 100, valid_from, until, _JAN), [])
    finally:
        control.close()


def _span_find(tx: TxnContext, at: dt.datetime) -> Any:
    return tx.find(ColumnsSpan.where(ColumnsSpan.id == 1).as_of(valid_time=at)).result()


@_RACE_ISOLATIONS
def test_a_replacement_and_a_later_gap_insert_leave_legal_history(
    profile_run: Any, isolation: _Isolation
) -> None:
    _two_ranges(profile_run)
    outcomes, failures = _race(
        profile_run,
        isolation,
        lambda tx: tx.replace(_span_find(tx, _FEB).edit(amount=150), until=_JUN),
        lambda tx: tx.insert(ColumnsSpan(id=1, amount=300), valid_from=_MAR, until=_APR),
    )
    _settled(outcomes, permanent=True)
    assert outcomes[0] is None
    assert {category for category, _ in failures} <= _ALLOWED
    assert _overlaps(profile_run, ColumnsSpan) == []


@_RACE_ISOLATIONS
def test_two_replacements_from_different_rows_leave_legal_history(
    profile_run: Any, isolation: _Isolation
) -> None:
    # Each replacement starts in its own stored range and fills the same gap.
    _two_ranges(profile_run, split=True)
    outcomes, failures = _race(
        profile_run,
        isolation,
        lambda tx: tx.replace(_span_find(tx, _JAN).edit(amount=150), until=_APR),
        lambda tx: tx.replace(_span_find(tx, _FEB).edit(amount=250), until=_APR),
    )
    _settled(outcomes, permanent=False)
    assert {category for category, _ in failures} <= _ALLOWED
    assert _overlaps(profile_run, ColumnsSpan) == []


@_RACE_ISOLATIONS
@pytest.mark.parametrize(
    ("second_from", "second_until", "overlapping"),
    [(_MAR, _SEP, True), (_JUN, _SEP, False)],
    ids=["overlapping", "adjacent"],
)
def test_two_first_inserts_overlap_only_when_their_windows_do(
    profile_run: Any,
    isolation: _Isolation,
    second_from: dt.datetime,
    second_until: dt.datetime,
    overlapping: bool,
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    outcomes, failures = _race(
        profile_run,
        isolation,
        lambda tx: tx.insert(ColumnsSpan(id=1, amount=100), valid_from=_JAN, until=_JUN),
        lambda tx: tx.insert(
            ColumnsSpan(id=1, amount=200), valid_from=second_from, until=second_until
        ),
    )
    _settled(outcomes, permanent=overlapping)
    assert {category for category, _ in failures} <= _ALLOWED
    if overlapping:
        assert sum(outcome is None for outcome in outcomes) == 1
    else:
        assert outcomes == [None, None]
        assert failures == []
    assert _overlaps(profile_run, ColumnsSpan) == []


@_RACE_ISOLATIONS
def test_a_sparse_patch_and_a_gap_insert_leave_legal_history(
    profile_run: Any, isolation: _Isolation
) -> None:
    _two_ranges(profile_run)
    outcomes, failures = _race(
        profile_run,
        isolation,
        lambda tx: tx.amend(_span_find(tx, _FEB).edit(amount=150), until=_JUN),
        lambda tx: tx.insert(ColumnsSpan(id=1, amount=300), valid_from=_MAR, until=_MAY),
    )
    _settled(outcomes, permanent=False)
    assert {category for category, _ in failures} <= _ALLOWED
    assert _overlaps(profile_run, ColumnsSpan) == []


@_RACE_ISOLATIONS
def test_a_range_termination_and_a_gap_insert_leave_legal_history(
    profile_run: Any, isolation: _Isolation
) -> None:
    _two_ranges(profile_run)
    outcomes, failures = _race(
        profile_run,
        isolation,
        lambda tx: tx.terminate(_span_find(tx, _FEB)),
        lambda tx: tx.insert(ColumnsSpan(id=1, amount=300), valid_from=_MAR, until=_MAY),
    )
    _settled(outcomes, permanent=False)
    assert {category for category, _ in failures} <= _ALLOWED
    assert _overlaps(profile_run, ColumnsSpan) == []


def test_repeatable_read_gives_a_sparse_patch_no_concurrently_inserted_coverage(
    profile_run: Any,
) -> None:
    # The patch's snapshot predates the gap insert, so it neither reaches the
    # new rectangle nor is refused by it: membership stays snapshot-relative.
    _two_ranges(profile_run)
    outcomes, failures = _race(
        profile_run,
        "repeatable_read",
        lambda tx: tx.amend(_span_find(tx, _FEB).edit(amount=150), until=_JUN),
        lambda tx: tx.insert(ColumnsSpan(id=1, amount=300), valid_from=_MAR, until=_MAY),
    )
    assert outcomes == [None, None]
    assert failures == []
    current = [row[2:] for row in _span_rows(profile_run, ColumnsSpan) if row[1] is None]
    assert (_MAR, _MAY, 300) in current
    assert _overlaps(profile_run, ColumnsSpan) == []
