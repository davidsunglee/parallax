"""The Usage Guide's root-options story, over a fake port.

The story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_database_options.py` executes it against real Postgres so what
is documented is what works. This is the database-free half — the same call
over a scripted port — so a snippet that stopped compiling, or a root record
that stopped reaching the transactions opened through it, fails on the first
run of the fast suite rather than on the Docker-backed one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from parallax.conformance import database_options_stories
from parallax.conformance.class_models import MODELS
from parallax.core.db_port import Bind, DatabaseConnection, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.snapshot import DatabaseOptions
from tests._support.db_port import ConnectsAsItself, body_outcome

_story = (
    database_options_stories.a_root_default_is_overridden_per_call_and_a_join_inherits_the_override
)


class _AccountPort(ConnectsAsItself):
    """The one seeded row the story reads, recording the level each boundary asked for."""

    dialect: Dialect = POSTGRES

    def __init__(self) -> None:
        self.levels: list[str | None] = []

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[object] = ()
    ) -> list[Row]:
        return [(2, "Linus", Decimal("250.00"), 1)]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        raise AssertionError("the story writes nothing")

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        self.levels.append(isolation)
        return body_outcome(self, body)


def test_the_documented_root_options_story_resolves_each_call_as_it_states() -> None:
    port = _AccountPort()
    shape = _story(port, MODELS["account"])
    root = DatabaseOptions(isolation="repeatable_read", max_retries=2)
    # The call that requested nothing ran under the root's own record; the call
    # that overrode one field kept the other three; and both joins answered the
    # OUTER call's resolved record — never the root's — while the join naming
    # the root's level was refused.
    assert shape.inherited == root
    assert shape.overridden == DatabaseOptions(isolation="serializable", max_retries=2)
    assert shape.joined == shape.overridden
    assert shape.repeated == shape.overridden
    assert shape.root_level_refused_on_join
    assert shape.balance == Decimal("250.00")
    # Two physical boundaries, each opened at the level its invocation resolved;
    # the three joining calls opened none of their own.
    assert port.levels == ["repeatable_read", "serializable"]


def test_the_snippet_the_usage_guide_renders_is_the_source_that_ran() -> None:
    snippet = database_options_stories.root_options_snippet()
    assert "DatabaseOptions(isolation=" in snippet
    assert "connect(adapter, model, options=root)" in snippet
    assert "tx.options" in snippet
    assert 'isolation="serializable"' in snippet
    assert "TransactionOptionConflictError" in snippet
