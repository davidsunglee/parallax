"""The native pool behind the runtime's pool seam (Docker-free).

Everything driver-shaped about a pool lives here: what each native checkout
failure means, how the native statistics become metrics, how both psycopg_pool
modes are built and opened, and how each physical connection attempt reports
what it met — from the thread that made it, once. Where the adapter's behavior
is the installed library's rather than its own, the pins drive `psycopg_pool`
itself over stub connections, so a release that changed it fails here.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, cast

import psycopg
import psycopg_pool
import pytest
from psycopg.adapt import AdaptersMap
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from parallax.core.internal.db_port import (
    DRIVER_MANAGED,
    CheckoutFailed,
    ConnectionAcquisitionError,
    CredentialResolutionError,
    Password,
    PoolMetrics,
)
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresEndpoint
from parallax.postgres._connection import IncompatibleSessionError
from parallax.postgres._context import checkout
from parallax.postgres._pool import (
    DialObserver,
    PostgresPool,
    open_pool,
    reservation_socket_options,
)
from parallax.postgres._route import PostgresRoute

_GAUGES: dict[str, object] = {
    "pool_min": 1,
    "pool_max": 10,
    "pool_size": 4,
    "pool_available": 3,
    "requests_waiting": 0,
}

_COUNTERS: dict[str, object] = {
    "requests_num": 17,
    "requests_queued": 2,
    "requests_wait_ms": 45,
    "requests_errors": 1,
    "connections_num": 5,
    "connections_ms": 130,
    "connections_errors": 1,
    "connections_lost": 2,
    "returns_bad": 3,
}


class _Native:
    """A native pool answering one scripted checkout and scripted statistics."""

    def __init__(
        self,
        *readings: Mapping[str, object],
        failure: BaseException | None = None,
    ) -> None:
        self.failure = failure
        self.connection = object()
        self._readings = list(readings) or [{**_GAUGES, **_COUNTERS}]
        self.timeouts: list[float | None] = []
        self.put: list[object] = []
        self.reads = 0
        self.closes = 0

    def getconn(self, timeout: float | None = None) -> object:
        self.timeouts.append(timeout)
        if self.failure is not None:
            raise self.failure
        return self.connection

    def putconn(self, connection: object) -> None:
        self.put.append(connection)

    def get_stats(self) -> Mapping[str, object]:
        self.reads += 1
        return self._readings[min(self.reads, len(self._readings)) - 1]

    def close(self) -> None:
        self.closes += 1


def _wrapped(native: _Native) -> PostgresPool:
    return PostgresPool(cast("Any", native))


# --------------------------------------------------------------------------- #
# Checkout and hand-back.                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("native", "reason"),
    [
        (psycopg_pool.PoolTimeout("waited"), "timeout"),
        (psycopg_pool.TooManyRequests("queued"), "queue_rejected"),
        (psycopg_pool.PoolClosed("closed"), "closed"),
        (psycopg.OperationalError("could not connect"), "unavailable"),
        (psycopg.ProgrammingError("invalid connection option"), "preparation_failed"),
        (CredentialResolutionError("RDS IAM token could not be generated"), "credentials_refused"),
    ],
)
def test_every_native_checkout_failure_maps_to_its_own_reason(
    native: Exception, reason: str
) -> None:
    # A dial failure is in the table because an on-demand pool with spare
    # capacity dials on the checking-out thread: what the dial met comes out of
    # the checkout itself.
    with pytest.raises(CheckoutFailed) as failed:
        _wrapped(_Native(failure=native)).check_out(5.0)

    assert failed.value.reason == reason
    assert failed.value.__cause__ is native


def test_a_control_flow_exception_from_the_native_checkout_is_not_a_checkout_failure() -> None:
    with pytest.raises(KeyboardInterrupt):
        _wrapped(_Native(failure=KeyboardInterrupt())).check_out(5.0)


def test_the_budget_is_the_one_native_wait_and_a_success_hands_over_its_connection() -> None:
    native = _Native()

    connection = _wrapped(native).check_out(2.5)

    assert connection is native.connection
    assert native.timeouts == [2.5]


def test_each_accounting_method_hands_the_connection_back_natively_once() -> None:
    native = _Native()
    pool = _wrapped(native)
    reused, disposed = cast("Any", object()), cast("Any", object())

    pool.check_in(reused)
    pool.discard(disposed)

    assert native.put == [reused, disposed]


def test_closing_twice_is_harmless_on_the_installed_pool() -> None:
    native = psycopg_pool.NullConnectionPool("", open=False)
    native.open()
    pool = PostgresPool(cast("Any", native))

    pool.close()
    pool.close()

    assert native.closed


# --------------------------------------------------------------------------- #
# Statistics: what a native reading must carry to be one.                      #
# --------------------------------------------------------------------------- #


def test_a_full_native_reading_becomes_metrics_field_for_field() -> None:
    assert _wrapped(_Native({**_GAUGES, **_COUNTERS})).metrics() == PoolMetrics(
        pool_min=1,
        pool_max=10,
        pool_size=4,
        pool_available=3,
        requests_waiting=0,
        requests_num=17,
        requests_queued=2,
        requests_wait_ms=45,
        requests_errors=1,
        connections_num=5,
        connections_ms=130,
        connections_errors=1,
        connections_lost=2,
        returns_bad=3,
    )


def test_counters_the_pool_never_incremented_read_as_zero() -> None:
    # The native pool omits a counter it has never touched, and "never touched"
    # is what zero says. A gauge is not defaulted this way: the pool supplies
    # every gauge on every successful call.
    metrics = _wrapped(_Native(dict(_GAUGES))).metrics()

    assert metrics.requests_num == 0
    assert metrics.connections_lost == 0
    assert metrics.returns_bad == 0
    assert metrics.pool_max == 10


def test_a_reading_the_contract_does_not_name_is_ignored() -> None:
    # `usage_ms` is the concrete instance: the native pool populates it only
    # from a checkout context this adapter does not use, so it is a key the
    # contract deliberately omits rather than one it never expected.
    metrics = _wrapped(
        _Native({**_GAUGES, "usage_ms": 900, "something_a_later_release_added": 7})
    ).metrics()

    assert metrics.pool_size == 4
    assert not hasattr(metrics, "usage_ms")


def test_no_relationship_between_two_fields_is_checked() -> None:
    # The reading is taken field by field rather than atomically, so more
    # available than managed is a pool measured mid-change, not a broken one.
    metrics = _wrapped(_Native({**_GAUGES, "pool_size": 1, "pool_available": 4})).metrics()

    assert (metrics.pool_size, metrics.pool_available) == (1, 4)


def test_each_reading_reads_the_pool_s_bookkeeping_anew_and_nothing_else() -> None:
    native = _Native({**_GAUGES, "requests_num": 40}, {**_GAUGES, "requests_num": 2})
    pool = _wrapped(native)

    first, second = pool.metrics(), pool.metrics()

    assert (first.requests_num, second.requests_num) == (40, 2)
    assert native.reads == 2
    assert native.timeouts == []


@pytest.mark.parametrize("missing", sorted(_GAUGES))
def test_a_missing_gauge_is_no_reading(missing: str) -> None:
    reading = {**_GAUGES, **_COUNTERS}
    del reading[missing]

    with pytest.raises(Exception, match="did not carry the measurements") as refused:
        _wrapped(_Native(reading)).metrics()

    assert type(refused.value).__name__ == "_MalformedStatistics"


@pytest.mark.parametrize(
    "value",
    [True, False, 1.0, "4", None, Ellipsis, -1],
    ids=["true", "false", "float", "string", "null", "object", "negative"],
)
@pytest.mark.parametrize("field", ["pool_size", "requests_num"])
def test_a_reading_that_is_not_a_nonnegative_integer_is_no_reading(
    field: str, value: object
) -> None:
    # A gauge and a counter, because the refusal is about the VALUE rather than
    # about which half of the contract it belongs to. `True` is refused although
    # it is an `int`: a pool reporting a flag where a size belongs has reported
    # no size, and recording it as one connection would publish a number nothing
    # measured.
    with pytest.raises(Exception, match="did not carry the measurements") as refused:
        _wrapped(_Native({**_GAUGES, **_COUNTERS, field: value})).metrics()

    assert str(value) not in str(refused.value)
    assert field not in str(refused.value)


# --------------------------------------------------------------------------- #
# Construction: both retention modes, opened explicitly.                       #
# --------------------------------------------------------------------------- #


class _Recording:
    """A native pool class recording how it was constructed and opened."""

    built: ClassVar[list[_Recording]] = []
    open_failure: ClassVar[BaseException | None] = None

    def __init__(self, conninfo: str, **kwargs: object) -> None:
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.opens = 0
        self.closes = 0
        _Recording.built.append(self)

    def open(self) -> None:
        self.opens += 1
        if _Recording.open_failure is not None:
            raise _Recording.open_failure

    def close(self) -> None:
        self.closes += 1


@pytest.fixture
def recording(monkeypatch: pytest.MonkeyPatch) -> type[_Recording]:
    _Recording.built = []
    _Recording.open_failure = None
    monkeypatch.setattr(psycopg_pool, "ConnectionPool", _Recording)
    monkeypatch.setattr(psycopg_pool, "NullConnectionPool", _Recording)
    return _Recording


def _open(
    options: PoolOptions | OnDemandOptions,
    *,
    purpose: Any = "application",
    credentials: Any = DRIVER_MANAGED,
    acquire_timeout: float = 15.0,
) -> PostgresPool:
    return open_pool(
        PostgresEndpoint("host=writer", credentials=credentials, pool=options),
        "reader",
        purpose,
        DialLedger(),
        acquire_timeout=acquire_timeout,
        prepare_threshold=5,
    )


@pytest.mark.parametrize(
    "options", [PoolOptions(), OnDemandOptions()], ids=["retaining", "on-demand"]
)
def test_neither_native_pool_is_given_a_check_to_run_at_checkout(
    recording: type[_Recording], options: PoolOptions | OnDemandOptions
) -> None:
    # A checkout hands over what the pool holds without a round trip; a
    # connection that broke while idle is found by its first submission.
    _open(options)

    (built,) = recording.built
    assert built.opens == 1
    assert "check" not in built.kwargs
    assert built.kwargs["open"] is False
    # Every dial goes through the observer's own class, every connection is
    # initialized by it, and the pool is named for its route so the driver's
    # own warnings say which one they met.
    configure = built.kwargs["configure"]
    assert isinstance(configure, DialObserver)
    assert built.kwargs["connection_class"] is configure.connection_class
    assert built.kwargs["name"] == "parallax-reader"
    assert built.kwargs["kwargs"] == {
        "autocommit": True,
        "row_factory": tuple_row,
        "prepare_threshold": 5,
    }


def test_a_configured_credential_source_makes_the_keywords_resolve_per_attempt(
    recording: type[_Recording],
) -> None:
    _open(PoolOptions(), credentials=Password("hunter2"))

    (built,) = recording.built
    resolve = cast("Callable[[], dict[str, object]]", built.kwargs["kwargs"])
    assert resolve()["password"] == "hunter2"


@pytest.mark.parametrize(
    ("options", "retention"),
    [
        (
            PoolOptions(),
            {"min_size": 0, "max_size": 1, "max_waiting": 0, "num_workers": 1},
        ),
        (OnDemandOptions(), {"max_size": 1, "max_waiting": 0, "num_workers": 1}),
    ],
    ids=["retaining", "on-demand"],
)
def test_a_reservation_pool_keeps_one_lazy_connection_under_socket_limits(
    recording: type[_Recording], options: PoolOptions | OnDemandOptions, retention: dict[str, int]
) -> None:
    _open(options, purpose="reservation", acquire_timeout=2.5)

    (built,) = recording.built
    assert built.kwargs["name"] == "parallax-reader-reservation"
    assert {name: built.kwargs[name] for name in retention} == retention
    keywords = built.kwargs["kwargs"]
    assert isinstance(keywords, dict)
    assert {name: keywords[name] for name in reservation_socket_options(2.5)} == {
        "keepalives": 1,
        "keepalives_idle": 1,
        "keepalives_interval": 1,
        "keepalives_count": 3,
        "tcp_user_timeout": 3000,
    }


@pytest.mark.parametrize(
    "failure",
    [psycopg_pool.PoolTimeout("the pool would not open"), KeyboardInterrupt()],
    ids=["failure", "interrupt"],
)
def test_a_pool_that_will_not_open_is_closed_and_its_failure_raised_as_itself(
    recording: type[_Recording], failure: BaseException
) -> None:
    # Nothing else holds a pool that never opened, so nothing else would ever
    # close it. Which phase failed is the runtime's to say.
    recording.open_failure = failure

    with pytest.raises(type(failure)) as raised:
        _open(PoolOptions())

    assert raised.value is failure
    (built,) = recording.built
    assert built.closes == 1


# --------------------------------------------------------------------------- #
# Dial outcomes: one report per physical attempt, from the attempting thread.  #
# --------------------------------------------------------------------------- #


class _Reports:
    """A dial record keeping every report and the thread that made it."""

    def __init__(self) -> None:
        self.reports: list[tuple[str, BaseException | None, str]] = []

    def report_failure(self, reason: Any, cause: BaseException, /) -> None:
        self.reports.append((reason, cause, threading.current_thread().name))

    def report_usable(self) -> None:
        self.reports.append(("usable", None, threading.current_thread().name))


class _Info:
    def __init__(self, encoding: str = "utf-8") -> None:
        self.encoding = encoding

    def parameter_status(self, name: str) -> str | None:
        return "ISO, MDY" if name == "DateStyle" else None


class _IdlePgConn:
    transaction_status = TransactionStatus.IDLE


class _Initializable:
    """A connection whose initialization succeeds, or meets ``encoding``: the
    two settings and its own adapter map over psycopg's defaults."""

    def __init__(self, encoding: str = "utf-8") -> None:
        self.info = _Info(encoding)
        self.adapters = AdaptersMap(psycopg.adapters)
        self.pgconn = _IdlePgConn()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_a_successful_initialization_reports_the_connection_usable_and_clears_the_record() -> None:
    ledger = DialLedger()
    ledger.report_failure("preparation_failed", IncompatibleSessionError("earlier"))

    DialObserver(ledger)(cast("Any", _Initializable()))

    assert ledger.latest_failure is None


