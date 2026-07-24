"""Self-managed provisioning (spec §6, m-conformance-adapter ``self-managed``).

The simple reset path — the only path in v1: one session-scoped
Testcontainers Postgres pinned to :data:`~parallax.conformance.constants.POSTGRES_IMAGE`,
and per case ``DROP SCHEMA … CASCADE`` → ``CREATE SCHEMA`` → model-derived
DDL (``applyDdl``) → fixture rows in canonical column order (``loadFixtures``).

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

from parallax.conformance import case_format, models
from parallax.core import inheritance
from parallax.core.base import STRING
from parallax.core.db_port import DbPort, JsonDocument
from parallax.core.descriptor import Metamodel as DescriptorMetamodel
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet, column_order
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
)

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


def _position(facet: InheritanceFacet, entity: EntityMetadata) -> InheritanceEntityView:
    """``entity``'s family-effective view; the facet covers every accepted Entity."""
    view = facet.entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    return view


def _tables(model: Metamodel, facet: InheritanceFacet) -> list[tuple[EntityMetadata, str]]:
    """Every row-owning Entity paired with the physical table it targets.

    The container is the position's own row storage, which is the root-owned
    shared table for a table-per-hierarchy participant and absent for a
    tableless abstract position.
    """
    tables: list[tuple[EntityMetadata, str]] = []
    for entity in model.entities:
        container = _position(facet, entity).container
        if container is not None:
            tables.append((entity, container.name))
    return tables


def schema_statements(model: Metamodel, dialect: Dialect = POSTGRES) -> list[str]:
    """Model-derived ``create table`` DDL for every row-owning table.

    A table is created once even when several entities map to it. For a
    non-inheritance entity that is the plain per-entity column set. For an
    inheritance participant (m-inheritance) it is derived from the family: a
    table-per-hierarchy table merges the WHOLE family sharing it — every
    concrete's own columns (nullable — a card row leaves the cash-only column
    null and vice versa), the inherited (root + abstract-subtype) columns, and
    the framework-owned tag column, physically nullable-free since every row
    carries one — created exactly once, from the first entity ``_tables``
    encounters mapped to that table; a table-per-concrete-subtype table is one
    concrete's own ancestry-derived full column chain (root → … → that
    concrete), no tag. DDL is not asserted byte-exact anywhere in the corpus
    (`m-case-format`), so column order and the tag column's own type are this
    provisioning path's own choice, not a golden.

    A **temporal** Entity's physical primary key is its declared primary key plus
    the physical column of each As-Of Axis's start Attribute: many milestone
    rows share one domain identity, so the declared key alone would reject a
    second milestone. Start-Attribute columns are appended in declared axis
    order (Valid-Time before Transaction-Time), matching each model's declared
    composite unique index.
    """
    facet = inheritance.view(model)
    statements: list[str] = []
    seen_tables: set[str] = set()
    for entity, table in _tables(model, facet):
        if table in seen_tables:
            continue
        seen_tables.add(table)
        statements.append(_table_ddl(model, facet, entity, table, dialect))
    return statements


def _column_ddl(attribute: AttributeMetadata, dialect: Dialect) -> str:
    column_type = dialect.column_type(attribute.type, attribute.max_length)
    return f"{dialect.quote(attribute.storage.name)} {column_type}"


# A framework-owned tag column is not a declared attribute (m-inheritance), so
# provisioning fixes its own physical type — wide enough for any authored
# tagValue and never asserted byte-exact (no DDL golden, `m-case-format`).
_TAG_COLUMN_TYPE = STRING
_TAG_COLUMN_MAX_LENGTH = 32


