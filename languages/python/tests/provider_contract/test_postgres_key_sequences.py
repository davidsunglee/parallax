"""Native key reservations against a real server: the shipped adapter's lazy
reservation capacity, the login it reserves under, the live sequence definition
every reservation checks, concurrent roots and threads drawing disjoint keys, and
the one budget that bounds a reservation stalled on the sequence's lock."""

from __future__ import annotations

import threading
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Final

import pytest

from parallax.core import (
    Attr,
    ConnectionAcquisitionError,
    DatabaseError,
    DomainModel,
    Entity,
    KeySequence,
    UsageError,
    attr,
)
from parallax.core.internal.db_port import PoolAvailable, PoolMetricsSource
from parallax.core.internal.entity._model import model_of
from parallax.postgres import PoolOptions, PostgresBinding, PostgresLocation, PostgresSequence
from parallax.snapshot import TxnContext, connect
from tests._support.bindings import TEST_BINDING, TEST_SCHEMA
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root


class Voucher(Entity, table="pks_voucher", namespace="key.sequences"):
    id: Attr[int] = attr(primary_key=KeySequence("pks_voucher_ids", batch_size=5))
    label: Attr[str] = attr(max_length=16)


class Token(Entity, table="pks_token", namespace="key.sequences"):
    id: Attr[int] = attr(primary_key=KeySequence("pks_token_ids", batch_size=1))
    label: Attr[str] = attr(max_length=16)


_MODEL: Final = DomainModel(Voucher, Token)
_SEQUENCE: Final = f"{TEST_SCHEMA}.pks_voucher_ids"


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def _keyless(label: str) -> Any:
    def insert(tx: TxnContext) -> object:
        return tx.insert(Voucher(label=label)).id

    return insert


def _sequence_state(profile_run: Any, sequence: str = _SEQUENCE) -> tuple[object, ...]:
    with closing(profile_run.control()) as control:
        ((last, called),) = control.execute(f"select last_value, is_called from {sequence}", [])
    return (last, called)


def _stored(profile_run: Any) -> list[tuple[object, ...]]:
    with closing(profile_run.control()) as control:
        return [
            tuple(row)
            for row in control.execute(
                f"select id, label from {TEST_SCHEMA}.pks_voucher order by id", []
            )
        ]


def test_a_principal_without_sequence_privilege_inserts_through_the_login_s_reservation(
    profile_run: Any,
) -> None:
    # Provisioning grants the conformance roles their tables and the login's own
    # role alone the sequence, as a deployment's application roles hold no
    # privilege on the sequence its service login reserves from.
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    role = profile_run.authorization("role-a")
    with closing(profile_run.control()) as control:
        ((allowed,),) = control.execute(
            "select has_sequence_privilege(?, ?, 'USAGE')", [role.name, _SEQUENCE]
        )
    assert allowed is False
    root = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING))
    db = root.using_principal(_Principal("key-sequences", role))

    assert db.transact(_keyless("first")) == 1
    assert _stored(profile_run) == [(1, "first")]


def test_a_root_whose_only_application_connection_is_held_still_reserves(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    configuration = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1))
    root = own_root(connect(configuration, _MODEL, binding=TEST_BINDING))
    db = root.using_database_login()

    def insert(tx: TxnContext) -> list[int]:
        return [tx.insert(Voucher(label=f"v{index}")).id for index in range(6)]

    assert db.transact(insert) == [1, 2, 3, 4, 5, 6]
    assert _sequence_state(profile_run) == (6, True)


def test_a_root_reserves_nothing_until_a_keyless_insert_and_then_hands_out_locally(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    root = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING))
    db = root.using_database_login()
    db.transact(lambda tx: tx.insert(Voucher(id=100, label="given")))
    assert _sequence_state(profile_run) == (1, False)

    assert [db.transact(_keyless(f"v{index}")) for index in range(5)] == [1, 2, 3, 4, 5]
    # One block of five served all five transactions.
    assert _sequence_state(profile_run) == (1, True)
    assert db.transact(_keyless("next")) == 6
    assert _sequence_state(profile_run) == (6, True)


def test_a_closed_root_refuses_new_work_though_it_still_held_reserved_keys(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    root = connect(profile_run.port, _MODEL, binding=TEST_BINDING)
    db = root.using_database_login()
    assert db.transact(_keyless("first")) == 1
    root.close()

    with pytest.raises(ConnectionAcquisitionError) as refused:
        db.transact(_keyless("after"))
    assert refused.value.reason == "closed"
    # A replacement root abandons what the closed one reserved and never reused.
    replacement = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING))
    assert replacement.using_database_login().transact(_keyless("replaced")) == 6