@pytest.mark.parametrize(
    "refusal",
    [IncompatibleSessionError("LATIN1"), RuntimeError("the loaders could not be installed")],
    ids=["incompatible", "unexpected"],
)
def test_an_initialization_that_fails_reports_its_refusal_closes_and_raises_it(
    monkeypatch: pytest.MonkeyPatch, refusal: Exception
) -> None:
    # The native pool neither keeps nor closes a connection its configure
    # refused, so nothing else would end the session.
    from parallax.postgres import _pool as pool_module

    def refuse(_connection: object) -> None:
        raise refusal

    monkeypatch.setattr(pool_module, "initialize_connection", refuse)
    reports = _Reports()
    connection = _Initializable()

    with pytest.raises(type(refusal)) as raised:
        DialObserver(reports)(cast("Any", connection))

    assert raised.value is refusal
    assert [(reason, cause) for reason, cause, _ in reports.reports] == [
        ("preparation_failed", refusal)
    ]
    assert connection.closed


def test_an_initialization_interrupted_reports_nothing_closes_and_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _pool as pool_module

    interrupt = KeyboardInterrupt()

    def interrupted(_connection: object) -> None:
        raise interrupt

    monkeypatch.setattr(pool_module, "initialize_connection", interrupted)
    reports = _Reports()
    connection = _Initializable()

    with pytest.raises(KeyboardInterrupt) as raised:
        DialObserver(reports)(cast("Any", connection))

    assert raised.value is interrupt
    assert reports.reports == []
    assert connection.closed


