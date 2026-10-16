"""The Usage Guide's read-only story, over a fake port.

The story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_read_only_transactions.py` executes it against real Postgres.
This is the database-free half — the same call over a scripted port — so a
snippet that stopped compiling, or a read-only request that stopped reaching
the boundary, fails on the first run of the fast suite.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from parallax.conformance import read_only_stories
from parallax.conformance.class_models import MODELS
from parallax.core.db_port import Bind, DatabaseConnection, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution import ReadOnlyTxnOptions
from tests._support.db_port import ConnectsAsItself, body_outcome


class _AccountPort(ConnectsAsItself):
    """The one seeded row the story reads, recording what each boundary asked for
    and each statement it ran."""

    dialect: Dialect = POSTGRES

    def __init__(self) -> None:
        self.boundaries: list[tuple[str | None, str | None]] = []
        self.statements: list[str] = []

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[object] = ()
    ) -> list[Row]:
        self.statements.append(sql)
        return [(2, "Linus", Decimal("250.00"), 1)]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        raise AssertionError("the story writes nothing")

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        self.boundaries.append((isolation, access_mode))
        return body_outcome(self, body)


def test_the_documented_read_only_story_opens_one_read_only_boundary() -> None:
    port = _AccountPort()
    report = read_only_stories.reads_run_in_one_read_only_transaction_at_a_chosen_isolation(
        port, MODELS["account"]
    )
    assert report.options == ReadOnlyTxnOptions(max_retries=10, isolation="repeatable_read")
    assert report.balance == report.reread_balance == Decimal("250.00")
    assert report.read_only_join_shared_the_context
    assert report.writable_join_refused
    # One physical boundary, read-only at the level the call named: the joined
    # call opened none, and the refused writable call reached nothing.
    assert port.boundaries == [("repeatable_read", "read_only")]
    assert len(port.statements) == 2
    assert not any("for share" in statement for statement in port.statements)


def test_the_snippet_the_usage_guide_renders_is_the_source_that_ran() -> None:
    snippet = read_only_stories.read_only_snippet()
    assert 'db.read_only(report, isolation="repeatable_read")' in snippet
    assert "rtx.find(query)" in snippet
    assert "TransactionAccessModeError" in snippet
