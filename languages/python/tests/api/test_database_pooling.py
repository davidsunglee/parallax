"""Owned connection lifetimes through the shipped public surface, against a real database.

The internal seams are proven elsewhere. What is proven here is the surface an
application actually holds: connect from configuration, run typed and Wire
operations, and close — with the resource consequences that are visible from
outside. A whole eager read is one connection; each standalone delivery page is
one lease returned before publication; a retry acquires afresh; and
participating work uses its attempt's connection.
"""

from __future__ import annotations

import asyncio
import operator
import threading
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

import parallax.postgres._connection as connection_module
from parallax.conformance import database_pooling_stories, engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Document,
    DomainModel,
    Entity,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import ConnectionAcquisitionError
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.execution import (
    ExecutionFailure,
    ServingModel,
    prepare_model,
)
from parallax.core.read_delivery._read_plan import ReadPlanCache
from parallax.core.sql_gen._compile import CompiledTemplate
from parallax.postgres import OnDemandOptions, PoolOptions
from parallax.snapshot import TxnContext, connect
from tests._support.ended_sessions import end_backend, named_backend
from tests._support.query_probes import canonical_document

_ACCOUNT = MODELS["account"]


def _seeded(profile_run: Any) -> None:
    case = load_case(default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml")
    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
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
    with connect(profile_run.configured(pool=pool), _ACCOUNT) as _root_db:
        db = _root_db.using_database_login()
        assert _accounts(db)


def test_a_handle_serves_after_a_close_of_another_over_the_same_configuration(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=2))
    first_root = connect(configured, _ACCOUNT)
    second_root = connect(configured, _ACCOUNT)
    second = second_root.using_database_login()
    try:
        first_root.close()
        assert _accounts(second)
    finally:
        first_root.close()
        second_root.close()


def test_a_closed_handle_refuses_the_next_operation(profile_run: Any) -> None:
    _seeded(profile_run)
    root = connect(profile_run.configured(pool=PoolOptions(min_size=0, max_size=1)), _ACCOUNT)
    db = root.using_database_login()
    root.close()

    with pytest.raises(ExecutionFailure) as refused:
        _accounts(db)

    assert isinstance(refused.value.__cause__, ConnectionAcquisitionError)
    assert refused.value.__cause__.reason == "closed"


def test_a_retry_after_a_close_fails_rather_than_replaying(profile_run: Any) -> None:
    # A retry needs a connection of its own, so a handle closed underneath a
    # retry loop stops it rather than letting it run again.
    _seeded(profile_run)
    root = connect(profile_run.configured(pool=PoolOptions(min_size=0, max_size=1)), _ACCOUNT)
    db = root.using_database_login()
    attempts: list[int] = []

    def body(_tx: TxnContext) -> None:
        attempts.append(1)
        root.close()
        raise RuntimeError("this attempt fails after the handle closed")

    with pytest.raises(ExecutionFailure):
        db.transact(body, max_retries=3)

    assert attempts == [1]


def test_a_startup_that_cannot_reach_a_server_publishes_no_handle(profile_run: Any) -> None:
    # Readiness is proved before publication, so a destination nothing answers
    # at is a composition failure rather than a handle that fails later.
    del profile_run  # the fixture is what admits this test to the database lane
    from parallax.core.db_port import DRIVER_MANAGED, DatabaseStartupError
    from parallax.postgres import PostgresAdapter

    unreachable = PostgresAdapter(
        "host=127.0.0.1 port=1 dbname=absent connect_timeout=1",
        credentials=DRIVER_MANAGED,
        pool=PoolOptions(min_size=0, max_size=1, startup_timeout=5.0, acquire_timeout=2.0),
    )

    with pytest.raises(DatabaseStartupError) as failed:
        connect(unreachable, _ACCOUNT)

    assert failed.value.phase in {"acquire", "open"}


# --------------------------------------------------------------------------- #
# What each operation holds, seen from outside.                                #
# --------------------------------------------------------------------------- #


def test_a_whole_eager_read_and_each_delivery_page_need_one_slot(profile_run: Any) -> None:
    # One connection is enough for both shapes: the eager read materializes
    # inside its acquisition, and each delivery page returns its lease in turn.
    _seeded(profile_run)
    with connect(
        profile_run.configured(pool=PoolOptions(min_size=1, max_size=1)), _ACCOUNT
    ) as _root_db:
        db = _root_db.using_database_login()
        assert _accounts(db)
        with db.stream(Account.where(Account.all), batch_size=1) as roots:
            assert list(roots)
        assert db.wire.find({"target": "Account", "predicate": {"true": {}}}).results()


