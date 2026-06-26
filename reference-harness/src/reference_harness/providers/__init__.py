"""The database-provider seam (M12 provisioning sub-part).

A ``DatabaseProvider`` yields a clean, migrated, isolated database for a single
dialect. The runner is written against this protocol only, so adding a dialect
(a later phase adds MariaDB) is a new provider behind the same seam — never a
runner redesign. This is also the seam the compatibility matrix grows along.

Each provider exposes:

* ``dialect`` — the dialect identifier (e.g. ``"postgres"``) selecting the
  ``goldenSql`` key and the sqlglot dialect.
* ``reset()`` — return to a clean, empty state (drop everything).
* ``apply_ddl(statements)`` — run derived ``CREATE TABLE`` DDL.
* ``load(table, columns, rows)`` — bulk-insert fixture rows.
* ``query(sql, binds)`` — execute a read and return rows as ordered dicts.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseProvider(Protocol):
    """The provisioning + execution seam the case runner is written against."""

    dialect: str

    def reset(self) -> None:
        """Drop all objects, returning the database to a clean empty state."""
        ...

    def apply_ddl(self, statements: Sequence[str]) -> None:
        """Execute derived DDL (``CREATE TABLE`` …)."""
        ...

    def load(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        """Bulk-insert fixture rows into *table* (column order matches *columns*)."""
        ...

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run a read query; return rows as dicts keyed by result-column name."""
        ...


# Registry of dialect -> provider factory. Providers register themselves on
# import; selection is by the PARALLAX_DATABASES env var (comma-separated),
# defaulting to all registered providers.
_FACTORIES: dict[str, Any] = {}


def register(dialect: str, factory: Any) -> None:
    _FACTORIES[dialect] = factory


def available_dialects() -> list[str]:
    """Dialects selected for this run (PARALLAX_DATABASES, else all registered)."""
    requested = os.environ.get("PARALLAX_DATABASES", "").strip()
    if requested:
        names = [name.strip() for name in requested.split(",") if name.strip()]
    else:
        names = sorted(_FACTORIES)
    return [name for name in names if name in _FACTORIES]


@contextmanager
def provider_for(dialect: str) -> Iterator[DatabaseProvider]:
    """Context-manage a provider for *dialect* (boots and tears down its container)."""
    if dialect not in _FACTORIES:
        raise KeyError(f"no provider registered for dialect {dialect!r}")
    factory = _FACTORIES[dialect]
    with factory() as provider:
        yield provider


def _register_builtin_providers() -> None:
    # Imported here (not at top) to avoid importing Testcontainers/psycopg unless
    # a provider is actually used. Import side effects call register().
    from . import postgres  # noqa: F401


_register_builtin_providers()
