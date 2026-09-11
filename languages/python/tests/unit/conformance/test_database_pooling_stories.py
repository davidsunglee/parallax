"""The PostgreSQL lifecycle guide's stories, over a scripted adapter.

The guide's blocks are these functions' own source and
`tests/api/test_database_pooling.py` runs them against real Postgres. This is
the database-free half, for the same reason every story has one: a documented
spelling that stopped compiling, a Provider that stopped being offered a source,
or a lifespan that stopped closing its handle should fail on the first run of the
fast suite rather than on the Docker-backed one.

What a real pool MEASURES is not provable here and is not attempted — the
scripted source answers a constant. What is provable here is the shape around
it: who is offered the source, when the registration is closed, and what a
handle's close does to the source it published.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence
from decimal import Decimal
from uuid import uuid4

import pytest

from parallax.conformance import database_pooling_stories as stories
from parallax.conformance.story_models import ACCOUNT_MODEL
from parallax.core.db_port import Bind, DocumentReadOrdinals, Row
from parallax.core.diagnostics import diagnostic_for
from parallax.core.execution_lifecycle import ExecutionLifecycleHandlerError
from parallax.postgres import OnDemandOptions, PoolOptions
from parallax.snapshot import ServingModel, prepare_model
from parallax.snapshot.handle import ExecutionFailure
from tests._support.db_port import Read, ScriptedAdapter, ScriptedRuntime
from tests.unit._pool_source_support import DetachableSource

_ROW = {"id": 1, "owner": "Newton", "balance": Decimal("10.00"), "version": 1}


def test_the_documented_retention_forms_are_the_four_the_guide_distinguishes() -> None:
    # The guide's construction block is a claim about which four policies exist
    # and what each one retains, so what is graded here is the policy each form
    # carries rather than that four adapters were built.
    forms = stories.every_retention_form_is_one_configuration_value("postgresql://localhost/app")

    assert forms.default.pool == PoolOptions()
    assert forms.tuned.pool == PoolOptions(min_size=2, max_size=20)
    assert forms.zero_minimum.pool == PoolOptions(min_size=0, max_size=20)
    assert forms.on_demand.pool == OnDemandOptions(max_size=20)


def test_both_model_forms_connect_and_both_closes_give_the_runtime_back() -> None:
    # Two connections over one adapter, one closed by leaving its scope and one
    # closed explicitly: two runtimes opened, two closed, and the Serving Model
    # an application prepared serves what the shorthand does.
    adapter = ScriptedAdapter(Read(rows=[_ROW], times=2))

    shape = stories.a_handle_is_closed_by_leaving_its_scope_or_by_closing_it(
        adapter, ACCOUNT_MODEL, ServingModel(prepare_model(ACCOUNT_MODEL, edition="published"))
    )

    assert shape == stories.ClosedBothWays(scoped_rows=1, explicit_rows=1)
    assert adapter.closes == 2


def test_two_handles_over_one_configuration_serve_independently() -> None:
    # One script, two runtimes: the second handle reads after the first has
    # closed, which it could only do on a runtime of its own.
    adapter = ScriptedAdapter(Read(rows=[_ROW], times=2))

    shape = stories.one_configuration_opens_independent_runtimes(adapter, ACCOUNT_MODEL)

    assert shape == stories.RetentionShape(1, 1)
    assert adapter.closes == 2


def test_the_pool_watch_is_offered_the_source_and_closed_with_the_handle() -> None:
    source = DetachableSource()
    adapter = ScriptedAdapter(Read(rows=[_ROW]), Read(rows=[]), metrics=source)

    reading = stories.the_pool_reports_its_own_capacity_and_stops_when_the_handle_closes(
        adapter, ACCOUNT_MODEL
    )

    assert reading.at_rest.managed == source.measurements.pool_size
    assert reading.while_working.idle == source.measurements.pool_available
    # The handle closed, so the runtime detached its source and then the
    # registration was given up — both, and in that order.
    assert reading.detached_after_close
    assert reading.registration_closed


def test_a_watch_reports_nothing_rather_than_a_zero_for_a_reading_it_could_not_take() -> None:
    # Unavailable and detached are both "no reading" to an exporter, and neither
    # is a measured zero it should publish.
    detached = DetachableSource()
    detached.detach()

    assert stories.PoolWatch(detached).read() is None


def test_the_pool_watching_provider_answers_the_reporter_half_of_the_seam() -> None:
    # It declines every root, so it opens no Handler and no Handler failure can
    # ever be reported to it. The method is here because the composition seam is
    # one Protocol with two methods and a Provider does not implement half of
    # it — so what is pinned is that it is total and reports nothing.
    error = ExecutionLifecycleHandlerError(
        execution_id=uuid4(),
        sequence=1,
        activity_id=1,
        handler_type="tests.unit.NothingThisProviderOpened",
        fanout_path=(),
        diagnostic=diagnostic_for(RuntimeError("a handler this provider never opened")),
    )

    assert stories.PoolWatchingProvider().report_handler_error(error) is None


def test_the_lifespan_yields_a_working_handle_and_closes_it_at_shutdown() -> None:
    adapter = ScriptedAdapter(Read(rows=[_ROW]))
    escaped: list[object] = []

    async def scenario() -> list[Decimal]:
        async with stories.pooled_database(adapter, ACCOUNT_MODEL) as db:
            escaped.append(db)
            return await stories.serve_account_balances(db)

    balances = asyncio.run(scenario())

    assert balances == [Decimal("10.00")]
    assert adapter.closes == 1
    with pytest.raises(ExecutionFailure):
        stories.account_balances(escaped[0])  # pyright: ignore[reportArgumentType] - the handle the lifespan yielded, deliberately used after its own shutdown


def test_the_offloaded_operation_runs_on_a_thread_that_is_not_the_event_loop_s() -> None:
    # The boundary the guide's advice rests on: an operation offloaded whole
    # runs its statements somewhere other than the loop. Which thread each
    # statement was issued on is the handshake — no timing is involved.
    issued: list[int] = []

    class _Recording(ScriptedAdapter):
        def execute(
            self,
            sql: str,
            binds: Sequence[Bind],
            document_reads: Sequence[DocumentReadOrdinals] = (),
        ) -> list[Row]:
            issued.append(threading.get_ident())
            return super().execute(sql, binds, document_reads)

    adapter = _Recording(Read(rows=[_ROW]))

    async def scenario() -> int:
        async with stories.pooled_database(adapter, ACCOUNT_MODEL) as db:
            await stories.serve_account_balances(db)
            return threading.get_ident()

    loop_thread = asyncio.run(scenario())

    assert issued
    assert loop_thread not in issued


def test_the_lifespan_opens_the_handle_off_the_loop_as_well() -> None:
    # Composition blocks — it opens the pool and proves it can execute — so it
    # is offloaded too. The scripted adapter records the thread its `open` ran
    # on, which is the only way to tell from outside.
    opened: list[int] = []

    class _Recording(ScriptedAdapter):
        def open(self) -> ScriptedRuntime:
            opened.append(threading.get_ident())
            return super().open()

    adapter = _Recording()

    async def scenario() -> int:
        async with stories.pooled_database(adapter, ACCOUNT_MODEL):
            return threading.get_ident()

    loop_thread = asyncio.run(scenario())

    assert opened
    assert loop_thread not in opened
