"""Parallax Postgres adapter (``parallax-postgres``).

The sole psycopg declarer; the concrete database port wired only at composition
roots. Exports :class:`PostgresAdapter`, the psycopg implementation of the
abstract ``m-db-port``.
"""

from __future__ import annotations

from parallax.postgres.adapter import Json, Jsonb, PostgresAdapter

__all__ = ["Json", "Jsonb", "PostgresAdapter"]
