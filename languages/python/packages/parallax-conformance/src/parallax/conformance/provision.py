"""Self-managed provisioning (spec §6, m-conformance-adapter ``self-managed``).

The simple reset path — the only path in v1 (ledger D-4): one session-scoped
Testcontainers Postgres pinned to :data:`~parallax.conformance.constants.POSTGRES_IMAGE`,
and per case ``DROP SCHEMA … CASCADE`` → ``CREATE SCHEMA`` → descriptor-derived
DDL (``applyDdl``) → fixture rows in descriptor column order (``loadFixtures``).

DDL and fixture *statement generation* is pure (``schema_statements`` /
``fixture_statements``) and unit-tested without Docker; the container lifecycle
and driver execution live behind :class:`Provisioner`, proven by the Docker
provider / conformance lanes.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml

from parallax.conformance import case_format
from parallax.core.db_port import DbPort, JsonDocument
from parallax.core.descriptor import Entity, Metamodel, column_order
from parallax.core.dialect import POSTGRES, Dialect

if TYPE_CHECKING:
    from parallax.postgres import PostgresAdapter

__all__ = [
    "Provisioner",
    "fixture_statements",
    "load_fixtures",
    "reset_statements",
    "schema_statements",
]


def reset_statements() -> list[str]:
    """The per-case schema reset (drop then recreate the public schema)."""
    return ["drop schema if exists public cascade", "create schema public"]


def _tables(meta: Metamodel) -> list[tuple[Entity, str]]:
    return [(entity, entity.table) for entity in meta.entities if entity.table is not None]


def schema_statements(meta: Metamodel, dialect: Dialect = POSTGRES) -> list[str]:
    """Descriptor-derived ``create table`` DDL for every row-owning table.

    A table is created once even when several entities map to it (the
    table-per-hierarchy shared table). Merging the full shared-table column set
    and the tag column is deferred with inheritance provisioning (COR-3 Phase 6+);
    the Phase-5 run lane provisions non-inheritance models only.
    """
    statements: list[str] = []
    seen_tables: set[str] = set()
    for entity, table in _tables(meta):
        if table in seen_tables:
            continue
        seen_tables.add(table)
        columns: list[str] = []
        pk_columns: list[str] = []
        for attribute in entity.attributes:
            column_type = dialect.column_type(attribute.type, attribute.max_length)
            columns.append(f"{dialect.quote(attribute.column)} {column_type}")
            if attribute.primary_key:
                pk_columns.append(dialect.quote(attribute.column))
        for value_object in entity.value_objects:
            columns.append(f"{dialect.quote(value_object.column)} jsonb")
        if pk_columns:
            columns.append(f"primary key ({', '.join(pk_columns)})")
        statements.append(f"create table {dialect.quote(table)} ({', '.join(columns)})")
    return statements


def fixture_statements(
    meta: Metamodel, fixtures: Mapping[str, object], dialect: Dialect = POSTGRES
) -> list[tuple[str, list[object]]]:
    """``insert`` statements for the model's fixtures, in descriptor column order.

    Columns and binds follow the descriptor ``column_order`` derivation (the same
    canonical physical order DDL and row-write lowering use), never the fixture
    mapping's key order — so re-spelling a fixture row with permuted keys emits
    byte-identical SQL (python.md §6 ``loadFixtures``). A physical column with no
    member in the row (an omitted nullable, or the inheritance tag column) is
    skipped, so only authored members bind.
    """
    statements: list[tuple[str, list[object]]] = []
    for entity, table in _tables(meta):
        rows = fixtures.get(entity.name)
        if not isinstance(rows, list):
            continue
        # column -> (member name, is-value-object) for the row-order resolution.
        member_by_column: dict[str, tuple[str, bool]] = {
            attr.column: (attr.name, False) for attr in entity.attributes
        }
        member_by_column.update((vo.column, (vo.name, True)) for vo in entity.value_objects)
        for row in cast("list[object]", rows):
            if not isinstance(row, Mapping):
                continue
            member_row = cast("Mapping[str, object]", row)
            columns: list[str] = []
            binds: list[object] = []
            for column in column_order(entity):
                member = member_by_column.get(column)
                if member is None:  # pragma: no cover - inheritance provisioning is COR-3 Phase 6+
                    continue  # a table-per-hierarchy tag column has no fixture member
                name, is_value_object = member
                if name not in member_row:
                    continue  # fixture omits this (nullable) column
                columns.append(dialect.quote(column))
                value = member_row[name]
                binds.append(JsonDocument(value) if is_value_object else value)
            placeholders = ", ".join("?" for _ in columns)
            column_list = ", ".join(columns)
            sql = f"insert into {dialect.quote(table)} ({column_list}) values ({placeholders})"
            statements.append((sql, binds))
    return statements


def load_fixtures(model_ref: str) -> dict[str, object]:
    """Load the sibling fixture rows for a model reference (empty when absent)."""
    root = case_format.find_repo_root()
    stem = Path(model_ref).stem
    fixture_path = root / "core" / "compatibility" / "fixtures" / f"{stem}.yaml"
    if not fixture_path.exists():
        return {}
    loaded = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):  # pragma: no cover - defensive: corpus fixtures are maps
        return {}
    return dict(cast("Mapping[str, object]", loaded))


class Provisioner:  # pragma: no cover - exercised by the Docker provider / conformance lanes
    """A session-scoped Testcontainers Postgres with the simple per-case reset path."""

    def __init__(self) -> None:
        from testcontainers.postgres import PostgresContainer

        from parallax.conformance import constants
        from parallax.postgres import PostgresAdapter

        self._container = PostgresContainer(constants.POSTGRES_IMAGE)
        self._container.start()
        self._conninfo = self._container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        self._adapter = PostgresAdapter.connect(self._conninfo, autocommit=True)
        self._peers: list[PostgresAdapter] = []

    @property
    def port(self) -> DbPort:
        """The concrete ``m-db-port`` over the container."""
        return self._adapter

    def peer(self, *, autocommit: bool = True) -> PostgresAdapter:
        """An independent second connection to the same container (provider `peer`).

        Concurrent-writer checks (the `m-db-error` deadlock / lock-wait proof) need
        a second connection that holds its own transaction, so `peer` returns the
        **concrete** :class:`~parallax.postgres.PostgresAdapter` (not just the
        abstract port) — a non-autocommit peer keeps a transaction open across
        statements. Tracked for teardown; also usable as a manual
        ``execRolledBack`` connection.
        """
        from parallax.postgres import PostgresAdapter

        peer = PostgresAdapter.connect(self._conninfo, autocommit=autocommit)
        self._peers.append(peer)
        return peer

    def reset(self, meta: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the schema, apply the descriptor DDL, and load the fixtures.

        Fixture binds carry the neutral :class:`JsonDocument` carrier for value
        objects; the adapter recognizes it at its boundary and binds the driver's
        native structured-document type, so no psycopg bind mechanics leak here.
        """
        for statement in reset_statements():
            self._adapter.execute_write(statement, [])
        for statement in schema_statements(meta):
            self._adapter.execute_write(statement, [])
        for sql, binds in fixture_statements(meta, fixtures):
            self._adapter.execute_write(POSTGRES.to_driver_sql(sql), binds)

    def close(self) -> None:
        for peer in self._peers:
            with suppress(Exception):
                peer.close()
        self._adapter.close()
        self._container.stop()
