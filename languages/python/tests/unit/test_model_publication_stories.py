"""The Usage Guide's model publication story, over a fake port.

The story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_model_publication_story.py` executes it against real Postgres so
what is documented is what works. This is the database-free half — the same call
over a fake port, plus the refusals the happy path never reaches — because a
snippet that stopped compiling, or an order that stopped being prepare-apply-
publish, should fail on the first run of the fast suite rather than on the
Docker-backed one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import cast

import pytest

from _support.db_port import body_outcome
from parallax.conformance import model_publication_stories as stories
from parallax.conformance.story_models import ACCOUNT_MODEL, NICKNAMED_ACCOUNT_MODEL
from parallax.core.db_port import (
    BeginFailed,
    Bind,
    CallbackRaised,
    DbPort,
    RollbackFailed,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import DomainModel, model_of
from parallax.evolution import SchemaDelta, evolve
from parallax.snapshot import ServingModel, connect, prepare_model

_ALTER = "alter table account add column nickname varchar(64)"
_CREATE_INDEX = "create unique index "
_ORDERED = ("alter table t add column a int", "create index i on t (a)", "analyze t")


class _AccountPort:
    dialect: Dialect = POSTGRES

    def __init__(self) -> None:
        self.writes: list[str] = []

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[object] = ()
    ) -> list[Row]:
        return [
            {
                "id": 2,
                "owner": "Linus",
                "balance": Decimal("250.00"),
                "version": 1,
                "nickname": None,
            }
        ]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.writes.append(sql)
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return body_outcome(self, body)


class _UnopenablePort(_AccountPort):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return BeginFailed(self.error)


class _RefusingPort(_AccountPort):
    """A port whose ``at``-th statement raises, so the delta stops there with
    every earlier statement already sent."""

    def __init__(self, error: Exception, *, at: int = 0) -> None:
        super().__init__()
        self.error = error
        self.at = at

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        if len(self.writes) == self.at:
            raise self.error
        return super().execute_write(sql, binds)


class _UnrollbackablePort(_AccountPort):
    """A port whose statement fails AND whose undo does not complete, so what
    the database holds is unknown."""

    def __init__(self, trigger: Exception, rollback_error: Exception) -> None:
        super().__init__()
        self.trigger = trigger
        self.rollback_error = rollback_error

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return RollbackFailed(CallbackRaised(self.trigger), self.rollback_error)


def test_the_documented_update_prepares_applies_then_publishes() -> None:
    port = _AccountPort()
    update = stories.a_running_service_publishes_an_evolved_model_without_restarting(port)

    # One handle, never reconnected: what moved is the selection its executions
    # adopt, and the transaction after the publication adopted the later one.
    assert update.before_edition == "2026-09-a"
    assert update.after_edition == "2026-09-b"
    assert update.nickname == "rainy-day"
    # The order is the story: the column exists before anything adopts the
    # edition prepared over it, so both schema statements precede the write that
    # names the new member — and the index follows the column it is over.
    assert port.writes[0] == _ALTER
    assert port.writes[1].startswith(_CREATE_INDEX)
    assert "nickname" in port.writes[2]
    assert len(port.writes) == 3
    assert update.statements == (port.writes[0], port.writes[1])
    # The rollout ledger the host retains: one entry per Index this delta
    # created, carrying the name a later uniqueness violation reports.
    (created,) = update.created_indices
    assert created.unique and created.physical_index_name.value in port.writes[1]


def test_the_same_update_run_backwards_is_not_a_live_publication_path() -> None:
    # Removing the attribute again is a complete description and a Coordinated
    # Evolution: there is no delta to apply and no moment at which one
    # publication would make the two editions agree, so the host refuses before
    # any statement is generated.
    backwards = evolve(model_of(NICKNAMED_ACCOUNT_MODEL), model_of(ACCOUNT_MODEL))
    with pytest.raises(stories.UnpublishableUpdateError, match="Coordinated Evolution"):
        stories.unilateral(backwards)


def test_a_candidate_that_cannot_be_prepared_leaves_the_earlier_edition_serving() -> None:
    # Preparation is the recipe's FIRST step, which is what makes this failure
    # cost nothing: it runs before any statement of a delta is generated, let
    # alone applied, so the database is untouched and the handle connected
    # before the attempt goes on serving the edition it already adopted.
    port = _AccountPort()
    a = prepare_model(ACCOUNT_MODEL, edition="2026-09-a")
    serving = ServingModel(a)
    db = connect(port, serving)

    unpreparable = cast("DomainModel", object())
    with pytest.raises(TypeError, match="Domain Model"):
        prepare_model(unpreparable, edition="2026-09-b")

    assert port.writes == []
    assert serving.current() is a
    assert db.transact(lambda tx: tx.edition) == "2026-09-a"


def test_a_boundary_that_never_opened_stops_the_update_before_it_publishes() -> None:
    failed = RuntimeError("no connection")
    port = _UnopenablePort(failed)
    with pytest.raises(stories.UnpublishableUpdateError, match="never began") as refusal:
        stories.apply_schema_delta(port, SchemaDelta((_ALTER,), ()))

    # The application's own refusal, carrying the database's failure as its
    # cause: nothing was applied, so nothing may be published.
    assert refusal.value.__cause__ is failed
    assert port.writes == []


def test_a_statement_that_did_not_commit_stops_the_update_before_it_publishes() -> None:
    failed = RuntimeError("relation is locked")
    with pytest.raises(stories.UnpublishableUpdateError, match="did not apply in full") as refusal:
        stories.apply_schema_delta(_RefusingPort(failed), SchemaDelta((_ALTER,), ()))

    assert refusal.value.__cause__ is failed


def test_a_multi_statement_delta_stops_at_the_first_failure_having_run_the_prefix() -> None:
    # The consumer contract is positional: every statement before the failing
    # one has already been sent, in the authored order, and nothing after it is
    # attempted. Nothing retries or reorders around the gap — a prefix-safe
    # statement is not an idempotent one.
    failed = RuntimeError("index already exists")
    port = _RefusingPort(failed, at=1)
    with pytest.raises(stories.UnpublishableUpdateError):
        stories.apply_schema_delta(port, SchemaDelta(_ORDERED, ()))

    assert port.writes == [_ORDERED[0]]


def test_the_generated_delta_stopping_partway_publishes_nothing() -> None:
    # The same stop, reached through the story's own generated delta: the index
    # statement fails, so the column change is all that was sent and the write
    # that names the new member never runs.
    port = _RefusingPort(RuntimeError("index already exists"), at=1)
    with pytest.raises(stories.UnpublishableUpdateError):
        stories.a_running_service_publishes_an_evolved_model_without_restarting(port)

    assert port.writes == [_ALTER]


def test_an_undo_that_did_not_complete_is_refused_as_an_unknown_database() -> None:
    # Two live failures, and reporting only the trigger would teach a host that
    # the database is back where it started. It is not: the undo did not run, so
    # the rollback failure is the cause and the trigger is named beside it.
    trigger = RuntimeError("relation is locked")
    rollback_error = RuntimeError("the session is gone")
    port = _UnrollbackablePort(trigger, rollback_error)
    with pytest.raises(stories.UnpublishableUpdateError, match="unknown") as refusal:
        stories.apply_schema_delta(port, SchemaDelta((_ALTER,), ()))

    assert refusal.value.__cause__ is rollback_error
    assert repr(trigger) in str(refusal.value)


def test_the_snippet_the_usage_guide_renders_is_the_source_that_ran() -> None:
    snippet = stories.publication_snippet()
    # Both model endpoints, the refusals, and the update are one story: a
    # snippet showing the three calls alone would document the surface without
    # the order that is the only thing an application has to get right.
    assert "class Account" in snippet
    assert "class NicknamedAccount" in snippet
    assert "class UnpublishableUpdateError" in snippet
    assert "def unilateral" in snippet
    assert "def apply_schema_delta" in snippet
    assert snippet.index("prepare_model(NICKNAMED_ACCOUNT_MODEL") < snippet.index(
        "apply_schema_delta(port, delta)"
    )
    assert snippet.index("apply_schema_delta(port, delta)") < snippet.index(
        "serving.publish(b, expected=a)"
    )