def test_a_reservation_finding_no_sequence_is_refused_and_keeps_nothing(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    with closing(profile_run.control()) as control:
        control.execute_write(f"drop sequence {_SEQUENCE}", [])
    db = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING)).using_database_login()

    with raises_code(UsageError, "key-sequence-missing"):
        db.transact(_keyless("missing"))
    assert _stored(profile_run) == []


def test_a_sequence_the_server_reports_exhausted_is_refused_and_stores_nothing(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    with closing(profile_run.control()) as control:
        control.execute_write(f"alter sequence {_SEQUENCE} maxvalue 1", [])
        control.execute(f"select nextval('{_SEQUENCE}')", [])
    db = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING)).using_database_login()

    with raises_code(UsageError, "key-sequence-exhausted"):
        db.transact(_keyless("exhausted"))
    assert _stored(profile_run) == []


@pytest.mark.parametrize(
    ("alteration", "detail"),
    [
        ("increment by 7", "steps by 7"),
        ("cycle", "cycles"),
    ],
    ids=["increment", "cycling"],
)
def test_a_reservation_under_an_altered_definition_is_refused_and_abandoned(
    profile_run: Any, alteration: str, detail: str
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    with closing(profile_run.control()) as control:
        control.execute_write(f"alter sequence {_SEQUENCE} {alteration}", [])
    db = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING)).using_database_login()

    with raises_code(UsageError, "key-sequence-mismatch", match=detail):
        db.transact(_keyless("altered"))
    assert _stored(profile_run) == []


_QUALIFIED: Final = PostgresBinding(
    default=PostgresLocation(TEST_SCHEMA),
    sequences={"pks_voucher_ids": PostgresSequence(schema="Key.Ring", name="voucher.ids")},
)


def test_a_misleading_search_path_redirects_neither_ddl_nor_reservation(
    profile_run: Any,
) -> None:
    # The sequence's schema and name each hold a dot and capitals, so only a
    # name quoted component by component reaches it; a same-named decoy first
    # on the search path catches anything resolved without qualification.
    profile_run.reset(model_of(_MODEL), {}, _QUALIFIED)
    role = profile_run.default_role.name
    with closing(profile_run.control()) as control:
        control.execute_write('create sequence public."voucher.ids" increment by 5', [])
        control.execute_write(f'grant usage on sequence public."voucher.ids" to "{role}"', [])
    configuration = profile_run.configured(settings={"search_path": "public"})
    db = own_root(connect(configuration, _MODEL, binding=_QUALIFIED)).using_database_login()

    assert db.transact(_keyless("qualified")) == 1
    assert _sequence_state(profile_run, '"Key.Ring"."voucher.ids"') == (1, True)
    assert _sequence_state(profile_run, 'public."voucher.ids"') == (1, False)


# --------------------------------------------------------------------------- #
# Concurrent reservations: disjoint blocks across roots, one block shared by   #
# a root's threads, and one connection shared by a root's sequences.           #
# --------------------------------------------------------------------------- #


def _in_parallel(workers: list[Any]) -> list[Any]:
    """Run each worker on its own thread, all released together, answering
    their results in worker order and re-raising the first failure."""
    start = threading.Barrier(len(workers))
    results: list[Any] = [None] * len(workers)
    failures: list[BaseException] = []

    def run(index: int) -> None:
        try:
            start.wait(10)
            results[index] = workers[index]()
        except BaseException as failure:
            failures.append(failure)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(len(workers))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    if failures:
        raise failures[0]
    return results


def _blocks(keys: list[int], batch_size: int = 5) -> set[int]:
    return {(key - 1) // batch_size for key in keys}


def test_concurrent_roots_reserve_disjoint_blocks_of_one_sequence(profile_run: Any) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    roots = [own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING)) for _ in range(3)]

    def worker(db: Any) -> Any:
        def run() -> list[int]:
            return [db.transact(_keyless(f"v{index}")) for index in range(7)]

        return run

    taken = _in_parallel([worker(root.using_database_login()) for root in roots])

    every = [key for keys in taken for key in keys]
    assert len(set(every)) == len(every) == 21
    # Each block of five belongs to the one root that reserved it.
    for index, keys in enumerate(taken):
        others = {key for other, held in enumerate(taken) if other != index for key in held}
        assert not _blocks(keys) & _blocks(sorted(others))
    # Seven keys per root is two blocks each: six reservations in all.
    assert _sequence_state(profile_run) == (26, True)


