"""A started runtime: what it declares and binds, its admission, and its close.

Binding a source acquires nothing; admission decides closure and expiry in one
place; closing stops admission, detaches every metrics source, and attempts
every pool's close whatever an earlier one raised.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import pytest

from parallax.core.internal.db_port import (
    RESOURCE_LOGGER_NAME,
    ConnectionAcquisitionError,
    PoolDetached,
    Route,
    RouteCapabilities,
    RouteSelection,
)
from parallax.core.internal.dialect import POSTGRES
from tests.unit.core.db_port._runtime._composition import (
    ROUTED,
    login_context,
    pool_of,
    pooled_runtime,
    reader_context,
    resource_records,
    routed,
)
from tests.unit.core.db_port._runtime._scripted_native import (
    ScriptedConnection,
    ScriptedDriver,
    checkout_failed,
)

# --------------------------------------------------------------------------- #
# Declaration and binding: what a runtime answers without acquiring.          #
# --------------------------------------------------------------------------- #


def test_a_runtime_publishes_an_immutable_copy_of_the_routes_it_was_declared() -> None:
    routes: dict[Route, RouteCapabilities] = {"writer": RouteCapabilities.every_level()}
    runtime = pooled_runtime(pool_of(), routes=routes)
    routes["reader"] = RouteCapabilities(frozenset())

    assert dict(runtime.routes) == {"writer": RouteCapabilities.every_level()}
    with pytest.raises(TypeError):
        cast("Any", runtime.routes)["reader"] = RouteCapabilities(frozenset())


def test_a_writer_only_acquisition_selects_the_writer_once_entered() -> None:
    pool = pool_of()
    resource = pooled_runtime(pool).login_source().new_context("writer_only")

    assert resource.selection is None
    with resource:
        assert resource.selection == RouteSelection("writer")
    assert resource.selection == RouteSelection("writer")


@pytest.mark.parametrize("policy", ["reader_only", "reader_preferred"])
def test_a_writer_only_runtime_refuses_to_build_a_reader_context(policy: str) -> None:
    # Core resolves every policy against the declared routes first, so being
    # asked for one this runtime cannot serve is a caller defect, refused before
    # anything is taken.
    pool = pool_of()

    with pytest.raises(ValueError, match="does not serve"):
        pooled_runtime(pool).login_source().new_context(cast("Any", policy))

    assert pool.budgets == []


def test_a_refused_entry_reports_the_writer_on_the_context_and_the_failure_alike() -> None:
    pool = pool_of(checkout_failure=checkout_failed("timeout"))
    resource = login_context(pooled_runtime(pool))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer")
    assert resource.selection == RouteSelection("writer")


def test_authority_binding_checks_its_authorization_once_and_acquires_nothing() -> None:
    pool = pool_of()
    driver = ScriptedDriver()
    runtime = pooled_runtime(pool, driver=driver)

    source = runtime.principal_source("tenant_reader")
    first = source.new_context("writer_only")
    second = source.new_context("writer_only")

    assert first is not second
    assert driver.authorizations == ["tenant_reader"]
    assert pool.budgets == []
    assert not hasattr(runtime, "connection")


def test_an_authorization_the_driver_refuses_binds_nothing_and_acquires_nothing() -> None:
    pool = pool_of()
    driver = ScriptedDriver()
    refusal = ValueError("not this driver's authorization")
    driver.authorization_refusal = refusal

    with pytest.raises(ValueError) as refused:
        pooled_runtime(pool, driver=driver).principal_source(7)

    assert refused.value is refusal
    assert pool.budgets == []


# --------------------------------------------------------------------------- #
# Admission and shutdown.                                                     #
# --------------------------------------------------------------------------- #


def test_close_is_idempotent_and_permanent() -> None:
    pool = pool_of()
    runtime = pooled_runtime(pool)

    runtime.close()
    runtime.close()

    assert pool.closes == 1
    with pytest.raises(ConnectionAcquisitionError) as refused:
        login_context(runtime).__enter__()
    assert refused.value.reason == "closed"


def test_a_scope_admitted_before_a_close_may_still_finish() -> None:
    # Admission is decided once, immediately before the connection is handed
    # over: later work in an admitted scope uses what it was given, including
    # statements it has not issued yet.
    connection = ScriptedConnection()
    pool = pool_of(connection)
    runtime = pooled_runtime(pool)

    with login_context(runtime) as scoped:
        runtime.close()
        scoped.submit("select 1")

    assert connection.submitted == ["select 1"]
    assert pool.returned == [connection]


def test_a_native_close_problem_is_reported_rather_than_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Close is what a caller runs while unwinding; a handle that refused to
    # close would leave them nothing better to do. So the problem leaves as a
    # report on the restricted resource logger — carrying the phase, the code
    # and fixed text, and nothing the native failure said — rather than as an
    # exception, and a close that reported nothing would be a silently lost
    # runtime.
    runtime = pooled_runtime(
        pool_of(close_failure=RuntimeError("connection to host=secret refused"))
    )

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        runtime.close()

    (record,) = caplog.records
    assert record.name == RESOURCE_LOGGER_NAME
    assert "return/handoff-failed" in record.getMessage()
    assert "secret" not in record.getMessage()
    assert record.exc_info is None


def test_the_ordinary_acquisition_budget_comes_from_the_configured_timeout() -> None:
    pool = pool_of()
    runtime = pooled_runtime(pool, acquire_timeout=3.0)
    with login_context(runtime):
        pass
    (given,) = pool.budgets
    assert given is not None and 0.0 < given <= 3.0


def test_a_runtime_answers_the_dialect_it_was_composed_with() -> None:
    assert pooled_runtime(pool_of()).dialect is POSTGRES


def test_login_identity_is_unavailable_before_startup_completion() -> None:
    runtime = pooled_runtime(pool_of())

    with pytest.raises(RuntimeError, match="not completed startup"):
        _ = runtime.login_identity


def test_startup_completion_installs_the_login_exactly_once() -> None:
    runtime = pooled_runtime(pool_of())

    runtime._complete_startup(  # pyright: ignore[reportPrivateUsage] - direct startup state pin
        "first-login"
    )

    assert runtime.login_identity == "first-login"
    with pytest.raises(RuntimeError, match="already completed startup"):
        runtime._complete_startup(  # pyright: ignore[reportPrivateUsage] - direct startup state pin
            "second-login"
        )


# --------------------------------------------------------------------------- #
# Routes: each pool measured, and every one closed.                           #
# --------------------------------------------------------------------------- #


def test_a_routed_runtime_measures_each_pool_in_route_order() -> None:
    runtime = routed(pool_of(), pool_of())

    assert dict(runtime.routes) == dict(ROUTED)
    assert [(source.route, source.purpose) for source in runtime.pool_metrics] == [
        ("writer", "application"),
        ("reader", "application"),
        ("writer", "reservation"),
    ]


def test_a_reader_lease_s_refusal_reports_the_reader() -> None:
    runtime = routed(pool_of(), pool_of(checkout_failure=checkout_failed("timeout")))
    resource = reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert (refused.value.reason, refused.value.selection) == (
        "timeout",
        RouteSelection("reader"),
    )


def test_closing_detaches_both_sources_then_closes_both_pools_whatever_one_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    writer_pool = pool_of(close_failure=RuntimeError("the writer would not close"))
    reader_pool = pool_of()
    runtime = routed(writer_pool, reader_pool)
    sources = runtime.pool_metrics

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        runtime.close()
        runtime.close()

    assert (writer_pool.closes, reader_pool.closes) == (1, 1)
    assert all(isinstance(source.sample(), PoolDetached) for source in sources)
    assert len(resource_records(caplog)) == 1
    # One admission decision serves both routes.
    with pytest.raises(ConnectionAcquisitionError) as refused:
        reader_context(runtime).__enter__()
    assert refused.value.reason == "closed"


def test_an_interrupted_close_still_closes_every_later_pool() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool, reader_pool = pool_of(close_failure=interrupt), pool_of()
    runtime = routed(writer_pool, reader_pool)

    with pytest.raises(KeyboardInterrupt) as raised:
        runtime.close()

    assert raised.value is interrupt
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)
