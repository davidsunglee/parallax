"""``parallax.core.db_port`` enforcement scope (m-db-port).

The abstract runtime database port: the execution interface the layers above the
seam call to run compiled SQL and demarcate transactions. It names
``execute`` (row-oriented), ``execute_write`` (affected-row count), and
``transaction`` (callback) — and nothing more. The port depends on nothing
application-specific (no driver, no concrete database), so any layer may hold it
without acquiring a database dependency. Concrete adapters (`parallax.postgres`)
implement it at the composition root and carry the normalize-at-boundary contract:
rows come back as managed values, never raw driver representations.
``m-db-port`` depends only on ``m-core``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["Bind", "DbPort", "JsonDocument", "Row"]

# A neutral bind value (m-core scalars) or the language's managed carriers.
Bind = object
# A managed result row: attribute/column name -> managed value.
Row = dict[str, object]


@dataclass(frozen=True, slots=True)
class JsonDocument:
    """A neutral managed carrier for a ``json`` (value-object document) bind.

    Above-seam code (fixture provisioning, the write path) wraps a
    structured-document value in this carrier rather than a driver-specific bind
    type; the concrete adapter recognizes it at its boundary and hands the driver
    its native structured-document bind (psycopg ``Jsonb``, …). Keeping the carrier
    neutral is what lets a concrete adapter own its driver's bind mechanics without
    leaking them into the developer surface (m-db-port: managed carriers only).
    """

    value: object


@runtime_checkable
class DbPort(Protocol):
    """The abstract database execution port (m-db-port)."""

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        """Run a row-returning statement and return managed rows."""
        ...

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        """Run a DML statement and return the driver's affected-row count."""
        ...

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        """Run ``body`` inside one database transaction, committing on success."""
        ...
