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

import asyncio
import threading
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import database_pooling_stories, engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.db_port import ConnectionAcquisitionError
from parallax.postgres import OnDemandOptions, PoolOptions
from parallax.snapshot import ServingModel, connect, prepare_model
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


# --------------------------------------------------------------------------- #
# Pool observation, through the shipped composition seam.                      #
# --------------------------------------------------------------------------- #


def test_a_provider_observes_the_pool_across_the_whole_life_of_a_handle(
    profile_run: Any,
) -> None:
    # The executable story, against the real pool it describes: registered
    # before the handle is published, read while a delivery is holding the only
    # slot, and detached once the handle closes.
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1))

    reading = (
        database_pooling_stories.the_pool_reports_its_own_capacity_and_stops_when_the_handle_closes(
            configured, _ACCOUNT
        )
    )

    assert reading.at_rest.managed == 1
    assert reading.at_rest.idle == 1
    # The delivery holds the runtime's one slot, and the reading still happens:
    # sampling takes no connection, so it could not have queued behind it.
    assert reading.while_working.idle == 0
    assert reading.while_working.checkouts > reading.at_rest.checkouts
    assert reading.while_working.waiting == 0
    assert reading.detached_after_close
    assert reading.registration_closed


def test_every_documented_retention_form_opens_against_a_real_server(profile_run: Any) -> None:
    # The guide's construction block builds four configurations over one
    # connection string. What a real server adds to the unit proof of their
    # policies is that each spelling opens a runtime that reads.
    _seeded(profile_run)
    conninfo = profile_run.configured().connection_string
    forms = database_pooling_stories.every_retention_form_is_one_configuration_value(conninfo)

    for adapter in (forms.default, forms.tuned, forms.zero_minimum, forms.on_demand):
        with connect(adapter, _ACCOUNT) as db:
            assert _accounts(db)


def test_both_model_forms_connect_and_both_closes_give_the_runtime_back(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=0, max_size=2))

    shape = database_pooling_stories.a_handle_is_closed_by_leaving_its_scope_or_by_closing_it(
        configured, _ACCOUNT, ServingModel(prepare_model(_ACCOUNT, edition="published"))
    )

    assert shape.scoped_rows > 0
    assert shape.explicit_rows == shape.scoped_rows


def test_one_configuration_serves_two_independent_handles(profile_run: Any) -> None:
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=2))

    shape = database_pooling_stories.one_configuration_opens_independent_runtimes(
        configured, _ACCOUNT
    )

    assert shape.first_rows > 0
    assert shape.second_rows_after_first_closed == shape.first_rows


# --------------------------------------------------------------------------- #
# The application lifespan and the offload boundary.                           #
# --------------------------------------------------------------------------- #


class _ThreadWitness:
    def __init__(self) -> None:
        self.threads: set[int] = set()
        self.transitions: list[str] = []

    def open(self, execution: Any, /) -> Any:
        del execution
        return self

    def report_handler_error(self, error: Any, /) -> None:
        raise AssertionError(f"no handler failure expected: {error.diagnostic.message}")

    def handle(self, event: Any, /) -> None:
        self.threads.add(threading.get_ident())
        self.transitions.append(type(event).__name__)


def test_the_lifespan_pattern_opens_one_handle_and_closes_it_at_shutdown(
    profile_run: Any,
) -> None:
    # The ASGI lifespan an application passes as `lifespan=`, without importing
    # one: an async context manager whose first half runs at startup and whose
    # second runs at shutdown. What is proven is the SHUTDOWN — the handle it
    # yielded is closed by the time the block is left, so the next operation
    # through it is refused rather than served by a runtime nobody closed.
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=2))
    escaped: list[Any] = []

    async def scenario() -> list[Decimal]:
        async with database_pooling_stories.pooled_database(configured, _ACCOUNT) as db:
            escaped.append(db)
            return await database_pooling_stories.serve_account_balances(db)

    balances = asyncio.run(scenario())

    assert balances
    with pytest.raises(ExecutionFailure) as refused:
        database_pooling_stories.account_balances(escaped[0])
    assert isinstance(refused.value.__cause__, ConnectionAcquisitionError)
    assert refused.value.__cause__.reason == "closed"


def test_a_complete_operation_offloaded_from_an_async_endpoint_never_touches_the_loop(
    profile_run: Any,
) -> None:
    # The boundary, not the offload. Every event of the operation — its
    # acquisition, its statements, its release — is delivered on the worker
    # thread, so the whole operation happened there and the loop thread was
    # never holding a connection. What comes back is plain values, which is
    # what makes that possible: a result still needing the database would have
    # dragged part of the operation back onto the loop.
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=2))
    witness = _ThreadWitness()

    async def scenario() -> tuple[int, list[Decimal]]:
        async with database_pooling_stories.pooled_database(
            configured, _ACCOUNT, lifecycle_provider=witness
        ) as db:
            balances = await database_pooling_stories.serve_account_balances(db)
            return threading.get_ident(), balances

    loop_thread, balances = asyncio.run(scenario())

    assert balances and all(isinstance(balance, Decimal) for balance in balances)
    assert witness.threads
    assert loop_thread not in witness.threads
    # A whole operation, not just its beginning: the read opened, acquired,
    # ran, released, and finished, all on the one worker thread.
    assert witness.transitions[0] == "ReadStarted"
    assert witness.transitions[1] == "AcquisitionStarted"
    assert witness.transitions[-2] == "ReleaseFinished"
    assert witness.transitions[-1] == "ReadFinished"
    assert len(witness.threads) == 1