def test_an_exhausted_delivery_gives_its_slot_back_before_its_scope_ends(
    profile_run: Any,
) -> None:
    # The proof is a second operation on a runtime with exactly one slot, run
    # INSIDE the delivery's own `with` block: it can only succeed if the
    # exhausted delivery released where it ended.
    _seeded(profile_run)
    with connect(
        profile_run.configured(pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=2.0)),
        _ACCOUNT,
    ) as _root_db:
        db = _root_db.using_database_login()
        with db.stream(Account.where(Account.all), batch_size=1) as roots:
            assert list(roots)
            assert _accounts(db)


def test_an_independent_read_uses_the_only_slot_between_delivery_pages(profile_run: Any) -> None:
    # Publication happens after the page lease returns, so independent work in
    # the consuming loop can use the only slot before the next page asks for it.
    _seeded(profile_run)
    with connect(
        profile_run.configured(pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=1.0)),
        _ACCOUNT,
    ) as _root_db:
        db = _root_db.using_database_login()
        with db.stream(Account.where(Account.all), batch_size=1) as roots:
            next(iter(roots))
            assert _accounts(db)


def test_a_transaction_and_its_participating_work_share_one_slot(profile_run: Any) -> None:
    _seeded(profile_run)
    with connect(
        profile_run.configured(pool=PoolOptions(min_size=1, max_size=1)), _ACCOUNT
    ) as _root_db:
        db = _root_db.using_database_login()

        def body(tx: TxnContext) -> int:
            found = tx.find(Account.where(Account.all)).results()
            with tx.stream(Account.where(Account.all), batch_size=1) as roots:
                streamed = list(roots)
            return len(found) + len(streamed)

        assert db.transact(body) > 0


def test_an_independent_transaction_needs_a_slot_of_its_own(profile_run: Any) -> None:
    _seeded(profile_run)
    with connect(
        profile_run.configured(pool=PoolOptions(min_size=0, max_size=2)), _ACCOUNT
    ) as _root_db:
        db = _root_db.using_database_login()
        started = threading.Event()
        release = threading.Event()
        outcomes: list[str] = []

        def hold(tx: TxnContext) -> None:
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
    ) as _root_db:
        db = _root_db.using_database_login()
        node: dict[str, object] = {"target": "Account", "predicate": {"true": {}}}
        assert db.wire.find(node).results()
        with db.wire.stream(node, batch_size=1) as roots:
            assert list(roots)
            # Released at exhaustion on the Wire lane exactly as on the typed
            # one: the two share one lifetime implementation.
            assert db.wire.find(node).results()


def test_a_committed_transaction_keeps_its_value_across_the_release(profile_run: Any) -> None:
    _seeded(profile_run)
    with connect(
        profile_run.configured(pool=PoolOptions(min_size=1, max_size=2)), _ACCOUNT
    ) as _root_db:
        db = _root_db.using_database_login()
        existing = _accounts(db)
        new_id = max(int(account.id) for account in existing) + 1

        def body(tx: TxnContext) -> int:
            tx.insert(Account(id=new_id, owner="Pooled", balance=Decimal("1.00")))
            return new_id

        assert db.transact(body) == new_id
        assert any(int(account.id) == new_id for account in _accounts(db))


# --------------------------------------------------------------------------- #
# A connection the server ended while idle, replaced at its first use.         #
# --------------------------------------------------------------------------- #

_FIRST_USE = "first.use"


class Memo(ValueObject):
    text: Attr[str]


class Ledger(Entity, table="fu_ledger", namespace=_FIRST_USE):
    id: Attr[int] = attr(primary_key=True)
    memo: Attr[Memo]
    entries: Rel[tuple[Entry, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "ledger"))
    holds: Rel[tuple[Hold, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "ledger"))


class Entry(Entity, table="fu_entry", namespace=_FIRST_USE):
    id: Attr[int] = attr(primary_key=True)
    ledger: Attr[int]
    amount: Attr[int]


class Hold(Entity, table="fu_hold", namespace=_FIRST_USE):
    id: Attr[int] = attr(primary_key=True)
    ledger: Attr[int]
    reason: Attr[str]


class Folio(Entity, table="fu_folio", namespace=_FIRST_USE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]


_FIRST_USE_MODEL = DomainModel(Ledger, Entry, Hold, Folio)

# Membership over the root and two sibling includes: the root read submits one
# array carrier, and its children are fetched together in one read pipeline,
# each with the child-key array the root gathered.
_LAYOUT_QUERIES: dict[str, Any] = {
    "columns": Ledger.where(Ledger.id.in_([1, 2]))
    .include(Ledger.entries, Ledger.holds)
    .order_by(Ledger.id.asc()),
    "documents": Folio.where(Folio.id.in_([1, 2])).order_by(Folio.id.asc()),
}


def _drained(stream: Any) -> list[Any]:
    with stream as opened:
        return list(opened)


