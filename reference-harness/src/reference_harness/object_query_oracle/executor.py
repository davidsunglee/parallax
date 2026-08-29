"""The read-execution seam an accepted Object Query observation needs.

An observation needs exactly two things from a database: which dialect's golden
SQL to select, and a way to run a read. Provisioning, reset, transaction control,
and session lifecycle belong to whoever supplied the executor, so a provider, a
held transaction session, and a scripted test adapter are all equally valid here
and the oracle cannot tell them apart.

Substitution is by value, never by type: the oracle uses the exact executor it
was handed for every page, Include level, golden query, and reference query of
one operation. That is what lets a Unit Work Scenario read through a held session
so the independent ``referenceSql`` oracle observes the same uncommitted state
the golden read did.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ReadExecutor(Protocol):
    """Everything an accepted read may ask of a database.

    * ``dialect`` — the dialect identifier (e.g. ``"postgres"``) selecting the
      statement entry's ``sql`` dialect key and the sqlglot dialect.
    * ``query(sql, binds)`` — execute a read and return rows as ordered dicts.

    A driver exception raised by ``query`` propagates unchanged: infrastructure
    failure is never reported as a semantic mismatch.
    """

    dialect: str

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]: ...
