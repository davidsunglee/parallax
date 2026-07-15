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
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml

from parallax.conformance import case_format
from parallax.core import inheritance
from parallax.core.db_port import DbPort, JsonDocument
from parallax.core.descriptor import Attribute, Entity, Metamodel, column_order
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

    A table is created once even when several entities map to it. For a
    non-inheritance entity that is the plain per-entity column set. For an
    inheritance participant (m-inheritance) it is derived from the family: a
    table-per-hierarchy table merges the WHOLE family sharing it — every
    concrete's own columns (nullable — a card row leaves the cash-only column
    null and vice versa), the inherited (root + abstract-subtype) columns, and
    the framework-owned tag column, physically nullable-free since every row
    carries one — created exactly once, from the first entity `_tables`
    encounters mapped to that table (its declaration-order position in the
    model file); a table-per-concrete-subtype table is one concrete's own
    ancestry-derived full column chain (root → … → that concrete), no tag.
    DDL is not asserted byte-exact anywhere in the corpus (`m-case-format`), so
    column order and the tag column's own type are this provisioning path's own
    choice, not a golden.

    A **temporal** entity's physical primary key is its business key **plus each
    as-of axis's ``fromColumn``** (``m-descriptor``): many milestone rows share one
    business key, so a single-column PK would reject a second milestone. The
    from-columns are appended in declared axis order (business before processing),
    matching each model's declared composite unique index.
    """
    statements: list[str] = []
    seen_tables: set[str] = set()
    for entity, table in _tables(meta):
        if table in seen_tables:
            continue
        seen_tables.add(table)
        if entity.inheritance is None:
            statements.append(_plain_table_ddl(entity, table, dialect))
        else:
            statements.append(_inheritance_table_ddl(meta, entity, table, dialect))
    return statements


def _column_ddl(attribute: Attribute, dialect: Dialect) -> str:
    column_type = dialect.column_type(attribute.type, attribute.max_length)
    return f"{dialect.quote(attribute.column)} {column_type}"


def _plain_table_ddl(entity: Entity, table: str, dialect: Dialect) -> str:
    columns: list[str] = []
    pk_columns: list[str] = []
    for attribute in entity.attributes:
        columns.append(_column_ddl(attribute, dialect))
        if attribute.primary_key:
            pk_columns.append(dialect.quote(attribute.column))
    for value_object in entity.value_objects:
        columns.append(f"{dialect.quote(value_object.column)} jsonb")
    pk_columns.extend(dialect.quote(aoa.from_column) for aoa in entity.as_of_attributes)
    if pk_columns:
        columns.append(f"primary key ({', '.join(pk_columns)})")
    columns.extend(_unique_constraints((entity,), pk_columns, dialect))
    return f"create table {dialect.quote(table)} ({', '.join(columns)})"


# A framework-owned tag column is not a declared attribute (m-inheritance), so
# provisioning fixes its own physical type — wide enough for any authored
# tagValue and never asserted byte-exact (no DDL golden, `m-case-format`).
_TAG_COLUMN_TYPE = "string"
_TAG_COLUMN_MAX_LENGTH = 32


def _inheritance_table_ddl(meta: Metamodel, entity: Entity, table: str, dialect: Dialect) -> str:
    root = inheritance.family_root(meta, entity)
    assert root.inheritance is not None
    if root.inheritance.strategy == "table-per-hierarchy":
        return _tph_table_ddl(meta, root, table, dialect)
    return _tpcs_table_ddl(meta, entity, dialect)


def _tph_table_ddl(meta: Metamodel, root: Entity, table: str, dialect: Dialect) -> str:
    """A table-per-hierarchy family's ONE shared table, merging every member
    sharing it — root, every intermediate abstract-subtype, and every
    concrete subtype.

    Value objects and unique secondary indices may be declared on ANY member
    of the family (m-inheritance "Inherited members"), so both are derived
    from the WHOLE member set (``ancestors + concretes``) rather than read off
    ``root`` alone: reading them off the root only would silently drop an
    intermediate- or concrete-declared value object, or a secondary unique
    index declared anywhere but the root. As-of axes are DIFFERENT: temporality
    is a family-wide property the root ALONE declares (the
    `inheritance-temporal-axes-not-root-owned` invariant rejects any
    descendant that does), so the milestone-interval PK suffix is read off
    ``root`` directly — never unioned across the member set.
    """
    assert root.inheritance is not None
    concretes = sorted(
        (e for e in meta.entities if e.inheritance is not None and e.table == table),
        key=lambda e: e.name,
    )
    columns: list[str] = []
    pk_columns: list[str] = []
    for attribute in root.attributes:
        columns.append(_column_ddl(attribute, dialect))
        if attribute.primary_key:
            pk_columns.append(dialect.quote(attribute.column))
    tag_col = root.inheritance.tag_column
    if tag_col is not None:
        columns.append(
            f"{dialect.quote(tag_col)} "
            f"{dialect.column_type(_TAG_COLUMN_TYPE, _TAG_COLUMN_MAX_LENGTH)}"
        )
    ancestors = inheritance.ancestor_chain(meta, tuple(c.name for c in concretes))
    for ancestor in ancestors:
        if ancestor.name == root.name:
            continue  # root's own columns already emitted above, in their declared order
        for attribute in ancestor.attributes:
            columns.append(_column_ddl(attribute, dialect))
    for concrete in concretes:
        for attribute in concrete.attributes:
            columns.append(_column_ddl(attribute, dialect))

    # The whole family sharing this table: every ancestor (root first) plus
    # every concrete row-owner — the complete member set value objects and
    # unique indices may be declared across (never root-only).
    members = (*ancestors, *concretes)
    for member in members:
        for value_object in member.value_objects:
            columns.append(f"{dialect.quote(value_object.column)} jsonb")

    # The root's own as-of axes — the family's ONLY legal declaration site
    # (temporality is family-wide; `validate` rejects a descendant that
    # declares any) — appended as the table's milestone-interval PK suffix.
    pk_columns.extend(dialect.quote(aoa.from_column) for aoa in root.as_of_attributes)

    if pk_columns:
        columns.append(f"primary key ({', '.join(pk_columns)})")
    columns.extend(_unique_constraints(members, pk_columns, dialect))
    return f"create table {dialect.quote(table)} ({', '.join(columns)})"


def _tpcs_table_ddl(meta: Metamodel, concrete: Entity, dialect: Dialect) -> str:
    """A table-per-concrete-subtype concrete's own table, its full
    ancestry-derived column chain (root → … → concrete).

    A TPCS family's temporal as-of axes are declared on the abstract ROOT
    ALONE and inherited by every concrete subtype — never repeated or amended
    lower (`inheritance-temporal-axes-not-root-owned`) — so the axes are
    derived through `inheritance.declaring_entity` (which resolves to the
    root for any participant) rather than read off `concrete` directly:
    reading them off the concrete alone would silently omit the
    milestone-interval from-columns from the physical primary key, leaving no
    way to store a second milestone for the same business key (`m-descriptor`
    "a temporal entity's physical primary key is the business key plus each
    dimension's fromColumn"). Any unique secondary index, though, MAY be
    declared on any ancestor along ``concrete``'s own chain (m-inheritance
    "Inherited members" places no such restriction on non-temporal members),
    so value objects and unique indices are unioned across the whole chain
    (today's corpus declares value objects only on the concrete, but a root-
    or intermediate-declared one must not be dropped either).
    """
    assert concrete.table is not None
    chain = (*inheritance.ancestor_chain(meta, (concrete.name,)), concrete)
    columns: list[str] = []
    pk_columns: list[str] = []
    for member in chain:
        for attribute in member.attributes:
            columns.append(_column_ddl(attribute, dialect))
            if attribute.primary_key:
                pk_columns.append(dialect.quote(attribute.column))
    for member in chain:
        for value_object in member.value_objects:
            columns.append(f"{dialect.quote(value_object.column)} jsonb")
    declaring = inheritance.declaring_entity(meta, concrete)
    pk_columns.extend(dialect.quote(aoa.from_column) for aoa in declaring.as_of_attributes)
    if pk_columns:
        columns.append(f"primary key ({', '.join(pk_columns)})")
    columns.extend(_unique_constraints(chain, pk_columns, dialect))
    return f"create table {dialect.quote(concrete.table)} ({', '.join(columns)})"


def _unique_constraints(
    chain: Sequence[Entity], pk_columns: list[str], dialect: Dialect
) -> list[str]:
    """``unique (…)`` constraints for the declared unique secondary indices of
    every entity in ``chain`` (a plain entity's own single-element chain, a
    table-per-concrete-subtype concrete's full ancestry, or a table-per-hierarchy
    table's whole member set — an ancestor's own index, e.g. its temporal
    composite, is otherwise invisible from a concrete descriptor alone).

    An index's attribute names resolve to physical columns through the WHOLE
    chain's scalar attributes and each as-of axis's from-column (the corpus
    convention: the composite milestone indices name the as-of attribute, e.g.
    ``processingFrom`` → ``in_z``), so an index declared on one chain member
    may reference an attribute inherited from another. The index matching the
    physical primary key is skipped — ``primary key (…)`` already enforces it
    — what remains are the true secondaries (a unique business column, a
    one-to-one FK column), which must be enforced for the `m-db-error`
    uniqueViolation-via-secondary-index triggers to raise. A duplicate
    constraint (the same resolved column set declared more than once in the
    chain) is emitted once. An unresolvable attribute name fails loudly rather
    than silently dropping a declared constraint.
    """
    resolve: dict[str, str] = {}
    for member in chain:
        resolve.update({attribute.name: attribute.column for attribute in member.attributes})
        resolve.update({aoa.name: aoa.from_column for aoa in member.as_of_attributes})
    constraints: list[str] = []
    seen: set[frozenset[str]] = set()
    for member in chain:
        for index in member.indices:
            if not index.unique:
                continue
            unresolved = [name for name in index.attributes if name not in resolve]
            if unresolved:
                raise ValueError(
                    f"{member.name}: unique index {index.name!r} names attributes with no "
                    f"physical column: {unresolved}"
                )
            quoted = [dialect.quote(resolve[name]) for name in index.attributes]
            if set(quoted) == set(pk_columns):
                continue
            key = frozenset(quoted)
            if key in seen:
                continue
            seen.add(key)
            constraints.append(f"unique ({', '.join(quoted)})")
    return constraints


def _fixture_columns(
    meta: Metamodel, entity: Entity
) -> tuple[list[str], dict[str, tuple[str, bool]], tuple[str, object] | None]:
    """The column order, member resolution map, and an optional (framework-owned)
    tag assignment for one fixture-bearing entity.

    A plain (non-inheritance) entity is unchanged: ``column_order`` and its own
    attributes/value-objects. An inheritance participant's fixture rows carry
    every ancestry-inherited member BY NAME (`m-case-format`: a Dog fixture row
    authors ``name``/``ownerId`` — Animal's own — alongside its own
    ``barkVolume``), so the column order and resolution map are derived from the
    full ancestry chain (root → … → this concrete) instead of the entity's own
    ``column_order`` view. A table-per-hierarchy concrete additionally always
    binds its tag column from its own declared ``tagValue`` — never authored in
    the fixture row (m-inheritance: "framework-owned metadata, never authored").
    """
    if entity.inheritance is None:
        member_by_column: dict[str, tuple[str, bool]] = {
            attr.column: (attr.name, False) for attr in entity.attributes
        }
        member_by_column.update((vo.column, (vo.name, True)) for vo in entity.value_objects)
        return list(column_order(entity)), member_by_column, None

    chain = (*inheritance.ancestor_chain(meta, (entity.name,)), entity)
    col_order: list[str] = []
    member_by_column = {}
    for member in chain:
        for attribute in member.attributes:
            col_order.append(attribute.column)
            member_by_column[attribute.column] = (attribute.name, False)
        for vo in member.value_objects:
            col_order.append(vo.column)
            member_by_column[vo.column] = (vo.name, True)

    tag_assignment: tuple[str, object] | None = None
    root = inheritance.family_root(meta, entity)
    if root.inheritance is not None and root.inheritance.strategy == "table-per-hierarchy":
        tag_col = root.inheritance.tag_column
        tag_value = entity.inheritance.tag_value
        if tag_col is not None and tag_value is not None:
            tag_assignment = (tag_col, tag_value)
    return col_order, member_by_column, tag_assignment


def fixture_statements(
    meta: Metamodel, fixtures: Mapping[str, object], dialect: Dialect = POSTGRES
) -> list[tuple[str, list[object]]]:
    """``insert`` statements for the model's fixtures, in descriptor column order.

    Columns and binds follow the descriptor ``column_order`` derivation (the same
    canonical physical order DDL and row-write lowering use) for a plain entity —
    an inheritance participant's ancestry-derived order, `_fixture_columns` —
    never the fixture mapping's key order, so re-spelling a fixture row with
    permuted keys emits byte-identical SQL (python.md §6 ``loadFixtures``). A
    physical column with no member in the row (an omitted nullable) is skipped,
    so only authored members bind; a table-per-hierarchy concrete's tag column is
    always bound first, derived from its own ``tagValue`` (never a fixture member).
    """
    statements: list[tuple[str, list[object]]] = []
    for entity, table in _tables(meta):
        rows = fixtures.get(entity.name)
        if not isinstance(rows, list):
            continue
        col_order, member_by_column, tag_assignment = _fixture_columns(meta, entity)
        for row in cast("list[object]", rows):
            if not isinstance(row, Mapping):
                continue
            member_row = cast("Mapping[str, object]", row)
            columns: list[str] = []
            binds: list[object] = []
            if tag_assignment is not None:
                tag_col, tag_value = tag_assignment
                columns.append(dialect.quote(tag_col))
                binds.append(tag_value)
            for column in col_order:
                member = member_by_column.get(column)
                if member is None:  # pragma: no cover - defends a malformed column plan
                    continue
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