def test_an_observed_dial_that_fails_reports_its_failure_and_raises_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = psycopg.OperationalError("connection refused")

    def refuse(cls: type[Any], conninfo: str = "", **kwargs: object) -> Any:
        del cls, conninfo, kwargs
        raise refused

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(refuse))
    reports = _Reports()

    with pytest.raises(psycopg.OperationalError):
        DialObserver(reports).connection_class.connect("")

    assert [(reason, cause) for reason, cause, _ in reports.reports] == [("unavailable", refused)]


def test_an_observed_dial_that_succeeds_records_nothing_until_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = DialLedger()
    earlier = psycopg.OperationalError("connection refused")
    ledger.report_failure("unavailable", earlier)
    dialed = object()

    def dial(cls: type[Any], conninfo: str = "", **kwargs: object) -> Any:
        del cls, conninfo, kwargs
        return dialed

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(dial))

    assert DialObserver(ledger).connection_class.connect("") is dialed
    recorded = ledger.latest_failure
    assert recorded is not None and recorded.cause is earlier


class _Refusing:
    """A source that raises what it was built with, counting how often it is asked."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def resolve(self) -> Password:
        self.calls += 1
        raise self.error


def _recorded(ledger: DialLedger) -> BaseException | None:
    failure = ledger.latest_failure
    return None if failure is None else failure.cause


def test_each_physical_connection_gets_fresh_keywords_carrying_the_resolved_secret() -> None:
    # A fresh dictionary per connection, because the base is what the NEXT
    # connection would inherit: writing the secret into it would outlive the
    # connection it was resolved for.
    ledger = DialLedger()
    base: dict[str, object] = {"autocommit": True}
    resolve = DialObserver(ledger).connect_kwargs(base, Password("hunter2"))

    first, second = resolve(), resolve()

    assert first == {"autocommit": True, "password": "hunter2"}
    assert first is not second
    assert base == {"autocommit": True}
    assert ledger.latest_failure is None


def test_a_source_that_refuses_records_its_own_refusal_and_re_raises_it() -> None:
    # The pool creates most connections on a background path, so the refusal
    # reaches a waiting caller only by being on record.
    ledger = DialLedger()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    resolve = DialObserver(ledger).connect_kwargs({"autocommit": True}, _Refusing(refusal))

    with pytest.raises(CredentialResolutionError) as raised:
        resolve()

    assert raised.value is refusal
    assert _recorded(ledger) is refusal
    failure = ledger.latest_failure
    assert failure is not None and failure.reason == "credentials_refused"


def test_any_other_exception_a_source_raises_is_wrapped_with_fixed_text() -> None:
    # Classification must not depend on a provider's discipline, and the pool's
    # own warning line prints the exception's text — so what surfaces is fixed
    # text with the original chained beneath it.
    ledger = DialLedger()
    native = RuntimeError("could not sign for hunter2")
    resolve = DialObserver(ledger).connect_kwargs({"autocommit": True}, _Refusing(native))

    with pytest.raises(CredentialResolutionError) as raised:
        resolve()

    assert str(raised.value) == (
        "credential-resolution-failed: the credential source could not produce a password"
    )
    assert "hunter2" not in str(raised.value)
    assert raised.value.__cause__ is native
    assert _recorded(ledger) is raised.value


def test_a_resolved_credential_leaves_a_refusal_on_record_until_a_connection_is_usable() -> None:
    # Several workers dial at once over one record. A credential resolved for
    # one attempt establishes nothing — that attempt can still fail to dial or
    # to initialize — so clearing there would let it erase another attempt's
    # completed refusal and hand the waiting caller a bare timeout instead.
    ledger = DialLedger()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    ledger.report_failure("credentials_refused", refusal)
    observer = DialObserver(ledger)

    observer.connect_kwargs({"autocommit": True}, Password("hunter2"))()

    assert _recorded(ledger) is refusal

    observer(cast("Any", _Initializable()))

    assert ledger.latest_failure is None


def _on_demand(observer: DialObserver, source: Any = None) -> PostgresPool:
    """The installed on-demand pool, dialing through ``observer``'s hooks."""
    native = psycopg_pool.NullConnectionPool(
        "",
        connection_class=observer.connection_class,
        kwargs=({} if source is None else observer.connect_kwargs({"autocommit": True}, source)),
        configure=observer,
        open=False,
        num_workers=1,
    )
    native.open()
    return PostgresPool(cast("Any", native))


