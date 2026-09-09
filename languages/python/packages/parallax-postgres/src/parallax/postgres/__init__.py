"""Parallax Postgres adapter (``parallax-postgres``).

The sole psycopg declarer, and the only package that names its companion pool;
the concrete database runtime wired only at composition roots. Exports
:class:`PostgresAdapter` — immutable, resource-free configuration whose ``open``
produces a ready ``m-db-port`` runtime — the two retention policies it is
configured with, and :func:`isolation_spelling`, this engine's name for each
portable Isolation Level. Driver and pool types (``Jsonb``, the native pool, the
psycopg connection) stay internal to the adapter (§8 topology fixes the public
exports).
"""

from __future__ import annotations

from parallax.postgres._isolation import isolation_spelling
from parallax.postgres._options import OnDemandOptions, PoolOptions
from parallax.postgres.adapter import PostgresAdapter

__all__ = ["OnDemandOptions", "PoolOptions", "PostgresAdapter", "isolation_spelling"]