def _table_ddl(
    model: Metamodel,
    facet: InheritanceFacet,
    entity: EntityMetadata,
    table: str,
    dialect: Dialect,
) -> str:
    """One table's ``create table``.

    A table-per-hierarchy family's ONE shared table merges every member sharing
    it — root, every intermediate abstract subtype, and every concrete — because
    value objects and unique secondary indices may be declared on ANY member
    (m-inheritance "Inherited members"). Every other table stores one position's
    own ancestry chain: a table-per-concrete-subtype concrete's root → … →
    concrete, and a standalone Entity's own single-member chain. As-of axes are
    DIFFERENT again: temporality is family-wide and root-declared, so the
    milestone-interval primary-key suffix is read off the root alone.
    """
    view = _position(facet, entity)
    root = _root(model, facet, entity)
    if view.tag_column is not None:
        members = _family_members(model, facet, root.identity)
        projection = facet.position([root.identity])
        assert projection is not None  # a root always denotes its own family position
        attributes: Sequence[AttributeMetadata] = projection.superset_attributes
        value_objects = projection.superset_value_objects
    else:
        members = tuple(
            member
            for member in (model.entity(identity) for identity in view.ancestry)
            if member is not None
        )
        attributes = view.applicable_attributes
        value_objects = view.applicable_value_objects

    # Canonical physical column order (`m-inheritance` canonical column order,
    # the rule `inheritance.column_order` states): the primary key, then the
    # framework-owned tag immediately after it, then the remaining scalars in
    # family-effective declaration order, and finally each value object's single
    # document column.
    key_columns: list[str] = []
    rest_columns: list[str] = []
    pk_columns: list[str] = []
    for attribute in attributes:
        if isinstance(attribute.primary_key, PrimaryKey):
            key_columns.append(_column_ddl(attribute, dialect))
            pk_columns.append(dialect.quote(attribute.storage.name))
        else:
            rest_columns.append(_column_ddl(attribute, dialect))
    tag_columns = (
        [
            f"{dialect.quote(view.tag_column)} "
            f"{dialect.column_type(_TAG_COLUMN_TYPE, _TAG_COLUMN_MAX_LENGTH)}"
        ]
        if view.tag_column is not None
        else []
    )
    documents = [f"{dialect.quote(member.storage.name)} jsonb" for member in value_objects]
    columns: list[str] = [*key_columns, *tag_columns, *rest_columns, *documents]
    pk_columns.extend(
        dialect.quote(_attribute_column(root, axis.start_attribute.name))
        for axis in root.declared_as_of_axes
    )
    if pk_columns:
        columns.append(f"primary key ({', '.join(pk_columns)})")
    columns.extend(_unique_constraints(members, pk_columns, dialect))
    return f"create table {dialect.quote(table)} ({', '.join(columns)})"


def _root(model: Metamodel, facet: InheritanceFacet, entity: EntityMetadata) -> EntityMetadata:
    root = model.entity(_position(facet, entity).root)
    if root is None:  # pragma: no cover - a family root is always an accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no family root")
    return root


def _family_members(
    model: Metamodel, facet: InheritanceFacet, root: EntityIdentity
) -> tuple[EntityMetadata, ...]:
    """Every accepted Entity whose family root is ``root``, in canonical order."""
    return tuple(
        member
        for member in model.entities
        if (position := facet.entity(member.identity)) is not None and position.root == root
    )


def _unique_constraints(
    chain: Sequence[EntityMetadata], pk_columns: list[str], dialect: Dialect
) -> list[str]:
    """``unique (…)`` constraints for the declared unique secondary indices of
    every entity in ``chain`` (a plain entity's own single-element chain, a
    table-per-concrete-subtype concrete's full ancestry, or a table-per-hierarchy
    table's whole member set — an ancestor's own index, e.g. its temporal
    composite, is otherwise invisible from a concrete declaration alone).

    An index's Attribute Identities resolve to physical columns through the
    WHOLE chain's scalar attributes. The composite milestone indices name the
    start Attribute (for example, ``tx_start`` maps to ``in_z``), so an index
    declared on one chain member may reference an attribute inherited from
    another. The index matching the physical primary key is skipped —
    ``primary key (…)`` already enforces it — what remains are the true
    secondaries (a unique business column, a one-to-one FK column), which must
    be enforced for the `m-db-error` uniqueViolation-via-secondary-index
    triggers to raise. A duplicate constraint (the same resolved column set
    declared more than once in the chain) is emitted once. An unresolvable
    attribute name fails loudly rather than silently dropping a declared
    constraint.
    """
    resolve: dict[str, str] = {}
    for member in chain:
        resolve.update(
            {
                attribute.identity.name: attribute.storage.name
                for attribute in member.declared_attributes
            }
        )
    constraints: list[str] = []
    seen: set[frozenset[str]] = set()
    for member in chain:
        for index in member.indices:
            if not index.unique:
                continue
            unresolved = [
                attribute.name for attribute in index.attributes if attribute.name not in resolve
            ]
            if unresolved:
                raise ValueError(
                    f"{member.identity.name}: unique index {index.identity.name!r} names "
                    f"attributes with no physical column: {unresolved}"
                )
            quoted = [dialect.quote(resolve[attribute.name]) for attribute in index.attributes]
            if set(quoted) == set(pk_columns):
                continue
            key = frozenset(quoted)
            if key in seen:
                continue
            seen.add(key)
            constraints.append(f"unique ({', '.join(quoted)})")
    return constraints