@pytest.mark.parametrize(
    ("step", "reason"),
    [
        ("credential", "credentials_refused"),
        ("dial", "unavailable"),
        ("initialization", "preparation_failed"),
        ("none", "usable"),
    ],
)
def test_an_on_demand_attempt_reports_one_outcome_from_the_caller_s_thread(
    monkeypatch: pytest.MonkeyPatch, step: str, reason: str
) -> None:
    # Each step that fails stops the attempt, so a refusal crossing the
    # library's hooks is reported by the one that met it and by no other.
    def dial(cls: type[Any], conninfo: str = "", **kwargs: object) -> Any:
        del cls, conninfo, kwargs
        if step == "dial":
            raise psycopg.OperationalError("connection refused")
        return _Initializable("latin1" if step == "initialization" else "utf-8")

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(dial))
    source = _Refusing(CredentialResolutionError("no token")) if step == "credential" else None
    reports = _Reports()
    pool = _on_demand(DialObserver(reports), source)
    try:
        if reason == "usable":
            pool.check_in(pool.check_out(1.0))
        else:
            with pytest.raises(CheckoutFailed) as failed:
                pool.check_out(1.0)
            assert failed.value.reason == reason
    finally:
        pool.close()

    caller = threading.current_thread().name
    assert [(reported, thread) for reported, _, thread in reports.reports] == [(reason, caller)]


