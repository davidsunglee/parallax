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

from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

from parallax.conformance import case_format
from parallax.conformance._case_literal import normalize_case_literal
from parallax.core import inheritance, storage_layout
from parallax.core.base import JSON, TIMESTAMP, NeutralType
from parallax.core.db_port import DatabaseRuntime, JsonDocument
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
    from parallax.conformance._database_control import (
        CaseDatabase,
        DriverControl,
        InterleavedExecution,
    )
    from parallax.conformance._postgres_control import (
        PostgresControl,
        PostgresInterleavedExecution,
    )
    from parallax.core.db_port import (
        Bind,
        ConnectionContext,
        DatabaseAdapter,
        DatabaseConnection,
        DocumentReadOrdinals,
        IsolationLevel,
        PipelineStatement,
        PoolMetricsSource,
        Row,
        TransactionOutcome,
    )
    from parallax.core.entity import DomainModel
    from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
    from parallax.core.unit_work import Clock
    from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter
    from parallax.snapshot.handle import ServingModel

__all__ = [
    "ContainerDatabase",
    "Provisioner",
    "fixture_document",
    "fixture_literal",
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


def fixture_document(
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
            value = fixture_literal(member.type, raw)
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
            fixture_document(member.shape, cast("Mapping[str, object]", element))
            for element in source
        ]
    if not isinstance(raw, Mapping):
        return raw
    return fixture_document(member.shape, cast("Mapping[str, object]", raw))


def fixture_literal(
    neutral_type: NeutralType, value: object, *, temporal_end: bool = False
) -> object:
    """Decode one fixture literal, admitting infinity only for a temporal end."""
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
            binds.append(JsonDocument(fixture_document(shape, row, preserve_unknown=False)))
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
                    fixture_document(projection, cast("Mapping[str, object]", value))
                    if isinstance(value, Mapping)
                    else value
                )
            )
        else:
            binds.append(
                fixture_literal(
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


# The connection-establishment option carrying each session default this
# provisioner can hand an adapter, keyed by the Isolation Level name
# `given.sessionDefault` declares. It arrives with the connection rather than as
# a `SET` afterwards, which is what makes it the connection's OWN default when
# the adapter initializes it — nothing borrows a session and changes it. Postgres
# has no level below Read Committed and runs a Read Uncommitted transaction as
# Read Committed, so a connection established this way still meets the floor here.
_SESSION_DEFAULTS: Mapping[str, str] = {
    "read-uncommitted": "-c default_transaction_isolation=read\\ uncommitted",
}


class ContainerDatabase:  # pragma: no cover - exercised by the Docker-backed lanes
    """One provisioned database as the two halves a case needs of it.

    The ``DatabaseAdapter`` half is configuration for the shipped adapter, so a
    case's modeled work runs through the real pooled runtime it is meant to
    prove. The ``DatabaseConnection`` half forwards to the provisioner's own
    session, so the DDL, the fixtures, a verbatim ``given.apply`` and a golden
    read of stored state run outside anything under test.

    It also keeps the runtimes it handed out. A Database that is closed retires
    its own; what is tracked here is the backstop for a case that composed one
    and did not, because a session that accumulated a pool per case would run the
    server out of connections long before the corpus ran out of cases.
    """

    def __init__(self, adapter: PostgresAdapter, session: DriverControl) -> None:
        self._adapter = adapter
        self._session = session
        self._opened: list[DatabaseRuntime] = []

    @property
    def dialect(self) -> Dialect:
        return self._session.dialect

    def open(self) -> DatabaseRuntime:
        runtime = _TrackedRuntime(self._adapter.open(), self._opened.remove)
        self._opened.append(runtime)
        return runtime

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._session.execute(sql, binds, document_reads)

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return self._session.execute_pipeline(statements)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return self._session.execute_write(sql, binds)

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        return self._session.transaction(body, isolation=isolation)

    def release_runtimes(self) -> None:
        """Close every runtime a composed Database left open."""
        for runtime in tuple(self._opened):
            with suppress(Exception):
                runtime.close()
        self._opened.clear()


class _TrackedRuntime:  # pragma: no cover - exercised by the Docker-backed lanes
    """A runtime that tells its opener when its Database closes it.

    Closing is idempotent underneath, so the backstop may close one this already
    reported; what the report buys is that the backstop closes only what a case
    actually left behind.
    """

    def __init__(self, inner: DatabaseRuntime, on_close: Callable[[DatabaseRuntime], None]) -> None:
        self._inner = inner
        self._on_close: Callable[[DatabaseRuntime], None] | None = on_close

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return self._inner.pool_metrics

    def connection(self) -> ConnectionContext:
        return self._inner.connection()

    def close(self) -> None:
        self._inner.close()
        released, self._on_close = self._on_close, None
        if released is not None:
            released(self)


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

    @staticmethod
    def _control() -> type[PostgresControl]:
        """The control implementation this provisioner opens scoped sessions with.

        Reached through the same deferred import as the adapter itself: naming a
        control must cost no psycopg import until something opens one.
        """
        from parallax.conformance._postgres_control import PostgresControl

        return PostgresControl

    @staticmethod
    def _interleaved() -> type[PostgresInterleavedExecution]:
        """The dedicated-execution implementation, reached the same deferred way."""
        from parallax.conformance._postgres_control import PostgresInterleavedExecution

        return PostgresInterleavedExecution

    def __init__(self) -> None:
        from testcontainers.community.postgres import PostgresContainer

        from parallax.conformance import constants

        self._container = PostgresContainer(constants.POSTGRES_IMAGE)
        self._container.start()
        self._conninfo = self._container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        # `prepare_threshold=None` throughout: a connection here can outlive
        # hundreds of per-case `DROP SCHEMA CASCADE` resets, so the SAME query
        # text (two DIFFERENT corpus models both naming a `person` table) can
        # legitimately see a changed result shape between two executions —
        # server-side auto-preparation would otherwise raise Postgres's own
        # "cached plan must not change result type" (a driver cache-invalidation
        # quirk, not a Parallax-level concern; an ordinary long-lived application
        # connection against one stable schema keeps the default).
        self._session = self._control().open(
            self._conninfo, autocommit=True, prepare_threshold=None
        )
        self._database = ContainerDatabase(self._configuration(), self._session)
        # Every scoped session that may still be alive. One removes itself as
        # soon as its session is gone — which is its close, or, for a close that
        # waited on a borrower, the relinquishment that completed it. What
        # remains is what a caller never closed and what would not close, and
        # `close` below is the backstop that ends both.
        self._open: set[PostgresControl | PostgresInterleavedExecution] = set()

    def _configuration(self, **conninfo_options: str) -> PostgresAdapter:
        """The shipped adapter's configuration for this container.

        Retention is deliberately lean rather than default: a case composes its
        own Database and the corpus has hundreds of cases, so a zero minimum
        keeps a run from paying for capacity a case may never acquire, and one
        maintenance worker keeps the thread cost of that per-case runtime down.
        Neither changes any behavior a case grades — capacity still grows on
        demand up to the same ceiling.
        """
        from parallax.postgres import PoolOptions

        return self._built(
            pool=PoolOptions(min_size=0, num_workers=1),
            prepare_threshold=None,
            **conninfo_options,
        )

    def _built(
        self,
        *,
        pool: PoolOptions | OnDemandOptions,
        prepare_threshold: int | None,
        **conninfo_options: str,
    ) -> PostgresAdapter:
        """The shipped configuration for this container, under ``conninfo_options``."""
        from psycopg.conninfo import make_conninfo

        return self.adapter()(
            make_conninfo(self._conninfo, **conninfo_options),
            pool=pool,
            prepare_threshold=prepare_threshold,
        )

    @property
    def port(self) -> CaseDatabase:
        """This container as the two halves a case runs against."""
        return self._database

    def control(self, *, autocommit: bool = True) -> DriverControl:
        """A separately owned second session to the same container (provider `peer`).

        Concurrent-writer checks (the `m-db-error` deadlock / lock-wait proof) need
        a second session holding its own transaction across statements, which is
        what `autocommit=False` opens; the same seam serves a manual
        ``execRolledBack`` connection, an executioner that ends another session,
        and any direct statement a case authors verbatim.

        The session belongs to the caller for exactly as long as the choreography
        that asked for it: closing it is the caller's, on every exit including a
        refusal to start. What is tracked here is only the backstop — for one a
        caller never closed at all, and for one whose close left the session
        alive.
        """
        control = self._control().open(
            self._conninfo,
            autocommit=autocommit,
            prepare_threshold=None,
            on_release=self._open.discard,
        )
        self._open.add(control)
        return control

    def interleaved_execution(
        self,
        model: DomainModel | ServingModel,
        *,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> InterleavedExecution:
        """A dedicated session for one interleaved choreography, and its Database.

        The adversarial lane may have to destroy the session a stuck worker is
        parked in, so it never runs over a pooled application connection: each
        group holds a session opened for it alone, behind a controlled adapter
        whose Database is composed here rather than paired with it afterwards.
        Scoped exactly as :meth:`control` is.
        """
        execution = self._interleaved().open(
            self._conninfo,
            model,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
            on_release=self._open.discard,
        )
        self._open.add(execution)
        return execution

    def configured(
        self,
        *,
        pool: PoolOptions | OnDemandOptions | None = None,
        prepare_threshold: int | None = None,
        settings: Mapping[str, str] | None = None,
    ) -> PostgresAdapter:
        """This container's configuration, tuned as a pool proof needs it.

        The proofs that grade capacity, queueing, retention and timeouts need
        configurations the ordinary lanes have no use for, and they must still
        name the database this run opened rather than assembling a connection
        string of their own.

        ``settings`` are session settings a deployment would configure its
        connections with, carried as connection-establishment options so every
        connection this configuration opens — initial, grown, replacement or
        on-demand — arrives already carrying them. Values containing spaces are
        the caller's to escape, exactly as libpq requires.
        """
        from parallax.postgres import PoolOptions

        options = (
            {}
            if not settings
            else {"options": " ".join(f"-c {name}={value}" for name, value in settings.items())}
        )
        return self._built(
            pool=pool if pool is not None else PoolOptions(),
            prepare_threshold=prepare_threshold,
            **options,
        )

    def adapter_for_session_default(self, level: str) -> DatabaseAdapter:
        """Configuration whose connections carry ``level`` as their OWN default.

        ``m-db-port`` puts the default's check at INTAKE — an adapter inspects a
        connection once, when it takes it — so the default has to be there
        BEFORE initialization rather than set on a session afterwards. A
        connection-establishment option is what expresses that: it travels with
        every connection this configuration opens, including one the pool creates
        to replace another, and no borrowed session is mutated to arrange it.
        """
        return self._configuration(options=_SESSION_DEFAULTS[level])

    def release_case_runtimes(self) -> None:
        """Close every runtime a case composed a Database over and left open."""
        self._database.release_runtimes()

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the schema, apply the model-derived DDL, and load the fixtures.

        Fixture binds carry the neutral :class:`JsonDocument` carrier for value
        objects; the adapter recognizes it at its boundary and binds the driver's
        native structured-document type, so no psycopg bind mechanics leak here.
        """
        dialect = self._session.dialect
        for statement in reset_statements():
            self._session.execute_write(statement, [])
        for statement in schema_statements(model, dialect):
            self._session.execute_write(statement, [])
        for sql, binds in fixture_statements(model, fixtures, dialect):
            self._session.execute_write(dialect.to_driver_sql(sql), binds)

    def close(self) -> None:
        """Close this provisioning, and anything a caller left open behind it."""
        self._database.release_runtimes()
        for session in tuple(self._open):
            with suppress(Exception):
                session.close()
        self._session.close()
        self._container.stop()
