"""The `m-db-port` / `m-dialect` seam: a port reports the dialect it executes in.

Docker-free. What it pins is the binding itself rather than any dialect rule
(``tests/dialect/`` owns those): that the concrete adapter states its dialect as
class-level metadata reachable before a connection exists, that a decorating port
reports the dialect of the port it stands in for — including the copy it re-wraps
around a transaction-scoped port — and that a connection compiles against the
dialect its own port declares rather than one chosen beside it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest
from _second_dialect import BACKTICKED
from _transact_support import ACCOUNT

from _support import mirrored_models as mm
from _support.db_port import body_outcome
from parallax.conformance import engine
from parallax.conformance.boundary_runner import FaultInjectingPort
from parallax.core.db_port import DbPort, DeclaresDialect, DocumentReadOrdinals, Row
from parallax.core.db_port import TransactionOutcome as Outcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres import PostgresAdapter
from parallax.snapshot import connect

_ACCOUNT_ROW: Row = {"id": 7, "owner": "Ada", "balance": Decimal("1.00"), "version": 1}


class _SpellingPort:
    """A port answering one canned row and recording the SQL it was handed."""

    def __init__(self, dialect: Dialect) -> None:
        self.dialect = dialect
        self.statements: list[str] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del binds, document_reads
        self.statements.append(sql)
        return [dict(_ACCOUNT_ROW)]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del binds
        self.statements.append(sql)
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> Outcome[T]:
        del isolation
        return body_outcome(self, body)


def test_the_postgres_adapter_declares_its_dialect_as_class_level_metadata() -> None:
    # No instance, so no connection: a composition root can resolve which SQL
    # spelling an adapter executes in before it opens anything.
    declaring: type[DeclaresDialect] = PostgresAdapter
    assert declaring.dialect is POSTGRES
    assert PostgresAdapter.dialect is POSTGRES


def test_a_fault_injecting_port_reports_the_dialect_of_the_port_it_decorates() -> None:
    inner = _SpellingPort(BACKTICKED)
    decorator = FaultInjectingPort(inner, fault=None, persistent=False)
    assert decorator.dialect is BACKTICKED


def test_a_fault_injecting_port_preserves_the_dialect_through_its_own_re_wrap() -> None:
    # The decorator wraps the transaction-scoped port its inner port hands the
    # body, so the dialect a body reads is still the one that will execute its
    # statements rather than a default the copy invented.
    inner = _SpellingPort(BACKTICKED)
    decorator = FaultInjectingPort(inner, fault=None, persistent=False)
    outcome = decorator.transaction(lambda conn: conn.dialect)
    assert getattr(outcome, "value", None) is BACKTICKED


def test_an_aborting_port_reports_the_dialect_of_the_port_it_decorates() -> None:
    inner = _SpellingPort(BACKTICKED)
    decorator = engine._AbortingPort(inner)  # pyright: ignore[reportPrivateUsage] - the case-only decorator's own seam
    assert decorator.dialect is BACKTICKED


def test_a_connection_compiles_against_the_dialect_its_own_port_declares() -> None:
    port = _SpellingPort(BACKTICKED)
    connect(port, ACCOUNT).find(mm.Account.where(mm.Account.id == 7)).result()
    (statement,) = port.statements
    assert "t0.`id`" in statement
    assert '"' not in statement


def test_two_connections_over_one_model_execute_in_their_own_ports_dialects() -> None:
    # Nothing beside the port selects the spelling, so one model served by two
    # ports produces two spellings without either connection being configured.
    postgres_port = _SpellingPort(POSTGRES)
    backticked_port = _SpellingPort(BACKTICKED)
    query = mm.Account.where(mm.Account.id == 7)
    connect(postgres_port, ACCOUNT).find(query).result()
    connect(backticked_port, ACCOUNT).find(query).result()
    assert "`" not in postgres_port.statements[0]
    assert "t0.`id`" in backticked_port.statements[0]


def test_connecting_with_an_obsolete_dialect_keyword_is_refused() -> None:
    # No alias and no mismatch check: the pair collapsed, so naming a dialect
    # beside a port is an unrecognized argument like any other.
    with pytest.raises(TypeError, match="dialect"):
        cast("Any", connect)(_SpellingPort(POSTGRES), ACCOUNT, dialect=POSTGRES)
