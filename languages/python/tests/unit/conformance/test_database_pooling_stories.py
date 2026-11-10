"""The PostgreSQL lifecycle guide's stories, over a scripted adapter.

`tests/api/test_database_pooling.py` runs the stories against real Postgres.
What is checked here is what the scripted adapter records: the route policy
each scope requests, the thread a handle is opened on, and that each story
closes every runtime it opened.
"""

from __future__ import annotations

import asyncio
import threading
from decimal import Decimal

from parallax.conformance import database_pooling_stories as stories
from parallax.conformance.story_models import ACCOUNT_MODEL
from parallax.core.internal.execution import (
    ServingModel,
    prepare_model,
)
from tests._support.db_port import Read, ScriptedAdapter, ScriptedRuntime

_ROW = {"id": 1, "owner": "Newton", "balance": Decimal("10.00"), "version": 1}


def test_each_routed_scope_requests_the_policy_its_story_names() -> None:
    adapter = ScriptedAdapter(Read(rows=[_ROW], times=3), routes=("writer", "reader"))

    balances = stories.each_scope_reads_where_its_policy_says(adapter, ACCOUNT_MODEL)

    assert balances == stories.RoutedBalances(
        [Decimal("10.00")], [Decimal("10.00")], [Decimal("10.00")]
    )
    assert adapter.requested_policies == ["reader_only", "writer_only", "reader_preferred"]
    assert adapter.closes == 1


def test_both_model_forms_close_the_runtime_each_opened() -> None:
    # One connection closed by leaving its scope and one closed explicitly: two
    # runtimes opened, two closed.
    adapter = ScriptedAdapter(Read(rows=[_ROW], times=2))

    stories.a_handle_is_closed_by_leaving_its_scope_or_by_closing_it(
        adapter, ACCOUNT_MODEL, ServingModel(prepare_model(ACCOUNT_MODEL, edition="published"))
    )

    assert adapter.closes == 2


def test_two_handles_over_one_configuration_each_close_their_own_runtime() -> None:
    adapter = ScriptedAdapter(Read(rows=[_ROW], times=2))

    stories.one_configuration_opens_independent_runtimes(adapter, ACCOUNT_MODEL)

    assert adapter.closes == 2


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