@pytest.mark.parametrize(
    "native", ["NullConnectionPool", "ConnectionPool"], ids=["on-demand", "retaining"]
)
def test_the_installed_pools_dial_through_the_observer_s_connection_class(
    monkeypatch: pytest.MonkeyPatch, native: str
) -> None:
    # The hook is the library's public `connection_class`: on-demand with spare
    # capacity dials on the caller's thread and retaining on its own workers,
    # and both reach it and report there, once per attempt.
    refused = psycopg.OperationalError("connection refused")

    def refuse(cls: type[Any], conninfo: str = "", **kwargs: object) -> Any:
        del cls, conninfo, kwargs
        raise refused

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(refuse))
    ledger = DialLedger()
    reports = _Reports()

    class _Both:
        def report_failure(self, reason: Any, cause: BaseException, /) -> None:
            reports.report_failure(reason, cause)
            ledger.report_failure(reason, cause)

        def report_usable(self) -> None:
            reports.report_usable()
            ledger.report_usable()

    observer = DialObserver(_Both())
    options: dict[str, Any] = {"min_size": 0, "max_size": 1} if native == "ConnectionPool" else {}
    pool = getattr(psycopg_pool, native)(
        "",
        connection_class=observer.connection_class,
        configure=observer,
        open=False,
        num_workers=1,
        reconnect_timeout=5.0,
        name="parallax-reader",
        **options,
    )
    pool.open()
    try:
        with pytest.raises(ConnectionAcquisitionError) as failed:
            checkout(PostgresRoute("reader", PostgresPool(pool), ledger), _soon(0.5))
        attempts = pool.get_stats()["connections_num"]
    finally:
        pool.close()

    assert failed.value.reason == "unavailable"
    recorded = ledger.latest_failure
    assert recorded is not None and recorded.cause is refused
    threads = {thread for _, _, thread in reports.reports}
    if native == "NullConnectionPool":
        assert threads == {threading.current_thread().name}
    else:
        assert all(thread.startswith("parallax-reader-worker-") for thread in threads)
    assert len(reports.reports) <= attempts