_READERS: dict[str, Callable[[Any, Any], list[Any]]] = {
    "typed-eager": lambda db, query: list(db.find(query).results()),
    "typed-stream": lambda db, query: _drained(db.stream(query, batch_size=10)),
    "wire-eager": lambda db, query: list(
        db.wire.find(canonical_document(query, _FIRST_USE_MODEL)).results()
    ),
    "wire-stream": lambda db, query: _drained(
        db.wire.stream(canonical_document(query, _FIRST_USE_MODEL), batch_size=10)
    ),
}


class _Heard:
    """A lifecycle provider recording each event it hears by kind."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def open(self, execution: Any, /) -> Any:
        del execution
        return self

    def report_handler_error(self, error: Any, /) -> None:
        raise AssertionError(f"no handler failure expected: {error.diagnostic.message}")

    def handle(self, event: Any, /) -> None:
        self.events.append(type(event).__name__)

    def heard(self) -> list[str]:
        heard, self.events = self.events, []
        return heard


type _Submission = tuple[object, tuple[bytes, ...], tuple[list[object], ...]]
"""The connection a native submission reached, its SQL, and its bind objects."""


@dataclass
class _Preparation:
    """What the read path did before and at the port, counted from outside it."""

    counts: Counter[str] = field(default_factory=Counter[str])
    submissions: list[_Submission] = field(default_factory=list[_Submission])

    def taken(self) -> tuple[Counter[str], list[_Submission]]:
        taken = (self.counts, self.submissions)
        self.counts, self.submissions = Counter[str](), []
        return taken


def _observed_preparation(monkeypatch: pytest.MonkeyPatch) -> _Preparation:
    """Count planning, rendering, driver-SQL conversion and bind adaptation, and
    record every native submission: which connection it reached, its SQL, and
    the very bind objects it handed the driver."""
    preparation = _Preparation()

    def counted(owner: Any, name: str, key: str) -> None:
        original = getattr(owner, name)

        def spied(*args: Any, **kwargs: Any) -> Any:
            preparation.counts[key] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, spied)

    counted(ReadPlanCache, "plan", "plan")
    counted(CompiledTemplate, "render", "render")
    counted(type(POSTGRES), "to_driver_sql", "to_driver_sql")
    counted(connection_module, "adapt_binds", "adapt_binds")
    rows, pipeline = connection_module._execute_rows, connection_module._execute_pipeline  # pyright: ignore[reportPrivateUsage] - the native submissions this proof observes

    def single(native: Any, context: Any, dialect: Any, sql: bytes, binds: Any, reads: Any) -> Any:
        preparation.submissions.append((native, (sql,), (binds,)))
        return rows(native, context, dialect, sql, binds, reads)

    def batch(native: Any, context: Any, dialect: Any, statements: Any) -> Any:
        preparation.submissions.append(
            (native, tuple(sql for sql, _, _ in statements), tuple(b for _, b, _ in statements))
        )
        return pipeline(native, context, dialect, statements)

    monkeypatch.setattr(connection_module, "_execute_rows", single)
    monkeypatch.setattr(connection_module, "_execute_pipeline", batch)
    return preparation


def _end_the_session(profile_run: Any, application_name: str) -> None:
    end_backend(profile_run, named_backend(profile_run, application_name))


def _first_use_database(profile_run: Any, provider: _Heard) -> tuple[Any, Any, str]:
    profile_run.reset(model_of(_FIRST_USE_MODEL), {})
    application_name = f"parallax_first_use_{uuid.uuid4().hex[:12]}"
    root = connect(
        profile_run.configured(
            pool=PoolOptions(min_size=1, max_size=1),
            settings={"application_name": application_name},
        ),
        _FIRST_USE_MODEL,
        lifecycle_provider=provider,
    )
    db = root.using_database_login()
    db.transact(
        lambda tx: (
            tx.insert(Ledger(id=1, memo=Memo(text="first"))),
            tx.insert(Ledger(id=2, memo=Memo(text="second"))),
            tx.insert(Ledger(id=3, memo=Memo(text="unread"))),
            tx.insert(Entry(id=10, ledger=1, amount=5)),
            tx.insert(Entry(id=11, ledger=2, amount=7)),
            tx.insert(Hold(id=20, ledger=2, reason="review")),
            tx.insert(Folio(id=1, title="one")),
            tx.insert(Folio(id=2, title="two")),
            tx.insert(Folio(id=3, title="three")),
        )
    )
    return root, db, application_name


@pytest.mark.parametrize("reader", sorted(_READERS))
@pytest.mark.parametrize("layout", sorted(_LAYOUT_QUERIES))
def test_a_read_over_a_session_ended_while_idle_is_replaced_without_preparing_it_again(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch, layout: str, reader: str
) -> None:
    # The retained session is ended while it sits idle, and nothing validates
    # it on the way out of the pool, so the read's first statement meets it.
    # That statement is submitted again on a replacement inside the same
    # lease, with the very SQL and bind objects — membership array included —
    # it was prepared with: nothing is planned, rendered, converted, or
    # adapted again, and its children follow on the replacement. What the
    # operation reports — rows, one Acquisition and Release per lease, one
    # Database Call per statement — is exactly what the same read reports
    # undisturbed.
    query, read = _LAYOUT_QUERIES[layout], _READERS[reader]
    provider = _Heard()
    root, db, application_name = _first_use_database(profile_run, provider)
    with root:
        read(db, query)
        preparation = _observed_preparation(monkeypatch)
        provider.heard()
        undisturbed = read(db, query)
        expected_events = provider.heard()
        expected_counts, expected_submissions = preparation.taken()
        _end_the_session(profile_run, application_name)
        preparation.taken()
        replaced = read(db, query)
        observed_events = provider.heard()
        counts, submissions = preparation.taken()

    assert len(undisturbed) == 2
    assert replaced == undisturbed
    assert observed_events == expected_events
    assert observed_events.count("AcquisitionStarted") == observed_events.count("ReleaseFinished")
    assert counts == expected_counts
    (lost, repeated, *rest) = submissions
    assert lost[0] is not repeated[0]
    assert lost[1] == repeated[1] and all(map(operator.is_, lost[2], repeated[2]))
    assert [bind for bind in repeated[2][0] if isinstance(bind, list)] == [[1, 2]]
    assert [sql for _, sql, _ in [repeated, *rest]] == [sql for _, sql, _ in expected_submissions]
    if layout == "columns":
        (children,) = (submission for submission in rest if len(submission[1]) == 2)
        assert children[0] is repeated[0]
        assert all(any(isinstance(bind, list) for bind in binds) for binds in children[2])


def test_a_child_pipeline_cannot_claim_the_opportunity_its_root_read_spent(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The root read was the lease's first submission and it was answered, so a
    # session lost before its children are fetched fails the read: the batch
    # of child reads, designated as reads, is submitted once and never again.
    provider = _Heard()
    root, db, application_name = _first_use_database(profile_run, provider)
    query = _LAYOUT_QUERIES["columns"]
    with root:
        children = connection_module._execute_pipeline  # pyright: ignore[reportPrivateUsage] - the native submission this proof interrupts
        batches: list[int] = []

        def ending_first(native: Any, context: Any, dialect: Any, statements: Any) -> Any:
            batches.append(len(statements))
            _end_the_session(profile_run, application_name)
            return children(native, context, dialect, statements)

        monkeypatch.setattr(connection_module, "_execute_pipeline", ending_first)
        provider.heard()
        with pytest.raises(ExecutionFailure) as failed:
            db.find(query).results()
        events = provider.heard()

        assert _ledger_ids(db) == [1, 2, 3]

    assert isinstance(failed.value.__cause__, DatabaseError)
    assert batches == [2]
    assert events.count("AcquisitionStarted") == events.count("ReleaseFinished") == 1


def _ledger_ids(db: Any) -> list[int]:
    return sorted(int(ledger.id) for ledger in db.find(Ledger.where(Ledger.all)).results())


# --------------------------------------------------------------------------- #
# Pool observation, through the shipped composition seam.                      #
# --------------------------------------------------------------------------- #


def test_a_provider_observes_the_pool_across_the_whole_life_of_a_handle(
    profile_run: Any,
) -> None:
    # The executable story, against the real pool it describes: registered
    # before the handle is published, read after a delivery page returned the
    # only slot, and detached once the handle closes.
    _seeded(profile_run)
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1))

    reading = (
        database_pooling_stories.the_pool_reports_its_own_capacity_and_stops_when_the_handle_closes(
            configured, _ACCOUNT
        )
    )

    assert reading.at_rest.managed == 1
    assert reading.at_rest.idle == 1
    # The sample is taken after one root was published, between pages, so the
    # page lease has returned even though the delivery remains open.
    assert reading.while_working.idle == 1
    assert reading.while_working.checkouts > reading.at_rest.checkouts
    assert reading.while_working.waiting == 0
    assert reading.detached_after_close
    assert reading.registration_closed


def test_every_documented_retention_form_opens_against_a_real_server(profile_run: Any) -> None:
    # The guide's construction block builds four configurations over one
    # connection string. What a real server adds to the unit proof of their
    # policies is that each spelling opens a runtime that reads.
    _seeded(profile_run)
    configured = profile_run.configured()
    forms = database_pooling_stories.every_retention_form_is_one_configuration_value(
        configured.connection_string, configured.credentials
    )

    for adapter in (forms.default, forms.tuned, forms.zero_minimum, forms.on_demand):
        with connect(adapter, _ACCOUNT) as _root_db:
            db = _root_db.using_database_login()
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
