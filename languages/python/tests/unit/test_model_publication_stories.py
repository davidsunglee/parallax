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
from typing import Any

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
from parallax.core.dialect import POSTGRES, Dialect, PhysicalIndexName
from parallax.core.entity import GraphConstructionError, model_of
from parallax.core.entity import _graph_construction as graph_construction_module
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import EntityIdentity, IndexIdentity, Table
from parallax.evolution import CreatedIndex, SchemaDelta, evolve
from parallax.snapshot import ModelSelection, ServingModel, connect
from parallax.snapshot.handle import Database

_ALTER = "alter table account add column nickname varchar(64)"
_ORDERED = ("alter table t add column a int", "create index i on t (a)", "analyze t")
_ROLLOUT_INDEX = CreatedIndex(
    physical_index_name=PhysicalIndexName("pxi_account_nickname_0"),
    physical_table=Table(name="account"),
    logical_index_identity=IndexIdentity(
        EntityIdentity("parallax.compatibility", "Account"), "accountNickname"
    ),
    unique=True,
)


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

    def __init__(self, error: BaseException, *, at: int = 0) -> None:
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

    def __init__(self, trigger: BaseException, rollback_error: Exception) -> None:
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
    # edition prepared over it, so the schema statement precedes the write that
    # names the new member.
    assert port.writes[0] == _ALTER
    assert "nickname" in port.writes[1]
    assert len(port.writes) == 2
    assert update.statements == (port.writes[0],)
    # One added Attribute creates no Index, so the rollout ledger this update
    # retains is empty rather than absent.
    assert update.created_indices == ()


def test_the_same_update_run_backwards_is_not_a_live_publication_path() -> None:
    # Removing the attribute again is a complete description and a Coordinated
    # Evolution: there is no delta to apply and no moment at which one
    # publication would make the two editions agree, so the host refuses before
    # any statement is generated.
    backwards = evolve(model_of(NICKNAMED_ACCOUNT_MODEL), model_of(ACCOUNT_MODEL))
    with pytest.raises(stories.UnpublishableUpdateError, match="Coordinated Evolution"):
        stories.unilateral(backwards)


def test_a_candidate_that_cannot_be_prepared_leaves_the_earlier_edition_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Preparation is the recipe's FIRST step, which is what makes this failure
    # cost nothing: every fallible model-only derivation runs there, before any
    # statement of a delta is generated, let alone applied. The failure is
    # driven through the recipe itself, so what is graded is the recipe's order
    # rather than the surface's — the database is untouched, the holder is
    # unmoved, and the next execution of the handle the recipe connected before
    # the attempt still adopts A.
    #
    # The candidate is the story's own later model and the derivation that fails
    # is a real one — its graph construction, refusing for that model alone
    # because a Domain Model that composes at all is one every derivation
    # accepts, and A's preparation must reach the recipe unharmed.
    port = _AccountPort()
    connected: list[tuple[ServingModel, ModelSelection, Database]] = []

    def connect_and_hold(adapter: DbPort, serving: ServingModel) -> Database:
        db = connect(adapter, serving)
        connected.append((serving, serving.current(), db))
        return db

    candidate = model_of(NICKNAMED_ACCOUNT_MODEL)
    derive_entity_facts = graph_construction_module._entity_facts  # pyright: ignore[reportPrivateUsage] - the real derivation this refusal stands in front of

    def refuse_the_candidate(cataloged: CatalogedModel, *derivation: Any) -> Any:
        if cataloged.meta is candidate:
            raise GraphConstructionError(
                code="entity-graph-layout-mismatch",
                message="the candidate's per-Entity facts could not be derived",
            )
        return derive_entity_facts(cataloged, *derivation)

    monkeypatch.setattr(stories, "connect", connect_and_hold)
    monkeypatch.setattr(graph_construction_module, "_entity_facts", refuse_the_candidate)

    with pytest.raises(GraphConstructionError):
        stories.a_running_service_publishes_an_evolved_model_without_restarting(port)

    ((serving, a, db),) = connected
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


def test_the_generated_delta_that_did_not_apply_publishes_nothing() -> None:
    # The same stop, reached through the story's own generated delta: the column
    # statement fails, so nothing reached the database and the write that names
    # the new member — the one an adopted later edition would make — never runs.
    port = _RefusingPort(RuntimeError("relation is locked"))
    with pytest.raises(stories.UnpublishableUpdateError):
        stories.a_running_service_publishes_an_evolved_model_without_restarting(port)

    assert port.writes == []


def test_the_delta_s_index_provenance_is_what_the_applying_host_is_handed_back() -> None:
    # The rollout ledger is the delta's own: a host that applied the statements
    # holds the entries to correlate a later uniqueness violation against, by the
    # Physical Index Name each carries. The story's own evolution creates no
    # Index, so the provenance is graded over a delta constructed here.
    port = _AccountPort()
    delta = SchemaDelta(
        ("create unique index pxi_account_nickname_0 on account (nickname)",), (_ROLLOUT_INDEX,)
    )
    assert stories.apply_schema_delta(port, delta) == (_ROLLOUT_INDEX,)
    assert port.writes == list(delta.statements)


def test_a_fatal_trigger_stays_primary_rather_than_becoming_a_refusal() -> None:
    # A control-flow failure is not an ordinary one: wrapping an interrupt in the
    # application's refusal would let a host catch a shutdown in progress and
    # report it as a schema delta that did not apply.
    interrupted = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt) as fatal:
        stories.apply_schema_delta(_RefusingPort(interrupted), SchemaDelta((_ALTER,), ()))
    assert fatal.value is interrupted

    # The same, with the undo failing too: the interrupt is still primary and
    # carries the rollback failure as its cause.
    rollback_error = RuntimeError("the session is gone")
    port = _UnrollbackablePort(interrupted, rollback_error)
    with pytest.raises(KeyboardInterrupt) as unrollbackable:
        stories.apply_schema_delta(port, SchemaDelta((_ALTER,), ()))
    assert unrollbackable.value is interrupted
    assert unrollbackable.value.__cause__ is rollback_error


def test_an_undo_that_did_not_complete_is_refused_as_an_unknown_database() -> None:
    # Two live failures, and reporting only the trigger would teach a host that
    # the database is back where it started. It is not: the undo did not
    # complete, so how much of it ran is unknown, the rollback failure is the
    # cause, and BOTH errors survive as objects a host can inspect rather than
    # as text it would have to parse.
    trigger = RuntimeError("relation is locked")
    rollback_error = RuntimeError("the session is gone")
    port = _UnrollbackablePort(trigger, rollback_error)
    with pytest.raises(stories.UnpublishableUpdateError, match="unknown") as refusal:
        stories.apply_schema_delta(port, SchemaDelta((_ALTER,), ()))

    assert refusal.value.__cause__ is rollback_error
    assert refusal.value.triggering_error is trigger
    assert refusal.value.rollback_error is rollback_error


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
