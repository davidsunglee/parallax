from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from parallax.conformance import case_format
from parallax.conformance._case_literal import normalize_case_literal
from parallax.core import storage_layout
from parallax.core.base import JSON, TIMESTAMP, DocumentValue, NeutralType, retain_document_value
from parallax.core.db_port import DatabaseRuntime, Password, StructuredDocument
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.document_codec import (
    MemberShape,
    OccurrenceDefinition,
    ScalarDefinition,
    encode_leaf,
    encode_scalar_many,
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
    entity_by_name,
)
from parallax.core.storage_layout import (
    ColumnSlot,
    EntityLayoutView,
    RelationalDocument,
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
    from parallax.conformance._lifecycle_observation import LifecycleObservation
    from parallax.conformance._postgres_control import (
        PostgresControl,
        PostgresInterleavedExecution,
    )
    from parallax.core.db_port import (
        AccessMode,
        Bind,
        ConnectionContextSource,
        CredentialSource,
        DatabaseAdapter,
        DatabaseConnection,
        DocumentReadOrdinals,
        DriverManaged,
        IsolationLevel,
        OrderedWriteTransport,
        PipelineStatement,
        PoolMetricsSource,
        Route,
        RouteCapabilities,
        Row,
        TransactionOutcome,
    )
    from parallax.core.entity import DomainModel
    from parallax.core.execution import ServingModel, TxnOptions
    from parallax.core.unit_work import Clock
    from parallax.postgres import (
        OnDemandOptions,
        PoolOptions,
        PostgresAdapter,
        PostgresEndpoint,
        PostgresRole,
    )

__all__ = [
    "CONFORMANCE_LOGIN",
    "ContainerDatabase",
    "Provisioner",
    "RuntimeLedger",
    "TrackedAdapter",
    "conformance_credentials",
    "database_authorization",
    "fixture_collection",
    "fixture_document",
    "fixture_literal",
    "fixture_statements",
    "install_authority_fixtures",
    "load_fixtures",
    "reset_database",
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
) -> tuple[str, AttributeMetadata | MemberShape] | None:
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


def fixture_document(
    shape: MemberShape, row: Mapping[str, object], *, preserve_unknown: bool = True
) -> object:
    """One fixture row's Structured Column, with every declared leaf spelled by the codec.

    Each document-resident member is authored in the row under its own member
    name, in the very spelling it would take if the layout had given it a Column
    of its own — a leaf as the neutral wire value, an occurrence as that
    occurrence's own document — so one fixture file describes one logical row
    under either layout. An omitted key stays absent, an authored null becomes
    JSON null, and a `many` occurrence always contributes its array.

    A fixture seeds stored data rather than writing through the framework, so an
    occurrence document keeps undeclared keys and a value contradicting its
    member's kind is stored as authored: the write path's encoder produces
    neither, and corpus cases read both back.
    """
    document: dict[str, object] = {}
    for member in shape.members:
        many = member.multiplicity is Multiplicity.MANY
        raw = row.get(member.name)
        if raw is None:
            if many:
                document[member.name] = ()
            elif member.name in row:
                document[member.name] = None
        elif isinstance(member, ScalarDefinition):
            document[member.name] = (
                fixture_collection(member.type, raw)
                if many
                else encode_leaf(member.type, fixture_literal(member.type, raw))
            )
        else:
            document[member.name] = _fixture_occurrence(member, raw)
    encoded = cast("Mapping[str, object]", retain_document_value(document))
    if not preserve_unknown:
        return encoded
    declared = {member.name for member in shape.members}
    unknown = {name: value for name, value in row.items() if name not in declared}
    if not unknown:
        return encoded
    canonical = encode_wire(JSON, decode_wire(JSON, cast("WireValue", unknown)))
    return {**encoded, **cast("Mapping[str, object]", canonical)}


def fixture_collection(element_type: NeutralType, raw: object) -> object:
    """One fixture scalar collection's stored array, each element spelled by
    the codec; a value that is not an array is stored as authored."""
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return raw
    return encode_scalar_many(
        element_type,
        tuple(fixture_literal(element_type, element) for element in cast("Sequence[object]", raw)),
    )


def _fixture_occurrence(member: OccurrenceDefinition, raw: object) -> object:
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
    shape: MemberShape | None,
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
            if shape is None:  # pragma: no cover - a shared document slot owns residency
                raise ValueError(f"{view.entity.canonical}: no document resident selection")
            columns.append(dialect.quote(slot.column.name))
            binds.append(
                StructuredDocument(
                    cast("DocumentValue", fixture_document(shape, row, preserve_unknown=False))
                )
            )
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
        elif (
            isinstance(projection, AttributeMetadata)
            and projection.multiplicity is Multiplicity.MANY
        ):
            binds.append(
                StructuredDocument(
                    cast("DocumentValue", fixture_collection(projection.type, value))
                )
            )
        elif isinstance(projection, MemberShape):
            binds.append(
                StructuredDocument(
                    cast(
                        "DocumentValue",
                        fixture_document(projection, cast("Mapping[str, object]", value))
                        if isinstance(value, Mapping)
                        else value,
                    )
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
    byte-identical SQL (the Python binding ``loadFixtures``). A physical column with no
    member in the row is skipped, so only authored members bind; a
    table-per-hierarchy concrete's discriminator always binds its own derived
    ``tagValue``.

    A block naming no row-owning Entity, naming one a second time, or spelling a
    bare local name two namespaces share, a block that is not a list, a row that
    is not a mapping, and a row naming a member its Entity's family does not
    declare are refused rather than dropped (`m-case-format`), so a mistyped
    fixture cannot seed less, or other tables, than it states.
    """
    blocks = _fixture_blocks(model, fixtures)
    statements: list[tuple[str, list[object]]] = []
    for entity in model.entities:
        resolved = blocks.get(entity.identity)
        if resolved is None:
            continue
        (block, view) = resolved
        canonical = entity.identity.canonical
        rows = fixtures[block]
        if not isinstance(rows, Sequence) or isinstance(rows, str | bytes):
            raise ValueError(f"{canonical}: a fixture block must be a list of rows")
        residents = view.document_residents
        shape = view.member_selection.shape
        for row in cast("Sequence[object]", rows):
            if not isinstance(row, Mapping):
                raise ValueError(f"{canonical}: a fixture row must be a mapping, not {row!r}")
            authored = cast("Mapping[str, object]", row)
            undeclared = sorted(member for member in authored if shape.position(member) is None)
            if undeclared:
                raise ValueError(
                    f"{canonical}: a fixture row names {undeclared!r}, which the Entity's "
                    "family declares no member of"
                )
            statements.append(
                _fixture_insert(
                    model,
                    view,
                    None if residents is None else residents.shape,
                    authored,
                    dialect,
                )
            )
    return statements


def _fixture_blocks(
    model: Metamodel, fixtures: Mapping[str, object]
) -> dict[EntityIdentity, tuple[str, EntityLayoutView]]:
    """The one fixture block each row-owning Entity's rows come from, with its
    view, resolving every block key by the reference-position spelling rule."""
    facet = storage_layout.storage_layout_facet_of(model)
    blocks: dict[EntityIdentity, tuple[str, EntityLayoutView]] = {}
    for block in fixtures:
        entity = entity_by_name(model, block)
        if entity is None:
            shared = sorted(
                candidate.identity.canonical
                for candidate in model.entities
                if candidate.identity.name == block
            )
            if shared:
                raise ValueError(
                    f"fixture block {block!r} is ambiguous: {shared!r} share that local "
                    "name; key it by one canonical spelling"
                )
            raise ValueError(f"fixture block {block!r} names no Entity of the model")
        identity = entity.identity
        view = facet.entity(identity)
        if view is None:
            raise ValueError(
                f"fixture block {block!r} names {identity.canonical}, which owns no rows"
            )
        (earlier, _view) = blocks.setdefault(identity, (block, view))
        if earlier != block:
            raise ValueError(
                f"fixture blocks {earlier!r} and {block!r} both name {identity.canonical}"
            )
    return blocks


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

CONFORMANCE_LOGIN: Final[str] = "parallax_conformance_login"
"""The login every conformance application session authenticates as."""

_TEST_PASSWORD = "parallax-conformance-password"
_DEFAULT_ROLE = "parallax_conformance_default"
_ROLE_AUTHORIZATIONS: Mapping[str, str] = {
    "role-a": "parallax_conformance_role_a",
    "role-b": "parallax_conformance_role_b",
}


def conformance_credentials() -> Password:
    """The conformance login's secret, as the adapter's credential source takes it."""
    return Password(_TEST_PASSWORD)


def database_authorization(selector: str) -> PostgresRole:
    """The database authorization a case's ``role-a`` / ``role-b`` selector names."""
    from parallax.postgres import PostgresRole

    try:
        role = _ROLE_AUTHORIZATIONS[selector]
    except KeyError as unknown:
        raise ValueError(f"unknown database authorization fixture {selector!r}") from unknown
    return PostgresRole(role)


def install_authority_fixtures(session: DatabaseConnection) -> None:
    """Create the conformance login and the roles it may act as, on a fresh server.

    This administers a server the harness started itself, so it stays apart
    from :func:`reset_database`, which needs only a database the conformance
    roles already exist on.
    """
    roles = (_DEFAULT_ROLE, *_ROLE_AUTHORIZATIONS.values())
    for role in roles:
        session.execute_write(f'create role "{role}"', [])
    session.execute_write(
        f"create role \"{CONFORMANCE_LOGIN}\" login password '{_TEST_PASSWORD}'", []
    )
    for role in roles:
        session.execute_write(f'grant "{role}" to "{CONFORMANCE_LOGIN}"', [])
    session.execute_write(f'alter role "{CONFORMANCE_LOGIN}" set role to "{_DEFAULT_ROLE}"', [])


def reset_database(
    session: DatabaseConnection, model: Metamodel, fixtures: Mapping[str, object]
) -> None:
    """Reset the schema, apply the model-derived DDL, load the fixtures, and grant
    the conformance roles what a case's sessions do with them.

    Fixture binds carry a :class:`StructuredDocument` for each value object; the
    adapter recognizes it at its boundary and binds the driver's
    native structured-document type, so no psycopg bind mechanics leak here.
    """
    dialect = session.dialect
    for statement in reset_statements():
        session.execute_write(statement, [])
    for statement in schema_statements(model, dialect):
        session.execute_write(statement, [])
    for sql, binds in fixture_statements(model, fixtures, dialect):
        session.execute_write(dialect.to_driver_sql(sql), binds)
    for role in (_DEFAULT_ROLE, *_ROLE_AUTHORIZATIONS.values()):
        session.execute_write(f'grant usage on schema public to "{role}"', [])
        session.execute_write(
            f'grant select, insert, update, delete on all tables in schema public to "{role}"',
            [],
        )


class RuntimeLedger:
    """The runtimes opened through the configurations that share it and may still be open.

    A Database that is closed retires its own; what stays on the ledger is what a
    case composed and did not close. Releasing it closes those, because a session
    that accumulated a pool per case would run the server out of connections long
    before the corpus ran out of cases, and counts them, so the case can be failed
    for leaving them.
    """

    def __init__(self) -> None:
        self._opened: list[DatabaseRuntime[PostgresRole]] = []

    def track(self, runtime: DatabaseRuntime[PostgresRole]) -> DatabaseRuntime[PostgresRole]:
        """``runtime``, kept on this ledger until it closes."""
        tracked = _TrackedRuntime(runtime, self._opened.remove)
        self._opened.append(tracked)
        return tracked

    def release(self) -> int:
        """Close every runtime still open, containing ordinary failures, and
        answer how many there were.

        Every close is attempted whatever the ones before it did; the first
        interrupt propagates only once all of them have been.
        """
        interrupted: BaseException | None = None
        left_open = tuple(self._opened)
        for runtime in left_open:
            try:
                with suppress(Exception):
                    runtime.close()
            except BaseException as interrupt:
                if interrupted is None:
                    interrupted = interrupt
        self._opened.clear()
        if interrupted is not None:
            raise interrupted
        return len(left_open)


class TrackedAdapter:
    """Configuration whose every runtime is kept on one :class:`RuntimeLedger`."""

    def __init__(self, adapter: PostgresAdapter, ledger: RuntimeLedger) -> None:
        self._adapter = adapter
        self._ledger = ledger

    @property
    def dialect(self) -> Dialect:
        return self._adapter.dialect

    @property
    def writer(self) -> PostgresEndpoint:
        return self._adapter.writer

    def open(self) -> DatabaseRuntime[PostgresRole]:
        return self._ledger.track(self._adapter.open())


class ContainerDatabase:  # pragma: no cover - exercised by the Docker-backed lanes
    """One provisioned database as the two halves a case needs of it.

    The ``DatabaseAdapter`` half is configuration for the shipped adapter, so a
    case's modeled work runs through the real pooled runtime it is meant to
    prove. The ``DatabaseConnection`` half forwards to the provisioner's own
    session, so the DDL, the fixtures, a verbatim ``given.apply`` and a golden
    read of stored state run outside anything under test.

    The runtimes it hands out are kept on ``adapter``'s ledger, which its owner
    releases.
    """

    def __init__(self, adapter: TrackedAdapter, session: DriverControl) -> None:
        self._adapter = adapter
        self._session = session

    @property
    def dialect(self) -> Dialect:
        return self._session.dialect

    def open(self) -> DatabaseRuntime[PostgresRole]:
        return self._adapter.open()

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        return self._session.execute(sql, binds, document_reads, read_only=read_only)

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement], *, read_only: bool = False
    ) -> list[list[Row]]:
        return self._session.execute_pipeline(statements, read_only=read_only)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return self._session.execute_write(sql, binds)

    @property
    def ordered_write_transport(self) -> OrderedWriteTransport | None:
        return self._session.ordered_write_transport

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        access_mode: AccessMode | None = None,
    ) -> TransactionOutcome[T]:
        return self._session.transaction(body, isolation=isolation, access_mode=access_mode)


