"""The Usage Guide's model publication story, over a fake port.

The story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_model_publication_story.py` executes it against real Postgres so
what is documented is what works. This is the database-free half — the same call
over a fake port, plus the two refusals the happy path never reaches — because a
snippet that stopped compiling, or an order that stopped being prepare-apply-
publish, should fail on the first run of the fast suite rather than on the
Docker-backed one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

import pytest

from _support.db_port import body_outcome
from parallax.conformance import model_publication_stories as stories
from parallax.conformance.models import accepted_model_of
from parallax.conformance.story_models import ACCOUNT_MODEL, NICKNAMED_ACCOUNT_MODEL
from parallax.core.db_port import (
    BeginFailed,
    Bind,
    DbPort,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.evolution import SchemaDelta, evolve

_ALTER = "alter table account add column nickname varchar(64)"


class _AccountPort:
    """The one seeded row the story renames, and a driver that accepts every
    statement — the schema change and the write alike, in the order they came."""

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
    """A port whose boundary never opens, so no statement of a delta runs."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return BeginFailed(self.error)


class _RefusingPort(_AccountPort):
    """A port whose first statement raises, so the delta stops partway."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        raise self.error


def test_the_documented_update_prepares_applies_then_publishes() -> None:
    port = _AccountPort()
    update = stories.a_running_service_publishes_an_evolved_model_without_restarting(port)

    # One handle, never reconnected: what moved is the selection its executions
    # adopt, and the transaction after the publication adopted the later one.
    assert update.before == "2026-09-a"
    assert update.after == "2026-09-b"
    assert update.statements == (_ALTER,)
    assert update.nickname == "rainy-day"
    # The order is the story: the column exists before anything adopts the
    # edition prepared over it, so the schema change precedes the write that
    # names the new member.
    assert port.writes[0] == _ALTER
    assert "nickname" in port.writes[1]
    assert len(port.writes) == 2


def test_the_same_update_run_backwards_is_not_a_live_publication_path() -> None:
    # Removing the attribute again is a complete description and a Coordinated
    # Evolution: there is no delta to apply and no moment at which one
    # publication would make the two editions agree, so the host refuses before
    # any statement is generated.
    backwards = evolve(accepted_model_of(NICKNAMED_ACCOUNT_MODEL), accepted_model_of(ACCOUNT_MODEL))
    with pytest.raises(stories.UnpublishableUpdateError, match="Coordinated Evolution"):
        stories.unilateral(backwards)


def test_a_boundary_that_never_opened_stops_the_update_before_it_publishes() -> None:
    failed = RuntimeError("no connection")
    port = _UnopenablePort(failed)
    with pytest.raises(stories.UnpublishableUpdateError) as refusal:
        stories.apply_schema_delta(port, SchemaDelta((_ALTER,), ()))

    # The application's own refusal, carrying the database's failure as its
    # cause: nothing was applied, so nothing may be published.
    assert refusal.value.__cause__ is failed
    assert port.writes == []


def test_a_statement_that_did_not_commit_stops_the_update_before_it_publishes() -> None:
    failed = RuntimeError("relation is locked")
    with pytest.raises(stories.UnpublishableUpdateError) as refusal:
        stories.apply_schema_delta(_RefusingPort(failed), SchemaDelta((_ALTER,), ()))

    assert refusal.value.__cause__ is failed


def test_the_snippet_the_usage_guide_renders_is_the_source_that_ran() -> None:
    snippet = stories.publication_snippet()
    # The later model, the refusals, and the update are one story: a snippet
    # showing the three calls alone would document the surface without the
    # order that is the only thing an application has to get right.
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
