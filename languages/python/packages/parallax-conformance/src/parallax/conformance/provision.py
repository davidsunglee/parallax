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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from parallax.conformance import case_format
from parallax.core.descriptor import Entity, Metamodel
from parallax.core.dialect import POSTGRES, Dialect

__all__ = [
    "JsonDocument",
    "Provisioner",
    "fixture_statements",
    "load_fixtures",
    "reset_statements",
    "schema_statements",
]


@dataclass(frozen=True, slots=True)
class JsonDocument:
    """A value-object document bind, wrapped so the adapter binds it as ``jsonb``."""

    value: object


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
    """``insert`` statements for the model's fixtures, in descriptor column order."""
    statements: list[tuple[str, list[object]]] = []
    for entity, table in _tables(meta):
        rows = fixtures.get(entity.name)
        if not isinstance(rows, list):
            continue
        attr_columns = {attr.name: attr.column for attr in entity.attributes}
        vo_columns = {vo.name: vo.column for vo in entity.value_objects}
        for row in cast("list[object]", rows):
            if not isinstance(row, Mapping):
                continue
            columns: list[str] = []
            binds: list[object] = []
            for key, value in cast("Mapping[str, object]", row).items():
                if key in attr_columns:
                    columns.append(dialect.quote(attr_columns[key]))
                    binds.append(value)
                elif key in vo_columns:
                    columns.append(dialect.quote(vo_columns[key]))
                    binds.append(JsonDocument(value))
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
        conninfo = self._container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        self._adapter = PostgresAdapter.connect(conninfo, autocommit=True)

    @property
    def port(self) -> Any:
        """The concrete ``m-db-port`` over the container."""
        return self._adapter

    def reset(self, meta: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the schema, apply the descriptor DDL, and load the fixtures."""
        for statement in reset_statements():
            self._adapter.execute_write(statement, [])
        for statement in schema_statements(meta):
            self._adapter.execute_write(statement, [])
        for sql, binds in fixture_statements(meta, fixtures):
            self._adapter.execute_write(POSTGRES.to_driver_sql(sql), _driver_binds(binds))

    def close(self) -> None:
        self._adapter.close()
        self._container.stop()


def _driver_binds(binds: Sequence[object]) -> list[object]:  # pragma: no cover - Docker lane
    from parallax.postgres import Jsonb

    return [Jsonb(bind.value) if isinstance(bind, JsonDocument) else bind for bind in binds]
