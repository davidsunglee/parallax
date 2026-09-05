"""Self-managed provisioning (spec §6, m-conformance-adapter ``self-managed``).

The simple reset path — the only path in v1: one session-scoped
Testcontainers Postgres pinned to :data:`~parallax.conformance.constants.POSTGRES_IMAGE`,
and per case ``DROP SCHEMA … CASCADE`` → ``CREATE SCHEMA`` → the shipped
generator's Schema Delta for the evolution from ABSENT (``applyDdl``) → fixture
rows in Entity Layout order (``loadFixtures``).

Statement generation is pure and unit-tested without Docker — the DDL by
`m-schema-delta`'s own suite, the fixtures by ``fixture_statements``' — while the
container lifecycle and driver execution live behind :class:`Provisioner`, proven
by the Docker provider / conformance lanes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

from parallax.conformance import case_format
from parallax.conformance._case_literal import normalize_case_literal
from parallax.core import inheritance, storage_layout
from parallax.core.base import JSON, TIMESTAMP, NeutralType
from parallax.core.db_port import DbPort, JsonDocument
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.document_codec import (
    NULL,
    DocumentShape,
    Leaf,
    Occurrence,
    Presence,
    Present,
    encode_document,
    entity_shape,
    occurrence_shape,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    TemporalDimension,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.storage_layout import (
    ColumnSlot,
    DocumentPath,
    EntityLayoutView,
    RelationalDocument,
    TableLayout,
)
from parallax.core.wire import WireValue, decode_wire, encode_wire
from parallax.evolution.model_evolution import ABSENT, evolve
from parallax.evolution.schema_delta import schema_delta

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
    """The shipped generator's provisioning DDL for ``model``.

    Provisioning is the Unilateral Evolution from ``ABSENT``, so this path holds
    no DDL of its own: every physical fact, every statement, and every Physical
    Index Name is `m-schema-delta`'s, which is what makes the whole
    database-backed suite a proof of the generator rather than of a second
    composition that happens to agree with it.
    """
    return list(schema_delta(evolve(ABSENT, model), dialect).statements)


def _declared_attribute(model: Metamodel, contributor: AttributeIdentity) -> AttributeMetadata:
    entity = model.entity(contributor.entity)
    attribute = None if entity is None else entity.attribute(contributor.name)
    if attribute is None:  # pragma: no cover - a slot names an accepted declaration
        raise ValueError(f"{contributor.entity.canonical}: no attribute {contributor.name!r}")
    return attribute


def _fixture_member(
    model: Metamodel, slot: ColumnSlot
) -> tuple[str, AttributeMetadata | DocumentShape] | None:
    """One slot's authorable fixture member and its declared projection metadata.

    A framework-owned discriminator has no fixture member: its value is derived
    from the concrete's own ``tagValue`` (m-inheritance).
    """
    contributor = slot.contributor
    if isinstance(contributor, AttributeIdentity):
        return contributor.name, _declared_attribute(model, contributor)
    if isinstance(contributor, ValueObjectIdentity):
        entity = model.entity(contributor.entity)
        value_object = None if entity is None else entity.value_object(contributor.path[-1])
        if value_object is None:  # pragma: no cover - a slot names an accepted declaration
            raise ValueError(
                f"{contributor.entity.canonical}: no value object {contributor.path[-1]!r}"
            )
        return contributor.path[-1], occurrence_shape(value_object)
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


def _fixture_document(
    shape: DocumentShape, row: Mapping[str, object], *, preserve_unknown: bool = True
) -> object:
    """One fixture row's Structured Column, composed through the codec.

    Each document-resident member is authored in the row under its own member
    name, in the very spelling it would take if the layout had given it a Column
    of its own — a leaf as the neutral wire value, an occurrence as that
    occurrence's own document — so one fixture file describes one logical row
    under either layout. The codec then spells every leaf and fixes presence: an
    omitted key stays absent, an authored null becomes JSON null, and a `many`
    occurrence always contributes its array.
    """
    encoded = encode_document(shape, _fixture_values(shape, row))
    if not preserve_unknown:
        return encoded
    declared = {member.name for member in shape.members}
    unknown = {name: value for name, value in row.items() if name not in declared}
    if not unknown:
        return encoded
    canonical = encode_wire(JSON, decode_wire(JSON, cast("WireValue", unknown)))
    return {**encoded, **cast("Mapping[str, object]", canonical)}


def _fixture_values(shape: DocumentShape, row: Mapping[str, object]) -> dict[str, Presence]:
    values: dict[str, Presence] = {}
    for member in shape.members:
        if member.name not in row:
            continue
        raw = row[member.name]
        if raw is None:
            values[member.name] = NULL
            continue
        if isinstance(member, Leaf):
            value = _fixture_literal(member.type, raw)
        else:
            value = _fixture_occurrence(member, raw)
        values[member.name] = Present(value)
    return values


def _fixture_occurrence(member: Occurrence, raw: object) -> object:
    if member.multiplicity is Multiplicity.MANY:
        if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
            return raw
        source = cast("Sequence[object]", raw)
        if any(not isinstance(element, Mapping) for element in source):
            raise ValueError(f"{member.name}: every many occurrence element must be a mapping")
        return [
            _fixture_document(member.shape, cast("Mapping[str, object]", element))
            for element in source
        ]
    if not isinstance(raw, Mapping):
        return raw
    return _fixture_document(member.shape, cast("Mapping[str, object]", raw))


def _fixture_literal(
    neutral_type: NeutralType, value: object, *, temporal_end: bool = False
) -> object:
    if temporal_end and neutral_type == TIMESTAMP and value == "infinity":
        return value
    return decode_wire(
        neutral_type,
        cast("WireValue", normalize_case_literal(neutral_type, value)),
    )


def _is_temporal_end(model: Metamodel, member: AttributeMetadata) -> bool:
    entity = model.entity(member.identity.entity)
    if entity is None:  # pragma: no cover - accepted Metadata owns every member
        return False
    return any(
        (axis := entity.as_of_axis(dimension)) is not None and axis.end_attribute == member.identity
        for dimension in TemporalDimension
    )


def _fixture_insert(
    model: Metamodel,
    view: EntityLayoutView,
    shape: DocumentShape,
    row: Mapping[str, object],
    dialect: Dialect,
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
            binds.append(JsonDocument(_fixture_document(shape, row, preserve_unknown=False)))
            continue
        member = _fixture_member(model, slot)
        if member is None:
            assert view.discriminator is not None  # only a shared table has a discriminator slot
            columns.append(dialect.quote(slot.column.name))
            binds.append(view.discriminator.value)
            continue
        name, projection = member
        if name not in row:
            continue  # the fixture omits this cell
        columns.append(dialect.quote(slot.column.name))
        value = row[name]
        if value is None:
            binds.append(None)
        elif isinstance(projection, DocumentShape):
            binds.append(
                JsonDocument(
                    _fixture_document(projection, cast("Mapping[str, object]", value))
                    if isinstance(value, Mapping)
                    else value
                )
            )
        else:
            binds.append(
                _fixture_literal(
                    projection.type,
                    value,
                    temporal_end=_is_temporal_end(model, projection),
                )
            )
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
            _fixture_insert(model, view, shape, cast("Mapping[str, object]", row), dialect)
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


# The Postgres SQL establishing each session default this provisioner can hand
# an adapter, keyed by the Isolation Level name `given.sessionDefault` declares.
# It sets the CONNECTION's own default rather than one transaction's level,
# which is what an adapter inspects when it takes the connection. Postgres has
# no level below Read Committed and runs a Read Uncommitted transaction as Read
# Committed, so a connection this statement configures still meets the floor
# here.
_SESSION_DEFAULTS: Mapping[str, str] = {
    "read-uncommitted": (
        "set session characteristics as transaction isolation level read uncommitted"
    ),
}


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

    def taken_at_session_default(self, level: str) -> PostgresAdapter:
        """The adapter over a connection whose OWN default isolation is ``level``.

        ``m-db-port`` puts the default's check at INTAKE — an adapter inspects
        the connection it is handed once, when it takes it — so the default is
        established on the connection first and the adapter constructed over it
        second. Opening the connection through the adapter's own ``connect`` and
        then taking it again is what expresses that order: ``connect`` takes a
        connection it opened itself, which carries no default a case chose.

        Tracked for teardown through the adapter that is returned, since both
        adapters hold the one connection.
        """
        opened = self.adapter().connect(self._conninfo, autocommit=True)
        opened.execute_write(_SESSION_DEFAULTS[level], [])
        taken = self.adapter()(opened.connection)
        self._peers.append(taken)
        return taken

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
