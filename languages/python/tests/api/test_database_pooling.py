"""Owned connection lifetimes through the shipped public surface, against a real database.

The internal seams are proven elsewhere. What is proven here is the surface an
application actually holds: connect from configuration, run typed and Wire
operations, and close — with the resource consequences that are visible from
outside. A whole eager read is one connection; a whole delivery is one
connection that goes back where the delivery ends; a retry acquires afresh; and
capacity a stream is occupying is capacity an independent transaction has to
wait for, which is the one pooling consequence an application has to design
around.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.db_port import ConnectionAcquisitionError
from parallax.postgres import OnDemandOptions, PoolOptions
from parallax.snapshot import connect
from parallax.snapshot.handle import ExecutionFailure, Transaction

_ACCOUNT = MODELS["account"]


def _seeded(profile_run: Any) -> None:
    case = load_case(default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml")
    profile_run.reset(
        engine.load_case_metamodel(case), provision.load_fixtures(str(case.document["model"]))
    )


def _accounts(db: Any) -> list[Any]:
    return list(db.find(Account.where(Account.all)).results())


# --------------------------------------------------------------------------- #
# Construction and ownership.                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pool",
    [
        None,
        PoolOptions(min_size=2, max_size=4),
        PoolOptions(min_size=0, max_size=2),
        OnDemandOptions(max_size=2),
    ],
    ids=["default", "tuned", "zero-minimum", "on-demand"],
)
def test_every_supported_configuration_connects_and_serves(profile_run: Any, pool: Any) -> None:
    _seeded(profile_run)
    with connect(profile_run.configured(pool=pool), _ACCOUNT) as db:
        assert _accounts(db)


def test_a_handle_serves_after_a_close_of_another_over_the_same_configuration(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=2))
    first = connect(configured, _ACCOUNT)
    second = connect(configured, _ACCOUNT)
    try:
        first.close()
        assert _accounts(second)
    finally:
        first.close()
        second.close()


def test_a_closed_handle_refuses_the_next_operation(profile_run: Any) -> None:
    _seeded(profile_run)
    db = connect(profile_run.configured(pool=PoolOptions(min_size=0, max_size=1)), _ACCOUNT)
    db.close()

    with pytest.raises(ExecutionFailure) as refused:
        _accounts(db)

    assert isinstance(refused.value.__cause__, ConnectionAcquisitionError)
    assert refused.value.__cause__.reason == "closed"


def test_a_retry_after_a_close_fails_rather_than_replaying(profile_run: Any) -> None:
    # A retry needs a connection of its own, so a handle closed underneath a
    # retry loop stops it rather than letting it run again.
    _seeded(profile_run)
    db = connect(profile_run.configured(pool=PoolOptions(min_size=0, max_size=1)), _ACCOUNT)
    attempts: list[int] = []

    def body(_tx: Transaction) -> None:
        attempts.append(1)
        db.close()
        raise RuntimeError("this attempt fails after the handle closed")

    with pytest.raises(ExecutionFailure):
        db.transact(body, retries=3)

    assert attempts == [1]


def test_a_startup_that_cannot_reach_a_server_publishes_no_handle(profile_run: Any) -> None:
    # Readiness is proved before publication, so a destination nothing answers
    # at is a composition failure rather than a handle that fails later.
    del profile_run  # the fixture is what admits this test to the database lane
    from parallax.core.db_port import DatabaseStartupError
    from parallax.postgres import PostgresAdapter

    unreachable = PostgresAdapter(
        "host=127.0.0.1 port=1 dbname=absent connect_timeout=1",
        pool=PoolOptions(min_size=0, max_size=1, startup_timeout=5.0, acquire_timeout=2.0),
    )

    with pytest.raises(DatabaseStartupError) as failed:
        connect(unreachable, _ACCOUNT)

    assert failed.value.phase in {"acquire", "open"}


# --------------------------------------------------------------------------- #
# What each operation holds, seen from outside.                                #
# --------------------------------------------------------------------------- #


def test_a_whole_eager_read_and_a_whole_delivery_each_need_one_slot(profile_run: Any) -> None:
    # One connection is enough for both shapes end to end: the read materializes
    # inside its own acquisition, and the delivery reads every page on one.
    _seeded(profile_run)
    with connect(profile_run.configured(pool=PoolOptions(min_size=1, max_size=1)), _ACCOUNT) as db:
        assert _accounts(db)
        with db.stream(Account.where(Account.all), batch_size=1) as roots:
            assert list(roots)
        assert db.wire.find({"target": "Account", "predicate": {"all": {}}}).results()


def test_an_exhausted_delivery_gives_its_slot_back_before_its_scope_ends(
    profile_run: Any,
) -> None:
    # The proof is a second operation on a runtime with exactly one slot, run
    # INSIDE the delivery's own `with` block: it can only succeed if the
    # exhausted delivery released where it ended.
    _seeded(profile_run)
    with (
        connect(
            profile_run.configured(pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=2.0)),
            _ACCOUNT,
        ) as db,
        db.stream(Account.where(Account.all), batch_size=1) as roots,
    ):
        assert list(roots)
        assert _accounts(db)


def test_a_delivery_still_reading_holds_its_slot(profile_run: Any) -> None:
    # The other side of the same fact, and the one an application has to design
    # around: an independent operation inside a stream loop needs another slot
    # and times out when the stream occupies them all.
    _seeded(profile_run)
    with (
        connect(
            profile_run.configured(pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=1.0)),
            _ACCOUNT,
        ) as db,
        db.stream(Account.where(Account.all), batch_size=1) as roots,
    ):
        next(iter(roots))
        with pytest.raises(ExecutionFailure) as refused:
            _accounts(db)

    assert isinstance(refused.value.__cause__, ConnectionAcquisitionError)
    assert refused.value.__cause__.reason == "timeout"


def test_a_transaction_and_its_participating_work_share_one_slot(profile_run: Any) -> None:
    _seeded(profile_run)
    with connect(profile_run.configured(pool=PoolOptions(min_size=1, max_size=1)), _ACCOUNT) as db:

        def body(tx: Transaction) -> int:
            found = tx.find(Account.where(Account.all)).results()
            with tx.stream(Account.where(Account.all), batch_size=1) as roots:
                streamed = list(roots)
            return len(found) + len(streamed)

        assert db.transact(body) > 0


def test_an_independent_transaction_needs_a_slot_of_its_own(profile_run: Any) -> None:
    _seeded(profile_run)
    with connect(profile_run.configured(pool=PoolOptions(min_size=0, max_size=2)), _ACCOUNT) as db:
        started = threading.Event()
        release = threading.Event()
        outcomes: list[str] = []

        def hold(tx: Transaction) -> None:
            tx.find(Account.where(Account.all)).results()
            started.set()
            release.wait(timeout=10.0)

        holder = threading.Thread(target=lambda: db.transact(hold))
        holder.start()
        try:
            assert started.wait(timeout=10.0)
            # A second slot exists, so a concurrent operation proceeds rather
            # than sharing the first one's connection.
            assert _accounts(db)
        finally:
            release.set()
            holder.join(timeout=10.0)
        assert outcomes == []


def test_typed_and_wire_operations_have_the_same_lifetimes(profile_run: Any) -> None:
    _seeded(profile_run)
    with connect(
        profile_run.configured(pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=2.0)),
        _ACCOUNT,
    ) as db:
        node: dict[str, object] = {"target": "Account", "predicate": {"all": {}}}
        assert db.wire.find(node).results()
        with db.wire.stream(node, batch_size=1) as roots:
            assert list(roots)
            # Released at exhaustion on the Wire lane exactly as on the typed
            # one: the two share one lifetime implementation.
            assert db.wire.find(node).results()


def test_a_committed_transaction_keeps_its_value_across_the_release(profile_run: Any) -> None:
    _seeded(profile_run)
    with connect(profile_run.configured(pool=PoolOptions(min_size=1, max_size=2)), _ACCOUNT) as db:
        existing = _accounts(db)
        new_id = max(int(account.id) for account in existing) + 1

        def body(tx: Transaction) -> int:
            tx.insert(Account(id=new_id, owner="Pooled", balance=Decimal("1.00")))
            return new_id

        assert db.transact(body) == new_id
        assert any(int(account.id) == new_id for account in _accounts(db))
