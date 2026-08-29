"""Self-managed provisioning (spec §6, m-conformance-adapter ``self-managed``).

The simple reset path — the only path in v1: one session-scoped
Testcontainers Postgres pinned to :data:`~parallax.conformance.constants.POSTGRES_IMAGE`,
and per case ``DROP SCHEMA … CASCADE`` → ``CREATE SCHEMA`` → DDL derived from
the accepted model's compiled Table Layouts (``applyDdl``) → fixture rows in
Entity Layout order (``loadFixtures``).

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

from parallax.conformance import case_format
from parallax.core import inheritance, storage_layout
from parallax.core.base import JSON, STRING, decode_neutral_literal
from parallax.core.db_port import DbPort, JsonDocument
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.document_codec import (
    NULL,
    DocumentShape,
    Leaf,
    Presence,
    Present,
    encode_document,
    entity_shape,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    Column,
    EntityIdentity,
    IndexIdentity,
    IndexMetadata,
    Metamodel,
    ValueObjectIdentity,
    ValueObjectMetadata,
    derive_primary_key_index,
)
from parallax.core.storage_layout import (
    ColumnSlot,
    DocumentPath,
    EntityLayoutView,
    InheritanceDiscriminator,
    RelationalDocument,
    TableLayout,
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


def schema_statements(model: Metamodel, dialect: Dialect = POSTGRES) -> list[str]:
    """``create table`` DDL for every compiled Table Layout, once per table.

    `m-storage-layout` already composed each physical table: the layout's
    ``columns`` are the sole physical order, ``effective_nullable`` is the sole
    nullability answer, and ``physical_primary_key`` is the sole key. This path
    therefore only renders those selected values through the dialect. DDL is not
    asserted byte-exact anywhere in the corpus (`m-case-format`), so the
    framework-owned discriminator's physical type is this path's own choice
    rather than a golden.
    """
    facet = storage_layout.view(model)
    return [_table_ddl(model, layout, dialect) for layout in facet.tables]


# A framework-owned discriminator is not a declared Attribute (m-inheritance),
# so provisioning fixes its own physical type — wide enough for any authored
# tagValue and never asserted byte-exact (no DDL golden, `m-case-format`).
_TAG_COLUMN_TYPE = STRING
_TAG_COLUMN_MAX_LENGTH = 32


def _slot_type(model: Metamodel, slot: ColumnSlot, dialect: Dialect) -> str:
    """The physical column type of one slot's contributor.

    A top-level Value Object occupies one structured-document column
    (m-value-object); nested occurrences and inner fields live inside it. A
    Relational Document Layout's shared Structured Column is the same neutral
    `json` type and carries the document-resident members of every governed row,
    so both reach the dialect's own mapping rather than a spelling stated here.
    Its `not null` comes from the slot's effective nullability, not from this.
    """
    contributor = slot.contributor
    if isinstance(contributor, InheritanceDiscriminator):
        return dialect.column_type(_TAG_COLUMN_TYPE, _TAG_COLUMN_MAX_LENGTH)
    if isinstance(contributor, (ValueObjectIdentity, RelationalDocument)):
        return dialect.column_type(JSON, None)
    attribute = _declared_attribute(model, contributor)
    return dialect.column_type(attribute.type, attribute.max_length)


def _declared_attribute(model: Metamodel, contributor: AttributeIdentity) -> AttributeMetadata:
    entity = model.entity(contributor.entity)
    attribute = None if entity is None else entity.attribute(contributor.name)
    if attribute is None:  # pragma: no cover - a slot names an accepted declaration
        raise ValueError(f"{contributor.entity.canonical}: no attribute {contributor.name!r}")
    return attribute


def _column_ddl(model: Metamodel, slot: ColumnSlot, dialect: Dialect) -> str:
    nullability = "" if slot.effective_nullable else " not null"
    return f"{dialect.quote(slot.column.name)} {_slot_type(model, slot, dialect)}{nullability}"


def _table_ddl(model: Metamodel, layout: TableLayout, dialect: Dialect) -> str:
    """One layout's ``create table``, in complete canonical slot order.

    Every constraint comes from an Index: the derived primary-key Index becomes
    ``primary key (…)`` and each authored unique Index becomes ``unique (…)``.
    The two sets are disjoint, so no constraint is redundant with another.
    """
    columns = [_column_ddl(model, slot, dialect) for slot in layout.columns]
    key_columns = [dialect.quote(slot.column.name) for slot in layout.physical_primary_key]
    if key_columns:
        columns.append(f"primary key ({', '.join(key_columns)})")
    columns.extend(_unique_constraints(model, layout, dialect))
    return f"create table {dialect.quote(layout.table.name)} ({', '.join(columns)})"


def _primary_key_indices(model: Metamodel) -> frozenset[IndexIdentity]:
    """The Identity of every Entity's derived primary-key Index.

    ``primary key (…)`` already emits it, so it is the one unique Index a table
    constraint list leaves out.
    """
    derived = (
        derive_primary_key_index(
            entity=entity.identity,
            container=entity.declared_container,
            attributes=entity.declared_attributes,
            as_of_axes=entity.declared_as_of_axes,
        )
        for entity in model.entities
    )
    return frozenset(index.identity for index in derived if index is not None)


def _index_columns(layout: TableLayout, index: IndexMetadata) -> list[Column] | None:
    """One Index's physical columns, or absent when it names another table.

    Index Metadata stays an ordered declaration of local Attribute Identities
    (`m-storage-layout`), so each component resolves through the layout's
    contributor lookup. An Entity's whole local Attribute set reaches the same
    tables, so a partially resolvable Index is a defect rather than a shape.
    """
    slots = [layout.contribution(attribute) for attribute in index.attributes]
    if all(slot is None for slot in slots):
        return None
    if any(slot is None for slot in slots):  # pragma: no cover - defensive
        raise ValueError(
            f"index {index.identity.name!r} spans Table {layout.table.name!r} only partially"
        )
    return [cast("ColumnSlot", slot).column for slot in slots]


def _unique_constraints(model: Metamodel, layout: TableLayout, dialect: Dialect) -> list[str]:
    """``unique (…)`` constraints for every authored unique Index this table holds.

    A unique Index may be declared on any Entity whose members reach the table —
    a standalone Entity, an ancestor of a table-per-concrete-subtype concrete, or
    any table-per-hierarchy family participant — so the layout's contributor
    lookup, not an ancestry walk, decides membership. The derived primary-key
    Index is left out because ``primary key (…)`` already emits it; what remains
    are the true secondaries (a unique business column, a one-to-one FK column)
    the `m-db-error` uniqueViolation triggers need. Each of those emits its own
    constraint: no Index is suppressed for spanning the Columns another already
    spans.
    """
    derived = _primary_key_indices(model)
    constraints: list[str] = []
    for entity in model.entities:
        for index in entity.indices:
            if not index.unique or index.identity in derived:
                continue
            resolved = _index_columns(layout, index)
            if resolved is None:
                continue
            quoted = [dialect.quote(column.name) for column in resolved]
            constraints.append(f"unique ({', '.join(quoted)})")
    return constraints


def _fixture_member(slot: ColumnSlot) -> tuple[str, bool] | None:
    """One slot's authorable fixture member name and whether it is a document.

    A framework-owned discriminator has no fixture member: its value is derived
    from the concrete's own ``tagValue`` (m-inheritance).
    """
    contributor = slot.contributor
    if isinstance(contributor, AttributeIdentity):
        return contributor.name, False
    if isinstance(contributor, ValueObjectIdentity):
        return contributor.path[-1], True
    return None


def _document_members(
    model: Metamodel, layout: TableLayout, entity: EntityIdentity
) -> tuple[tuple[AttributeMetadata, ...], tuple[ValueObjectMetadata, ...]]:
    """``entity``'s applicable members that live inside the shared Structured Column.

    Member Placement decides residency (`m-storage-layout`), and the applicable
    member sequences come from the Inheritance view rather than from the Entity's
    own declarations, so an inheritance participant's inherited members reach the
    document exactly as they reach a Column.
    """
    view = inheritance.view(model).entity(entity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return (), ()
    return (
        tuple(
            attribute
            for attribute in view.applicable_attributes
            if isinstance(layout.placement(attribute.identity), DocumentPath)
        ),
        tuple(
            value_object
            for value_object in view.applicable_value_objects
            if isinstance(layout.placement(value_object.identity), DocumentPath)
        ),
    )


def _fixture_document(shape: DocumentShape, row: Mapping[str, object]) -> object:
    """One fixture row's Structured Column, composed through the codec.

    Each document-resident member is authored in the row under its own member
    name, in the very spelling it would take if the layout had given it a Column
    of its own — a leaf as the neutral wire value, an occurrence as that
    occurrence's own document — so one fixture file describes one logical row
    under either layout. The codec then spells every leaf and fixes presence: an
    omitted key stays absent, an authored null becomes JSON null, and a `many`
    occurrence always contributes its array.
    """
    values: dict[str, Presence] = {}
    for member in shape.members:
        if member.name not in row:
            continue
        raw = row[member.name]
        if raw is None:
            values[member.name] = NULL
            continue
        values[member.name] = Present(
            decode_neutral_literal(raw, member.type) if isinstance(member, Leaf) else raw
        )
    return encode_document(shape, values)


def _fixture_insert(
    view: EntityLayoutView, shape: DocumentShape, row: Mapping[str, object], dialect: Dialect
) -> tuple[str, list[object]]:
    """One fixture row's ``insert``, following the Entity Layout slot order.

    The shared Structured Column always binds, even for a row authoring no
    document-resident member: it is `NOT NULL` and every governed row carries a
    document, the empty object included (`m-storage-layout`).
    """
    columns: list[str] = []
    binds: list[object] = []
    for slot in view.columns:
        if isinstance(slot.contributor, RelationalDocument):
            columns.append(dialect.quote(slot.column.name))
            binds.append(JsonDocument(_fixture_document(shape, row)))
            continue
        member = _fixture_member(slot)
        if member is None:
            assert view.discriminator is not None  # only a shared table has a discriminator slot
            columns.append(dialect.quote(slot.column.name))
            binds.append(view.discriminator.value)
            continue
        name, is_document = member
        if name not in row:
            continue  # the fixture omits this cell
        columns.append(dialect.quote(slot.column.name))
        value = row[name]
        binds.append(JsonDocument(value) if is_document else value)
    placeholders = ", ".join("?" for _ in columns)
    sql = (
        f"insert into {dialect.quote(view.layout.table.name)} "
        f"({', '.join(columns)}) values ({placeholders})"
    )
    return sql, binds


def fixture_statements(
    model: Metamodel, fixtures: Mapping[str, object], dialect: Dialect = POSTGRES
) -> list[tuple[str, list[object]]]:
    """``insert`` statements for the model's fixtures, in Entity Layout order.

    An Entity Layout view already selects the slots applicable to one row-owning
    Entity, in complete table order, so an inheritance participant's fixture row
    resolves every ancestry-inherited member by name exactly as a standalone
    Entity's does. Columns and binds follow that order rather than the fixture
    mapping's key order, so re-spelling a row with permuted keys emits
    byte-identical SQL (python.md §6 ``loadFixtures``). A physical column with no
    member in the row is skipped, so only authored members bind; a
    table-per-hierarchy concrete's discriminator always binds its own derived
    ``tagValue``.
    """
    facet = storage_layout.view(model)
    statements: list[tuple[str, list[object]]] = []
    for entity in model.entities:
        view = facet.entity(entity.identity)
        if view is None:
            continue  # a rowless abstract position owns no fixture rows
        rows = fixtures.get(entity.identity.canonical, fixtures.get(entity.identity.name))
        if not isinstance(rows, list):
            continue
        shape = entity_shape(*_document_members(model, view.layout, entity.identity))
        statements.extend(
            _fixture_insert(view, shape, cast("Mapping[str, object]", row), dialect)
            for row in cast("list[object]", rows)
            if isinstance(row, Mapping)
        )
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

    @classmethod
    def adapter(cls) -> type[PostgresAdapter]:
        """The database adapter class this provisioner opens.

        Declared here, beside the container image and the driver options the
        connection is opened with, so nothing else restates which adapter runs:
        a profile reads its dialect back off this class without constructing a
        provisioner, a container, or a connection. The import is deferred like
        this module's other reaches into the driver, so naming the adapter costs
        no psycopg import until something asks for it.
        """
        from parallax.postgres import PostgresAdapter

        return PostgresAdapter

    def __init__(self) -> None:
        from testcontainers.community.postgres import PostgresContainer

        from parallax.conformance import constants

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
        self._adapter = self.adapter().connect(
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
        peer = self.adapter().connect(self._conninfo, autocommit=autocommit)
        self._peers.append(peer)
        return peer

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the schema, apply the model-derived DDL, and load the fixtures.

        Fixture binds carry the neutral :class:`JsonDocument` carrier for value
        objects; the adapter recognizes it at its boundary and binds the driver's
        native structured-document type, so no psycopg bind mechanics leak here.
        """
        dialect = self._adapter.dialect
        for statement in reset_statements():
            self._adapter.execute_write(statement, [])
        for statement in schema_statements(model, dialect):
            self._adapter.execute_write(statement, [])
        for sql, binds in fixture_statements(model, fixtures, dialect):
            self._adapter.execute_write(dialect.to_driver_sql(sql), binds)

    def close(self) -> None:
        for peer in self._peers:
            with suppress(Exception):
                peer.close()
        self._adapter.close()
        self._container.stop()
