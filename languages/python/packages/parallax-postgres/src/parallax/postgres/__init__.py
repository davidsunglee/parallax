"""Parallax Postgres adapter (``parallax-postgres``).

The sole psycopg declarer; the concrete database port wired only at composition
roots. Exports :class:`PostgresAdapter`, the psycopg implementation of the
abstract ``m-db-port``, and :func:`isolation_spelling`, this engine's name for
each portable Isolation Level — psycopg bind types (``Jsonb``) stay
internal to the adapter (§8 topology fixes the public exports).
"""

from __future__ import annotations

from parallax.postgres._isolation import isolation_spelling
from parallax.postgres.adapter import PostgresAdapter

__all__ = ["PostgresAdapter", "isolation_spelling"]
