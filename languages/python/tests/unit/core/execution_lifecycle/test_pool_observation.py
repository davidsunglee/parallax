"""Registering an interest in a pool, and giving it up again (driver-free).

Pool observation is the one lifecycle interest that belongs to no operation, so
what is proven here is the LIFETIME rather than any event: when a Provider is
offered the source, what makes it not be offered at all, what a registration that
raised leaves behind, and what a handle closing does with one it holds.

Two rules carry most of the weight. Registration precedes publication, so a
registration that raises produces no handle and closes the runtime that was
opened for it. And a handle owns the REGISTRATION rather than the exporter behind
it: closing gives the interest up and touches nothing else the application built.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import pytest

from parallax.conformance.story_models import ACCOUNT_MODEL
from parallax.core.db_port import RESOURCE_LOGGER_NAME
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    FanoutLifecycleProvider,
    RootExecution,
)
from parallax.core.execution_lifecycle._pool_observation import (
    PoolObservation,
    register_pool_observation,
)
from parallax.snapshot import connect
from parallax.snapshot.handle import Database
from tests._support.db_port import Read, ScriptedAdapter
from tests.unit._contention_support import observing
from tests.unit._pool_source_support import DetachableSource


class _Registration:
    def __init__(self, *, refuses: Exception | None = None) -> None:
        self.closes = 0
        self._refuses = refuses

    def close(self) -> None:
        self.closes += 1
        if self._refuses is not None:
            raise self._refuses


class _Executions:
    """A Provider that observes executions and nothing else."""

    def __init__(self, *, accepts: bool = True) -> None:
        self.accepts = accepts
        self.roots = 0
        self.events: list[ExecutionEvent] = []
        self.closes = 0

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        self.roots += 1
        return _Handler(self) if self.accepts else None

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(f"no handler failure expected: {error.diagnostic.message}")

    def close(self) -> None:
        # Nothing calls this. It exists so a test can prove nothing calls it: a
        # handle closes the registration it was given, never the exporter.
        self.closes += 1


class _Handler:
    def __init__(self, provider: _Executions) -> None:
        self._provider = provider

    def handle(self, event: ExecutionEvent, /) -> None:
        self._provider.events.append(event)


class _Observes(_Executions):
    """A Provider that also observes the pool."""

    def __init__(
        self,
        *,
        accepts: bool = True,
        registration: _Registration | None = None,
        declines_pool: bool = False,
        raises: Exception | None = None,
    ) -> None:
        super().__init__(accepts=accepts)
        self.registration = registration if registration is not None else _Registration()
        self.offered: list[object] = []
        self._declines_pool = declines_pool
        self._raises = raises

    def observe_pool(self, source: Any, /) -> PoolObservation | None:
        self.offered.append(source)
        if self._raises is not None:
            raise self._raises
        return None if self._declines_pool else self.registration


_DEADLINE = 10.0
"""How long a handshake below waits before failing rather than hanging."""


def _adapter(*, metrics: object | None = None, script: Any = ()) -> ScriptedAdapter:
    return ScriptedAdapter(*script, metrics=metrics)  # pyright: ignore[reportArgumentType] - a source double satisfies the protocol structurally


def _connected(provider: Any, *, metrics: object | None = None, script: Any = ()) -> Database:
    return connect(
        _adapter(metrics=metrics, script=script), ACCOUNT_MODEL, lifecycle_provider=provider
    )


# --------------------------------------------------------------------------- #
# What is offered, and what is not offered at all.                             #
# --------------------------------------------------------------------------- #


def test_nothing_registers_without_a_provider() -> None:
    assert register_pool_observation(None, DetachableSource()) is None


def test_nothing_registers_without_a_source() -> None:
    # A runtime managing no pool publishes no source, so an observing Provider
    # is never asked: there is nothing to offer it.
    provider = _Observes()

    assert register_pool_observation(provider, None) is None
    assert provider.offered == []


def test_a_provider_that_observes_no_pool_registers_nothing() -> None:
    # Interest is declared by implementing the method and by nothing else —
    # there is no capability flag to answer and no second seam to pass.
    assert register_pool_observation(_Executions(), DetachableSource()) is None


def test_an_observing_provider_is_offered_the_runtime_s_own_source() -> None:
    source = DetachableSource()
    provider = _Observes()

    registered = register_pool_observation(provider, source)

    assert provider.offered == [source]
    assert registered is provider.registration


def test_a_provider_offered_the_source_may_decline_it() -> None:
    provider = _Observes(declines_pool=True)

    assert register_pool_observation(provider, DetachableSource()) is None
    assert provider.offered  # it WAS offered; declining is its own answer


# --------------------------------------------------------------------------- #
# Composition.                                                                 #
# --------------------------------------------------------------------------- #


def test_a_connected_handle_registers_the_runtime_s_source() -> None:
    source = DetachableSource()
    provider = _Observes()

    db = _connected(provider, metrics=source)
    try:
        assert provider.offered == [source]
    finally:
        db.close()


def test_a_provider_declining_every_root_still_observes_the_pool() -> None:
    # The two interests are independent: what a Provider wants from operations
    # says nothing about what it wants from the resource they run on.
    provider = _Observes(accepts=False)

    db = _connected(provider, metrics=DetachableSource(), script=[Read()])
    try:
        list(db.wire.find({"target": "Account", "predicate": {"all": {}}}).results())
        assert provider.roots == 1
        assert provider.events == []
        assert len(provider.offered) == 1
    finally:
        db.close()


def test_a_runtime_publishing_no_source_offers_nothing_to_an_observing_provider() -> None:
    provider = _Observes()

    db = _connected(provider, metrics=None)
    try:
        assert provider.offered == []
    finally:
        db.close()


def test_a_registration_that_raises_publishes_no_handle_and_closes_the_runtime() -> None:
    # Registration precedes publication, so a Provider that raised has stopped
    # composition rather than left a handle explaining itself later. The
    # exception keeps its identity: nothing wraps or reclassifies it.
    refusal = RuntimeError("this exporter refuses to observe this pool")
    provider = _Observes(raises=refusal)
    adapter = _adapter(metrics=DetachableSource())

    with pytest.raises(RuntimeError) as raised:
        connect(adapter, ACCOUNT_MODEL, lifecycle_provider=provider)

    assert raised.value is refusal
    assert adapter.closes == 1


# --------------------------------------------------------------------------- #
# Shutdown.                                                                    #
# --------------------------------------------------------------------------- #


def test_closing_the_handle_closes_the_registration_once_however_often_it_is_closed() -> None:
    provider = _Observes()
    db = _connected(provider, metrics=DetachableSource())

    db.close()
    db.close()

    assert provider.registration.closes == 1


def test_the_handle_closes_the_registration_and_never_the_provider() -> None:
    # The exporter, the queue, and the metrics client behind a registration are
    # the application's and outlive the handle.
    provider = _Observes()
    db = _connected(provider, metrics=DetachableSource())

    db.close()

    assert provider.registration.closes == 1
    assert provider.closes == 0


def test_a_runtime_that_will_not_close_still_gives_up_the_registration() -> None:
    class _Refusing:
        dialect = ScriptedAdapter().dialect

        def __init__(self) -> None:
            self.metrics = DetachableSource()

        @property
        def pool_metrics(self) -> Any:
            return self.metrics

        def open(self) -> Any:
            return self

        def connection(self) -> Any:
            raise AssertionError("no acquisition expected")

        def close(self) -> None:
            raise RuntimeError("this runtime would not close")

    provider = _Observes()
    db = connect(_Refusing(), ACCOUNT_MODEL, lifecycle_provider=provider)

    with pytest.raises(RuntimeError):
        db.close()

    assert provider.registration.closes == 1


class _ParkedRuntime:
    """A runtime whose close blocks in the middle, so a second close overlaps it."""

    dialect = ScriptedAdapter().dialect

    def __init__(self, log: list[str]) -> None:
        self.metrics = DetachableSource()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.in_close = False
        self.log = log
        self._closing = threading.Lock()
        self._closed = False

    @property
    def pool_metrics(self) -> Any:
        return self.metrics

    def open(self) -> Any:
        return self

    def connection(self) -> Any:
        raise AssertionError("no acquisition expected")

    def close(self) -> None:
        with self._closing:
            if self._closed:
                return
            self._closed = True
        self.in_close = True
        self.entered.set()
        assert self.release.wait(_DEADLINE)
        self.metrics.detach()
        self.in_close = False
        self.log.append("runtime-close-finished")


class _ClosesAfterTheRuntime(_Registration):
    def __init__(self, runtime: _ParkedRuntime) -> None:
        super().__init__()
        self._runtime = runtime
        self.saw_the_runtime_still_closing = False

    def close(self) -> None:
        self.saw_the_runtime_still_closing = self._runtime.in_close
        self._runtime.log.append("registration-closed")
        super().close()


def test_two_callers_closing_at_once_give_the_registration_up_once_and_last() -> None:
    # The second caller reaches the handle's shutdown claim and finds the first
    # caller holding it, parked inside the runtime's own close: that arrival is
    # the overlap itself, and the first caller is released only once it has
    # happened. The registration is then given up exactly once and only after
    # the runtime's close has returned — never beside a runtime still being torn
    # down — and the caller that closed a handle another thread was closing does
    # not return before that is true.
    log: list[str] = []
    runtime = _ParkedRuntime(log)
    registration = _ClosesAfterTheRuntime(runtime)
    provider = _Observes(registration=registration)
    db = connect(runtime, ACCOUNT_MODEL, lifecycle_provider=provider)

    def close_and_record() -> None:
        db.close()
        log.append("second-close-returned")

    first = threading.Thread(target=db.close)
    first.start()
    assert runtime.entered.wait(_DEADLINE)
    shutdown = observing(db, "_shutdown")
    second = threading.Thread(target=close_and_record)
    second.start()
    assert shutdown.contended.wait(_DEADLINE)
    runtime.release.set()
    first.join(_DEADLINE)
    second.join(_DEADLINE)

    assert not first.is_alive()
    assert not second.is_alive()
    assert registration.closes == 1
    assert registration.saw_the_runtime_still_closing is False
    assert log.index("runtime-close-finished") < log.index("registration-closed")
    assert log[-1] == "second-close-returned"


def test_a_registration_that_will_not_close_is_contained_and_reported_thinly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Shutdown runs when no Handler is left to receive anything, so the one line
    # this produces is the whole report — and it names nothing about the
    # observer that refused, whose message is application state nobody audited.
    refusal = RuntimeError("the exporter's socket is already shut: 10.0.0.4:9090")
    provider = _Observes(registration=_Registration(refuses=refusal))
    db = _connected(provider, metrics=DetachableSource())

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        db.close()

    (record,) = caplog.records
    assert record.name == RESOURCE_LOGGER_NAME
    assert record.getMessage() == "a pool observation registered at composition could not be closed"
    assert record.exc_info is None
    assert "10.0.0.4" not in record.getMessage()


# --------------------------------------------------------------------------- #
# Fan-out.                                                                     #
# --------------------------------------------------------------------------- #


def test_every_composed_provider_that_observes_the_pool_is_offered_one_source() -> None:
    source = DetachableSource()
    first, second, third = _Observes(), _Executions(), _Observes()
    fanout = FanoutLifecycleProvider([first, second, third])

    registered = fanout.observe_pool(source)

    assert first.offered == [source]
    assert third.offered == [source]
    assert registered is not None


def test_a_nested_fan_out_registers_its_own_leaves() -> None:
    source = DetachableSource()
    inner_leaf, outer_leaf = _Observes(), _Observes()
    fanout = FanoutLifecycleProvider(
        [FanoutLifecycleProvider([inner_leaf]), outer_leaf],
    )

    registered = fanout.observe_pool(source)
    assert registered is not None
    registered.close()

    assert inner_leaf.offered == [source]
    assert inner_leaf.registration.closes == 1
    assert outer_leaf.registration.closes == 1


def test_a_composition_no_child_observed_registers_nothing() -> None:
    fanout = FanoutLifecycleProvider([_Executions(), _Executions()])

    assert fanout.observe_pool(DetachableSource()) is None


def test_closing_a_composition_s_registration_closes_every_child_s() -> None:
    first, second = _Observes(), _Observes()
    registered = FanoutLifecycleProvider([first, second]).observe_pool(DetachableSource())
    assert registered is not None

    registered.close()

    assert first.registration.closes == 1
    assert second.registration.closes == 1


def test_a_child_registration_that_raises_unwinds_the_ones_before_it() -> None:
    # A registration nobody holds could never be closed, so the children that
    # already registered are closed on the way out and the failure that stopped
    # the composition is the one that leaves.
    refusal = RuntimeError("the third exporter refuses this pool")
    first, second = _Observes(), _Observes()
    third = _Observes(raises=refusal)
    fourth = _Observes()
    fanout = FanoutLifecycleProvider([first, second, third, fourth])

    with pytest.raises(RuntimeError) as raised:
        fanout.observe_pool(DetachableSource())

    assert raised.value is refusal
    assert first.registration.closes == 1
    assert second.registration.closes == 1
    # The fourth was never reached, so it has nothing to give up.
    assert fourth.offered == []
    assert fourth.registration.closes == 0


def test_an_unwind_attempts_every_close_even_where_one_of_them_fails() -> None:
    refusal = RuntimeError("the second exporter refuses this pool")
    stubborn = _Observes(registration=_Registration(refuses=RuntimeError("nor will this close")))
    willing = _Observes()
    fanout = FanoutLifecycleProvider([stubborn, willing, _Observes(raises=refusal)])

    with pytest.raises(RuntimeError) as raised:
        fanout.observe_pool(DetachableSource())

    assert raised.value is refusal
    assert stubborn.registration.closes == 1
    assert willing.registration.closes == 1


def test_a_fanned_out_composition_registers_through_a_connected_handle() -> None:
    first, second = _Observes(), _Observes()
    db = _connected(FanoutLifecycleProvider([first, second]), metrics=DetachableSource())

    db.close()

    assert len(first.offered) == 1
    assert first.registration.closes == 1
    assert second.registration.closes == 1