def test_a_root_s_threads_hand_out_one_block_before_reserving_another(profile_run: Any) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    configuration = profile_run.configured(pool=PoolOptions(min_size=1, max_size=4))
    db = own_root(connect(configuration, _MODEL, binding=TEST_BINDING)).using_database_login()

    def worker() -> list[int]:
        return [db.transact(_keyless("threaded")) for _ in range(5)]

    taken = _in_parallel([worker for _ in range(4)])

    assert sorted(key for keys in taken for key in keys) == list(range(1, 21))
    # Twenty keys from blocks of five: four reservations and no more.
    assert _sequence_state(profile_run) == (16, True)


class _PoolSources:
    """A lifecycle Provider keeping every pool source a root publishes."""

    def __init__(self) -> None:
        self.sources: list[PoolMetricsSource] = []

    def open(self, execution: object, /) -> None:
        return None

    def report_handler_error(self, error: object, /) -> None:
        raise AssertionError(f"lifecycle handler failed: {error!r}")

    def observe_pool(self, source: PoolMetricsSource, /) -> Any:
        self.sources.append(source)
        return closing(self)

    def close(self) -> None:
        return None

    def reservation(self) -> Any:
        (source,) = [source for source in self.sources if source.purpose == "reservation"]
        sample = source.sample()
        assert isinstance(sample, PoolAvailable)
        return sample.measurements


def test_a_root_s_sequences_reserve_through_its_one_reservation_connection(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    pools = _PoolSources()
    configuration = profile_run.configured(pool=PoolOptions(min_size=1, max_size=4))
    root = own_root(connect(configuration, _MODEL, binding=TEST_BINDING, lifecycle_provider=pools))
    db = root.using_database_login()

    def tokens() -> list[int]:
        return [db.transact(lambda tx: tx.insert(Token(label="t")).id) for _ in range(5)]

    def vouchers() -> list[int]:
        return [db.transact(_keyless("v")) for _ in range(5)]

    first, voucher_keys, second = _in_parallel([tokens, vouchers, tokens])

    assert sorted(first + second) == list(range(1, 11))
    assert voucher_keys == [1, 2, 3, 4, 5]
    # Ten single-key blocks and one block of five, all on one connection.
    measured = pools.reservation()
    assert measured.requests_num == 11
    assert measured.connections_num == 1


# --------------------------------------------------------------------------- #
# A reservation's one budget bounds a wait on the sequence's lock.             #
# --------------------------------------------------------------------------- #


def test_a_reservation_waiting_on_a_held_sequence_lock_fails_within_its_budget(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    configuration = profile_run.configured(acquire_timeout=1.0)
    db = own_root(connect(configuration, _MODEL, binding=TEST_BINDING)).using_database_login()
    with closing(profile_run.control(autocommit=False)) as holder:
        # An uncommitted alteration holds the lock every nextval must take.
        holder.execute_write(f"alter sequence {_SEQUENCE} increment by 5", [])
        started = time.monotonic()
        with pytest.raises(DatabaseError) as stalled:
            db.transact(_keyless("stalled"))
        waited = time.monotonic() - started
        holder.rollback()

    assert stalled.value.native_code == "57014"
    assert 0.5 < waited < 5.0
    # Nothing was reserved, so the next reservation takes the sequence's first block.
    assert db.transact(_keyless("after")) == 1
    assert _stored(profile_run) == [(1, "after")]


def test_a_definition_altered_under_a_root_is_refused_at_its_next_refill(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    db = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING)).using_database_login()
    assert db.transact(_keyless("first")) == 1
    with closing(profile_run.control()) as control:
        control.execute_write(f"alter sequence {_SEQUENCE} increment by 7", [])

    # The block already held stays the root's; the refill after it is checked.
    assert [db.transact(_keyless(f"local{index}")) for index in range(4)] == [2, 3, 4, 5]
    with raises_code(UsageError, "key-sequence-mismatch", match="steps by 7"):
        db.transact(_keyless("refused"))
    assert [row[0] for row in _stored(profile_run)] == [1, 2, 3, 4, 5]
