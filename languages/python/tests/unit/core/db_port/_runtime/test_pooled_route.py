"""A route's readiness and its probe slot, as the leases it hands over see them.

A pending route proves itself on the connections it hands over: the first proof
that succeeds verifies it, the first positive mismatch refuses it for good, and
a race between them admits nothing on a refused route. A route known to be
unreachable lets one preferred acquisition probe it while the rest move on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest

from parallax.core.internal.db_port import (
    RESOURCE_LOGGER_NAME,
    ConnectionAcquisitionError,
    Invalidated,
    ProbeMismatch,
    Returned,
    RouteSelection,
)
from parallax.core.internal.db_port._runtime._pooled_route import PooledRoute
from parallax.core.internal.db_port._runtime._pooled_runtime import PooledRuntime
from tests.unit.core.db_port._runtime._composition import (
    available_samples,
    lost_session,
    pool_of,
    preferred_context,
    reader_context,
    reader_route_of,
    resource_records,
    routed,
    whatever_budget,
)
from tests.unit.core.db_port._runtime._scripted_native import (
    PROVE,
    RESTORE,
    Clock,
    ScriptedConnection,
    SessionLost,
    checkout_failed,
)


def _lose_after_probe(connection: ScriptedConnection) -> Callable[[str], None]:
    def lose(text: str) -> None:
        if text != PROVE:
            connection.lost = lost_session()

    return lose


def _losing_after_probe() -> ScriptedConnection:
    connection = ScriptedConnection()
    connection.on_submit = _lose_after_probe(connection)
    return connection


def _known_unreachable(
    runtime: PooledRuntime[ScriptedConnection, object],
) -> PooledRoute[ScriptedConnection]:
    reader = reader_route_of(runtime)
    reader.dial_ledger.report_failure("unavailable", lost_session("connection refused"))
    return reader


# --------------------------------------------------------------------------- #
# Readiness: a pending route proves itself on the connections it hands over.  #
# --------------------------------------------------------------------------- #


def test_a_pending_reader_proves_each_connection_before_its_role_and_then_serves(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reader_pool = pool_of(ScriptedConnection(), ScriptedConnection())
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")
    reader = reader_route_of(runtime)

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        with reader_context(runtime, "tenant_reader") as scoped:
            scoped.submit("select 1")
        with reader_context(runtime) as scoped:
            scoped.submit("select 2")

    first, second = reader_pool.returned
    assert first.submitted == [PROVE, "authorize tenant_reader", "select 1", RESTORE]
    # Verified now, so a later connection is not proved again.
    assert second.submitted == ["select 2"]
    assert reader.readiness() == "verified"
    notices = resource_records(caplog)
    assert notices[-1] == "the database runtime's reader route was verified and now serves its work"
    assert sum("verified and now serves" in notice for notice in notices) == 1


def test_a_pending_reader_s_proof_spends_the_first_send_before_its_role() -> None:
    # The proof was the lease's first submission, so a role installation that
    # then meets a broken session is not a second opportunity.
    reader_pool = pool_of(_losing_after_probe(), ScriptedConnection())
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")
    resource = reader_context(runtime, "tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert len(reader_pool.budgets) == 1
    assert reader_route_of(runtime).readiness() == "verified"


@pytest.mark.parametrize("setup", [True, False], ids=["begin", "modeled-read"])
def test_a_pending_reader_s_proof_spends_the_first_send_before_later_work(setup: bool) -> None:
    reader_pool = pool_of(_losing_after_probe(), ScriptedConnection())
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")

    with reader_context(runtime) as scoped, pytest.raises(SessionLost):
        scoped.submit("BEGIN" if setup else "select 1", replay_safe=True, setup=setup)

    assert len(reader_pool.budgets) == 1


def test_a_broken_proof_is_replaced_once_and_the_replacement_is_proved() -> None:
    broken = ScriptedConnection(lost=lost_session())
    fresh = ScriptedConnection()
    reader_pool = pool_of(broken, fresh)
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")

    with reader_context(runtime) as scoped:
        scoped.submit("select 1", replay_safe=True)

    assert broken.submitted == [PROVE]
    assert fresh.submitted == [PROVE, "select 1"]
    assert reader_route_of(runtime).readiness() == "verified"


def test_a_proof_lost_beyond_replacement_fails_its_acquisition_as_unavailable() -> None:
    # An outage is not an incompatibility, so the route stays pending for the
    # next acquisition to prove.
    second = lost_session("the replacement was lost too")
    reader_pool = pool_of(
        ScriptedConnection(lost=lost_session()),
        ScriptedConnection(lost=second),
        ScriptedConnection(),
    )
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")
    resource = reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "unavailable"
    assert refused.value.__cause__ is second
    assert refused.value.selection == RouteSelection("reader")
    assert reader_route_of(runtime).readiness() == "pending"
    assert isinstance(resource.cleanup_result, Invalidated)
    with reader_context(runtime):
        pass
    assert reader_route_of(runtime).readiness() == "verified"


def test_a_proof_that_fails_for_an_unknown_reason_changes_no_readiness() -> None:
    failure = RuntimeError("the statement failed")
    reader_pool = pool_of(ScriptedConnection(failure=failure))
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        reader_context(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is failure
    assert reader_route_of(runtime).readiness() == "pending"


def test_a_control_flow_exception_in_a_proof_keeps_its_own_propagation() -> None:
    # The connection is still disposed of, and an interrupt is no evidence
    # about the route, so its readiness is untouched.
    connection = ScriptedConnection(failure=KeyboardInterrupt())
    runtime = routed(pool_of(), pool_of(connection), reader_readiness="pending")
    resource = reader_context(runtime)

    with pytest.raises(KeyboardInterrupt):
        resource.__enter__()

    assert connection.closes == 1 and isinstance(resource.cleanup_result, Invalidated)
    assert reader_route_of(runtime).readiness() == "pending"


def test_a_proof_that_reads_another_login_refuses_the_route_for_good(
    caplog: pytest.LogCaptureFixture,
) -> None:
    other = ScriptedConnection(login="other")
    reader_pool = pool_of(other, ScriptedConnection())
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")
    resource = reader_context(runtime)

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        with pytest.raises(ConnectionAcquisitionError) as refused:
            resource.__enter__()
        with pytest.raises(ConnectionAcquisitionError) as later:
            reader_context(runtime).__enter__()

    assert refused.value.reason == later.value.reason == "preparation_failed"
    mismatch = refused.value.__cause__
    assert isinstance(mismatch, ProbeMismatch) and later.value.__cause__ is mismatch
    # The mismatched connection is disposed of; the later acquisition takes nothing.
    assert other.closes == 1 and isinstance(resource.cleanup_result, Invalidated)
    assert len(reader_pool.budgets) == 1
    assert reader_route_of(runtime).readiness() == "refused"
    assert [sample.readiness for sample in available_samples(runtime)][1] == "refused"
    assert resource_records(caplog)[-1].startswith(
        "the database runtime's reader route was refused"
    )


def test_a_proof_that_succeeds_after_a_concurrent_refusal_admits_nothing() -> None:
    def refuse_meanwhile(_text: str) -> None:
        reader_route_of(runtime).mark_refused(ProbeMismatch("another lease read another login"))

    runtime = routed(
        pool_of(),
        pool_of(ScriptedConnection(on_submit=refuse_meanwhile)),
        reader_readiness="pending",
    )
    resource = reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert str(refused.value.__cause__) == "another lease read another login"
    # The connection itself proved compatible, so it is returned rather than disposed of.
    assert resource.cleanup_result == Returned()
    assert reader_route_of(runtime).readiness() == "refused"


def test_a_route_refused_while_a_checkout_waited_admits_nothing_handed_over() -> None:
    connection = ScriptedConnection()
    reader_pool = pool_of(connection)
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")
    mismatch = ProbeMismatch("another lease read another login")
    reader_pool.on_check_out = whatever_budget(
        lambda: reader_route_of(runtime).mark_refused(mismatch)
    )
    resource = reader_context(runtime, "tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is mismatch
    assert connection.submitted == []
    assert resource.cleanup_result == Returned()


def test_a_mismatch_whose_disposal_is_interrupted_still_refuses_the_route() -> None:
    other = ScriptedConnection(login="other", close_failure=KeyboardInterrupt())
    runtime = routed(pool_of(), pool_of(other), reader_readiness="pending")

    with pytest.raises(KeyboardInterrupt):
        reader_context(runtime).__enter__()

    assert reader_route_of(runtime).readiness() == "refused"


def test_a_transient_proof_failure_never_downgrades_a_concurrently_verified_route() -> None:
    def verify_meanwhile_then_lose(_text: str) -> None:
        reader_route_of(runtime).mark_verified()
        connection.lost = lost_session()

    connection = ScriptedConnection(on_submit=verify_meanwhile_then_lose)
    reader_pool = pool_of(connection, ScriptedConnection(lost=lost_session()))
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError):
        reader_context(runtime).__enter__()

    assert reader_route_of(runtime).readiness() == "verified"


def test_a_mismatch_on_a_verified_route_fails_only_its_own_acquisition() -> None:
    def verify_meanwhile(_text: str) -> None:
        reader_route_of(runtime).mark_verified()

    connection = ScriptedConnection(on_submit=verify_meanwhile, login="other")
    runtime = routed(pool_of(), pool_of(connection), reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        reader_context(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert reader_route_of(runtime).readiness() == "verified"


def test_simultaneous_proofs_each_run_and_the_route_is_verified_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Both connections were handed over while the route was pending, so each
    # proves itself; the first success verifies and the second changes nothing.
    nested: list[Any] = []

    def acquire_meanwhile(text: str) -> None:
        if text == PROVE and not nested:
            inner = reader_context(runtime)
            nested.append(inner)
            with inner:
                pass

    outer = ScriptedConnection(on_submit=acquire_meanwhile)
    inner_connection = ScriptedConnection()
    reader_pool = pool_of(outer, inner_connection)
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME), reader_context(runtime):
        pass

    assert outer.submitted == inner_connection.submitted == [PROVE]
    assert reader_route_of(runtime).readiness() == "verified"
    assert sum("verified and now serves" in notice for notice in resource_records(caplog)) == 1


def test_a_pending_proof_still_spends_the_acquisition_s_own_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    slow = ScriptedConnection(on_submit=lambda _text: setattr(clock, "now", 20.0))
    reader_pool = pool_of(slow)
    runtime = routed(pool_of(), reader_pool, reader_readiness="pending")
    resource = reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert resource.cleanup_result == Returned()
    assert reader_route_of(runtime).readiness() == "verified"


# --------------------------------------------------------------------------- #
# The probe slot: one demand re-dial of a reader known to be unreachable.     #
# --------------------------------------------------------------------------- #


def test_one_acquisition_holds_the_probe_slot_and_concurrent_ones_fall_back_at_once() -> None:
    # Only the holder waits on the reader; whoever arrives meanwhile goes to
    # the writer without queueing on the route that just failed.
    writer_pool = pool_of(ScriptedConnection(), ScriptedConnection())
    reader_pool = pool_of(ScriptedConnection())
    runtime = routed(writer_pool, reader_pool)
    reader = _known_unreachable(runtime)
    concurrent: list[Any] = []

    def recovering(_budget: float) -> None:
        meanwhile = preferred_context(runtime)
        with meanwhile:
            concurrent.append(meanwhile.selection)

    reader_pool.on_check_out = recovering
    holder = preferred_context(runtime)

    with holder:
        pass
    reader_pool.on_check_out = None

    assert concurrent == [RouteSelection("writer", "unavailable")]
    assert len(reader_pool.budgets) == 1
    assert holder.selection == RouteSelection("reader")
    # The holder's checkout cleared the record, and the slot was given back.
    assert reader.dial_ledger.latest_failure is None
    assert reader.claim_probe()
    reader.release_probe()
    with preferred_context(runtime) as scoped:
        scoped.submit("select 1")
    assert len(reader_pool.budgets) == 2


def test_a_reader_with_an_idle_connection_is_tried_whatever_its_record_says() -> None:
    reader_pool = pool_of()
    reader_pool.available = 1
    runtime = routed(pool_of(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        resource = preferred_context(runtime)
        with resource:
            pass
    finally:
        reader.release_probe()

    assert resource.selection == RouteSelection("reader")


def test_a_reader_whose_pool_cannot_be_measured_is_taken_to_hold_no_idle_connection() -> None:
    reader_pool = pool_of(metrics_failure=RuntimeError("the pool's bookkeeping could not be read"))
    runtime = routed(pool_of(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        resource = preferred_context(runtime)
        with resource:
            pass
    finally:
        reader.release_probe()

    assert reader_pool.budgets == []
    assert resource.selection == RouteSelection("writer", "unavailable")


def test_a_probe_holder_falls_back_on_an_outage_recorded_before_its_wait() -> None:
    writer_pool = pool_of()
    reader_pool = pool_of(checkout_failure=checkout_failed("timeout"))
    runtime = routed(writer_pool, reader_pool)
    reader = _known_unreachable(runtime)
    resource = preferred_context(runtime)

    with resource as scoped:
        scoped.submit("select 1")

    assert len(reader_pool.budgets) == 1
    assert writer_pool.returned[0].submitted == ["select 1"]
    assert resource.selection == RouteSelection("writer", "unavailable")
    assert reader.claim_probe()
    reader.release_probe()


def test_a_strict_reader_always_demands_the_reader_whatever_its_record_says() -> None:
    reader_pool = pool_of()
    runtime = routed(pool_of(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        with reader_context(runtime):
            pass
    finally:
        reader.release_probe()

    assert len(reader_pool.budgets) == 1
