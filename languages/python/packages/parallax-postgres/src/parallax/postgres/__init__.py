"""Parallax Postgres adapter (``parallax-postgres``).

The sole psycopg declarer; the concrete database port wired only at composition
roots. Exports :class:`PostgresAdapter`, the psycopg implementation of the
abstract ``m-db-port`` — and nothing else: psycopg bind types (``Jsonb``) stay
internal to the adapter (§8 topology fixes the public export as ``PostgresAdapter``).
"""

from __future__ import annotations

from parallax.postgres.adapter import PostgresAdapter

__all__ = ["PostgresAdapter"]