def _soon(seconds: float) -> float:
    from time import monotonic

    return monotonic() + seconds


# --------------------------------------------------------------------------- #
# The native release this adapter's documented behavior rests on.              #
# --------------------------------------------------------------------------- #


class _NativeStub:
    """What the INSTALLED native pool creates, hands on, and closes.

    The pins below drive `psycopg_pool` itself rather than a fake of it. One of
    this adapter's documented behaviors is the library's rather than its own —
    on-demand establishment bounded by the remaining acquisition budget — so a
    release that changed it would otherwise change what the adapter promises
    without changing a line of it.
    """

    connects: ClassVar[list[dict[str, object]]] = []

    def __init__(self) -> None:
        self._pool: object = None
        self._created_at = 0.0
        self._expire_at = 0.0
        self.closed = False
        self.pgconn = _IdlePgConn()

    @classmethod
    def connect(cls, conninfo: str, **kwargs: object) -> _NativeStub:
        cls.connects.append({"conninfo": conninfo, **kwargs})
        return cls()

    def close(self) -> None:
        self.closed = True


def _native_null_pool(conninfo: str = "", **kwargs: Any) -> Any:
    _NativeStub.connects = []
    return cast(
        "Any",
        psycopg_pool.NullConnectionPool(
            conninfo, connection_class=cast("Any", _NativeStub), open=False, **kwargs
        ),
    )