class _TrackedRuntime:
    """A runtime that tells its ledger when its Database closes it.

    Closing is idempotent underneath, so the ledger may close one this already
    reported; what the report buys is that the ledger closes and counts only what
    a case actually left behind.
    """

    def __init__(
        self,
        inner: DatabaseRuntime[PostgresRole],
        on_close: Callable[[DatabaseRuntime[PostgresRole]], None],
    ) -> None:
        self._inner = inner
        self._on_close: Callable[[DatabaseRuntime[PostgresRole]], None] | None = on_close

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    @property
    def routes(self) -> Mapping[Route, RouteCapabilities]:
        return self._inner.routes

    @property
    def pool_metrics(self) -> tuple[PoolMetricsSource, ...]:
        return self._inner.pool_metrics

    @property
    def login_identity(self) -> str:
        return self._inner.login_identity

    def login_source(self) -> ConnectionContextSource:
        return self._inner.login_source()

    def principal_source(self, authorization: PostgresRole) -> ConnectionContextSource:
        return self._inner.principal_source(authorization)

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
        self._admin_conninfo = self._container.get_connection_url().replace(
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
            self._admin_conninfo, autocommit=True, prepare_threshold=None
        )
        install_authority_fixtures(self._session)
        from psycopg.conninfo import make_conninfo

        # Composed from the container's own host, port and database rather than
        # derived from the admin URL by overriding its user: that URL carries the
        # container superuser's password, and a string derived from it would
        # still carry it into an adapter that now refuses one.
        self._conninfo = make_conninfo(
            host=self._container.get_container_host_ip(),
            port=self._container.get_exposed_port(self._container.port),
            dbname=self._container.dbname,
            user=CONFORMANCE_LOGIN,
        )
        # Every runtime any configuration of this container opens, the case
        # port's and a tuned proof's alike.
        self._ledger = RuntimeLedger()
        self._database = ContainerDatabase(self._configuration(), self._session)
        # Every scoped session that may still be alive. One removes itself as
        # soon as its session is gone — which is its close, or, for a close that
        # waited on a borrower, the release that completed it. What
        # remains is what a caller never closed and what would not close, and
        # `close` below is the backstop that ends both.
        self._open: set[PostgresControl | PostgresInterleavedExecution] = set()

    def _configuration(self, **conninfo_options: str) -> TrackedAdapter:
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
            credentials=self.credentials,
            conninfo_options=conninfo_options,
        )

    def _built(
        self,
        *,
        pool: PoolOptions | OnDemandOptions,
        prepare_threshold: int | None,
        credentials: CredentialSource | DriverManaged,
        conninfo_options: Mapping[str, str],
        acquire_timeout: float | None = None,
        startup_timeout: float | None = None,
        reader: PostgresEndpoint | None = None,
        reader_startup: str | None = None,
    ) -> TrackedAdapter:
        """The shipped configuration for this container, under ``conninfo_options``,
        its every runtime kept on this run's ledger.

        An omitted budget or reader startup takes the adapter's own default.
        """
        chosen = {
            name: value
            for name, value in (
                ("acquire_timeout", acquire_timeout),
                ("startup_timeout", startup_timeout),
                ("reader_startup", reader_startup),
            )
            if value is not None
        }
        configured = self.adapter()(
            writer=self._endpoint(pool, credentials, conninfo_options),
            reader=reader,
            prepare_threshold=prepare_threshold,
        )
        return TrackedAdapter(
            dataclasses.replace(configured, **chosen) if chosen else configured, self._ledger
        )

    def _endpoint(
        self,
        pool: PoolOptions | OnDemandOptions,
        credentials: CredentialSource | DriverManaged,
        conninfo_options: Mapping[str, str],
    ) -> PostgresEndpoint:
        from psycopg.conninfo import make_conninfo

        from parallax.postgres import PostgresEndpoint

        return PostgresEndpoint(
            make_conninfo(self._conninfo, **conninfo_options),
            credentials=credentials,
            pool=pool,
        )

    @property
    def port(self) -> CaseDatabase:
        """This container as the two halves a case runs against."""
        return self._database

    @property
    def connection_info(self) -> str:
        """The running container's libpq connection string for isolated report children.

        It says where the test login is, and carries no secret: a child takes
        the password beside it and supplies it the way its own composition
        chooses.
        """
        return self._conninfo

    @property
    def credentials(self) -> Password:
        """The test login's secret, as the adapter's credential source takes it."""
        return conformance_credentials()

    @property
    def login_identity(self) -> str:
        return CONFORMANCE_LOGIN

    @property
    def default_role(self) -> PostgresRole:
        from parallax.postgres import PostgresRole

        return PostgresRole(_DEFAULT_ROLE)

    def authorization(self, selector: str) -> PostgresRole:
        return database_authorization(selector)

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
            self._admin_conninfo,
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
        observation: LifecycleObservation,
        options: TxnOptions | None = None,
        clock: Clock | None = None,
    ) -> InterleavedExecution:
        """A dedicated session for one interleaved choreography, and its Database.

        The adversarial lane may have to destroy the session a stuck worker is
        parked in, so it never runs over a pooled application connection: each
        group holds a session opened for it alone, behind a controlled adapter
        whose Database is composed here rather than paired with it afterwards.
        Scoped exactly as :meth:`control` is.

        This is the one view that dials raw psycopg rather than the adapter, so
        it is also the one that composes the two halves back into a single
        string libpq can authenticate from.
        """
        from psycopg.conninfo import make_conninfo

        execution = self._interleaved().open(
            make_conninfo(self._conninfo, password=_TEST_PASSWORD),
            model,
            observation=observation,
            options=options,
            clock=clock,
            on_release=self._open.discard,
        )
        self._open.add(execution)
        return execution

    def configured(
        self,
        *,
        pool: PoolOptions | OnDemandOptions | None = None,
        acquire_timeout: float | None = None,
        startup_timeout: float | None = None,
        prepare_threshold: int | None = None,
        settings: Mapping[str, str] | None = None,
        credentials: CredentialSource | DriverManaged | None = None,
        reader: PostgresEndpoint | None = None,
        reader_startup: str | None = None,
    ) -> TrackedAdapter:
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

        ``credentials`` is how a proof about the credential seam itself crosses
        it: a counting or refusing source reaches the adapter through the same
        keyword a deployment uses. Omitting it takes this container's own test
        login secret.

        ``reader`` adds a reader route — usually one of this container's own
        :meth:`endpoint` values — and ``reader_startup`` says what opening does
        when it cannot be reached.

        A runtime it opens and a proof leaves open is closed and counted with the
        case's own.
        """
        from parallax.postgres import PoolOptions

        return self._built(
            pool=pool if pool is not None else PoolOptions(),
            prepare_threshold=prepare_threshold,
            credentials=credentials if credentials is not None else self.credentials,
            conninfo_options=self._session_options(settings),
            acquire_timeout=acquire_timeout,
            startup_timeout=startup_timeout,
            reader=reader,
            reader_startup=reader_startup,
        )

    @staticmethod
    def _session_options(settings: Mapping[str, str] | None) -> Mapping[str, str]:
        """``settings`` as the connection option that carries them to every session."""
        if not settings:
            return {}
        return {"options": " ".join(f"-c {name}={value}" for name, value in settings.items())}

    def endpoint(
        self,
        *,
        pool: PoolOptions | OnDemandOptions | None = None,
        settings: Mapping[str, str] | None = None,
        credentials: CredentialSource | DriverManaged | None = None,
    ) -> PostgresEndpoint:
        """This container as one endpoint, for a proof composing several routes.

        ``settings`` and ``credentials`` mean what they mean to
        :meth:`configured`. Two endpoints over this one container are two routes
        to the same server, which is what a routing proof needs where
        replication does not matter.
        """
        from parallax.postgres import PoolOptions

        return self._endpoint(
            pool if pool is not None else PoolOptions(),
            credentials if credentials is not None else self.credentials,
            self._session_options(settings),
        )

    def adapter_for_session_default(self, level: str) -> DatabaseAdapter[PostgresRole]:
        """Configuration whose connections carry ``level`` as their OWN default.

        ``m-db-port`` puts the default's check at INTAKE — an adapter inspects a
        connection once, when it takes it — so the default has to be there
        BEFORE initialization rather than set on a session afterwards. A
        connection-establishment option is what expresses that: it travels with
        every connection this configuration opens, including one the pool creates
        to replace another, and no borrowed session is mutated to arrange it.
        """
        return self._configuration(options=_SESSION_DEFAULTS[level])

    def release_case_runtimes(self) -> int:
        """Close every runtime a case opened over this container and left open,
        and answer how many there were."""
        return self._ledger.release()

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the schema, apply the model-derived DDL, and load the fixtures."""
        reset_database(self._session, model, fixtures)

    def close(self) -> None:
        """Close this provisioning, and anything a caller left open behind it."""
        self._ledger.release()
        for session in tuple(self._open):
            with suppress(Exception):
                session.close()
        self._session.close()
        self._container.stop()