def _attribute_column(entity: EntityMetadata, name: str) -> str:
    attribute = entity.attribute(name)
    if attribute is None:  # pragma: no cover - an accepted axis names a declared Attribute
        raise ValueError(f"{entity.identity.name}: no attribute {name!r}")
    return attribute.storage.name


def _fixture_columns(
    facet: InheritanceFacet, entity: EntityMetadata
) -> tuple[Sequence[str], dict[str, tuple[str, bool]], tuple[str, object] | None]:
    """The column order, member resolution map, and an optional (framework-owned)
    tag assignment for one fixture-bearing entity.

    An inheritance participant's fixture rows carry every ancestry-inherited
    member BY NAME (`m-case-format`: a Dog fixture row authors ``name`` /
    ``ownerId`` — Animal's own — alongside its own ``barkVolume``), and the
    canonical column order is family-effective for exactly that reason, so one
    derivation serves a participant and a standalone Entity alike. A
    table-per-hierarchy concrete additionally always binds its tag column from
    its own declared ``tagValue`` — never authored in the fixture row
    (m-inheritance: "framework-owned metadata, never authored").
    """
    view = _position(facet, entity)
    member_by_column: dict[str, tuple[str, bool]] = {
        attribute.storage.name: (attribute.identity.name, False)
        for attribute in view.applicable_attributes
    }
    member_by_column.update(
        (member.storage.name, (member.identity.path[-1], True))
        for member in view.applicable_value_objects
    )
    tag_assignment: tuple[str, object] | None = None
    if view.tag_column is not None and view.tag_value is not None:
        tag_assignment = (view.tag_column, view.tag_value)
    return column_order(entity, facet), member_by_column, tag_assignment


def fixture_statements(
    model: Metamodel, fixtures: Mapping[str, object], dialect: Dialect = POSTGRES
) -> list[tuple[str, list[object]]]:
    """``insert`` statements for the model's fixtures, in canonical column order.

    Columns and binds follow the canonical physical column order (the same one
    DDL and row-write lowering use) rather than the fixture mapping's key order,
    so re-spelling a fixture row with permuted keys emits byte-identical SQL
    (python.md §6 ``loadFixtures``). A physical column with no member in the row
    (an omitted nullable) is skipped, so only authored members bind; a
    table-per-hierarchy concrete's tag column is always bound first, derived
    from its own ``tagValue`` (never a fixture member).
    """
    facet = inheritance.view(model)
    statements: list[tuple[str, list[object]]] = []
    for entity, table in _tables(model, facet):
        rows = fixtures.get(entity.identity.name)
        if not isinstance(rows, list):
            continue
        col_order, member_by_column, tag_assignment = _fixture_columns(facet, entity)
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
                if member is None:
                    continue  # the framework-owned tag column binds above, never here
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
    loaded = case_format.safe_load_yaml(fixture_path.read_text(encoding="utf-8"))
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
        # `prepare_threshold=None`: this ONE connection lives for the whole
        # session across hundreds of per-case `DROP SCHEMA CASCADE` resets, so
        # the SAME query text (e.g. two DIFFERENT corpus models both naming a
        # `person` table) can legitimately see a changed result shape between
        # two executions — server-side auto-preparation would otherwise raise
        # Postgres's own "cached plan must not change result type" (a driver
        # cache-invalidation quirk, not a Parallax-level concern; an ordinary
        # long-lived application connection against one stable schema keeps
        # the default).
        self._adapter = PostgresAdapter.connect(
            self._conninfo, autocommit=True, prepare_threshold=None
        )
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

    def reset(self, meta: DescriptorMetamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the schema, apply the model-derived DDL, and load the fixtures.

        Takes the descriptor record graph the harness already holds and forms it
        into the accepted model the pure statement generators consume, so a
        caller hands the same view it names a case's model with. Fixture binds
        carry the neutral :class:`JsonDocument` carrier for value objects; the
        adapter recognizes it at its boundary and binds the driver's native
        structured-document type, so no psycopg bind mechanics leak here.
        """
        model = models.accepted_model(meta)
        for statement in reset_statements():
            self._adapter.execute_write(statement, [])
        for statement in schema_statements(model):
            self._adapter.execute_write(statement, [])
        for sql, binds in fixture_statements(model, fixtures):
            self._adapter.execute_write(POSTGRES.to_driver_sql(sql), binds)

    def close(self) -> None:
        for peer in self._peers:
            with suppress(Exception):
                peer.close()
        self._adapter.close()
        self._container.stop()
