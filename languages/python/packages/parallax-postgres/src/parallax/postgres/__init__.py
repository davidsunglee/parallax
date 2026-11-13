"""Connect Parallax to PostgreSQL."""

from __future__ import annotations

from parallax.postgres._adapter import PostgresAdapter
from parallax.postgres._authorization import PostgresRole
from parallax.postgres._binding import (
    PostgresBinding,
    PostgresLocation,
    PostgresSequence,
    PostgresTable,
)
from parallax.postgres._endpoint import PostgresEndpoint
from parallax.postgres._isolation import isolation_spelling
from parallax.postgres._options import OnDemandOptions, PoolOptions

__all__ = [
    "OnDemandOptions",
    "PoolOptions",
    "PostgresAdapter",
    "PostgresBinding",
    "PostgresEndpoint",
    "PostgresLocation",
    "PostgresRole",
    "PostgresSequence",
    "PostgresTable",
    "isolation_spelling",
]