def test_on_demand_establishment_is_bounded_by_the_remaining_budget_and_rounded() -> None:
    # `OnDemandOptions` documents this as the reason `acquire_timeout` is the
    # control that matters there: the establishment limit is whatever remains of
    # the acquisition budget, rounded to whole seconds with a floor of one.
    pool = _native_null_pool("connect_timeout=30")

    pool._connect(timeout=4.4)
    pool._connect(timeout=0.2)

    assert [created["connect_timeout"] for created in _NativeStub.connects] == [4, 1]


def test_an_establishment_keyword_overrides_what_the_connection_string_asked_for() -> None:
    # The other half of the same claim: the derived limit is passed as a keyword,
    # and a keyword wins over the same setting in the connection string.
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    resolved = conninfo_to_dict(make_conninfo("connect_timeout=30", connect_timeout=4))

    assert resolved["connect_timeout"] == "4"


class _RecoveringStub(_NativeStub):
    """A native connection whose first ``refusals`` dials fail."""

    refusals: ClassVar[int] = 0

    @classmethod
    def connect(cls, conninfo: str, **kwargs: object) -> _NativeStub:
        if cls.refusals > 0:
            cls.refusals -= 1
            raise psycopg.OperationalError("connection refused")
        return super().connect(conninfo, **kwargs)


def test_a_retaining_pool_that_gave_up_reconnecting_grows_again_on_later_demand() -> None:
    # The library relinquishes the capacity a failed growth held once its own
    # reconnection deadline passes, so the next checkout schedules a dial of
    # its own: demand alone recovers a reader nothing probes in the background.
    # Its own retry is immediate under a zero deadline, so two refusals spend it.
    _RecoveringStub.refusals = 2
    _NativeStub.connects = []
    pool = psycopg_pool.ConnectionPool(
        "",
        connection_class=cast("Any", _RecoveringStub),
        open=False,
        min_size=0,
        max_size=1,
        num_workers=1,
        reconnect_timeout=0.0,
    )
    pool.open()
    try:
        with pytest.raises(psycopg_pool.PoolTimeout):
            pool.getconn(timeout=0.5)
        recovered = pool.getconn(timeout=2.0)
        pool.putconn(recovered)
    finally:
        pool.close()

    assert len(_NativeStub.connects) == 1


def test_an_on_demand_pool_dials_again_on_every_later_demand() -> None:
    _RecoveringStub.refusals = 1
    _NativeStub.connects = []
    pool = psycopg_pool.NullConnectionPool(
        "", connection_class=cast("Any", _RecoveringStub), open=False, num_workers=1
    )
    pool.open()
    try:
        with pytest.raises(psycopg.OperationalError):
            pool.getconn(timeout=1.0)
        recovered = pool.getconn(timeout=1.0)
        pool.putconn(recovered)
    finally:
        pool.close()

    assert len(_NativeStub.connects) == 1
