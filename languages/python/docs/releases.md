# Release notes

## Unreleased

These changes are not part of any published release.

Applications now import from a small, fixed set of modules. Each distribution's root
holds the calls, configuration, declarations and errors an application spells. Three
vocabulary modules hold the types an application matches on or reads:
`parallax.core.introspection`, `parallax.core.execution_lifecycle` and
`parallax.evolution.operations`. `parallax.aws.postgres` stays separate because it needs
the `parallax-aws[postgres]` extra. Every other module moved under
`parallax.core.internal` or `parallax.evolution.internal`, which carry no compatibility
promise. The [API snapshot](../tests/api/public_api.json) records the complete
application surface, and each name in it has exactly one home. Import each name from
its new home:

| Previously imported from | Now import from |
| -- | -- |
| `parallax.core.base`, `parallax.core.entity`, `parallax.core.execution`, `parallax.core.db_error` or `parallax.core.read_delivery` | `parallax.core` |
| `parallax.core.db_port`: credentials, pool metrics, `ConnectionAcquisitionError` and `DatabaseStartupError` | `parallax.core` |
| `parallax.core.execution_lifecycle`: Providers, Handlers, `RootExecution`, pool observers and the two lifecycle codes | `parallax.core` |
| `parallax.core.metamodel`: inheritance roles and strategies, key generation, `Document`, `Columns` and `MetamodelIssue` | `parallax.core` |
| `parallax.core.metamodel`: identities and read-only metadata | `parallax.core.introspection` |
| `parallax.evolution` or `parallax.evolution.model_evolution`: operation, detail, impact and fact types | `parallax.evolution.operations` |
| `parallax.evolution.model_evolution` or `parallax.evolution.schema_delta`: `evolve`, `schema_delta`, `ABSENT` and the result types | `parallax.evolution` |
| `parallax.postgres.adapter` | `parallax.postgres` |

A name an application only holds or passes along has no application home and is now
internal. That covers `Metamodel`, `model_of`, `FacetKey`, the Wire codec functions, the
database port's adapter protocols, `FailureDiagnostic`, the document codec and storage
layout modules, the `Cardinality` and `PersistenceMode` classes (their members stay at
the root), the evolution `*Delta` unions, `*_ORDER` constants and
`canonical_operation_key`, and the lifecycle per-kind outcome unions, `ActivityStarted`,
`ActivityFinished`, `ActivityFailure`, `TransactionInvocation` and `Literal` aliases
such as `RootExecutionKind`. Match lifecycle events on their concrete classes, and spell a union of them
where you need one.

`DomainModel.meta(key)` is replaced by `DomainModel.entity(key)`, which takes the same
keys and raises the same errors. It returns resolved metadata, and `DomainModel.entities`
lists every Entity's. The name `EntityMetadata` now means this resolved type, imported
from `parallax.core.introspection`. Its `declared` profile holds what the Entity itself
declares, and its `effective` profile adds the members, container, layout and primary
key it inherits. Replace `meta(X).declared_attributes` with
`entity(X).declared.attributes`, and likewise for relationships, Value Objects, As-Of
Axes, container, persistence and layout. A relationship is now a resolved
`RelationshipMetadata` direction rather than its authored declaration. `inheritance`
answers the Entity's role (`AbstractRoot`, `AbstractSubtype` or `ConcreteSubtype`) and
`parent` names its resolved parent. There is no lookup of an index by name; search
`indices`.

`evolve` takes Domain Models, as `prepare_model` and descriptor export already did.
Replace `evolve(model_of(earlier), model_of(later))` with `evolve(earlier, later)`;
`ABSENT` still provisions from nothing. Anything other than a Domain Model raises
`TypeError`.

The Parallax column type `Decimal` is now `Numeric`, so it no longer shares a name with
Python's `decimal.Decimal`, which stays its value type. Messages that print a declared
type now say `Numeric(precision=…, scale=…)`. The core type name, the descriptor's
`decimal(p,s)` spelling and the Wire spelling are unchanged. Declaring
`layout=Columns()` is now accepted and means the same as omitting `layout`.

`InvalidValueError`, a new `UsageError` subclass, reports a value the calling code
stated that doesn't fit its member: the wrong type, outside the type's value space, or
absent where the member requires one. It is raised for `neutral-literal-*`,
`write-value-type-mismatch`, `write-required-attribute-missing`,
`write-required-value-object-missing`, `write-assignment-value-type-mismatch`, and a
Typed query operand of the wrong type (`query-expression-invalid`), on both the Typed
and Wire lanes. Those codes are unchanged, and `except UsageError` still catches it.
Catch it around client input and answer 422. A Wire assignment whose value doesn't fit
its member now reports `write-assignment-value-type-mismatch` in place of
`write-instruction-invalid`.

A `UsageError` with code `transaction-rollback-only` now answers `is_transient` from
the failure that doomed the transaction. A caught transient conflict that outlasts the
retries therefore reads as worth trying later rather than as a permanent failure.

Nine code constants leave the `parallax.core` root: `WRITE_VALUE_NOT_STORED`,
`WRITE_VALUE_ALREADY_STORED`, `WRITE_VALUE_FOREIGN_LIFECYCLE`,
`TRANSACTION_ACCESS_MODE_MISMATCH`, `TRANSACTION_AUTHORITY_MISMATCH`,
`TRANSACTION_OPTION_CONFLICT`, `TRANSACTION_OWNER_MISMATCH`,
`TRANSACTION_TIME_PIN_READ_ONLY` and `EXECUTION_FEATURE_DEFERRED`. Decide from an
error's class and fields. Where a log, alert or test needs a code, compare `code` with
its string. The root keeps `QUERY_TARGET_NOT_IN_MODEL`, `PRINCIPAL_INVALID`,
`LIFECYCLE_PROVIDER_FAILED` and `LIFECYCLE_REENTERED`, and now also publishes
`StoredDataIssue` and `MISSING_STORED_VALUE` beside `InvalidData`.

`pin_of` now accepts a Wire node as `edge_of` does: any node a Wire read published,
direct or projected, answers the `Pin` its read retained, with no I/O and no write
authority. A non-temporal node raises `snapshot-pin-unavailable`, and anything no read
published raises `snapshot-node-required`.

`read_rows` is gone from `ScopedDatabase`, `TxnContext`, and `ReadOnlyTxnContext`, and
`parallax.core.read_delivery` no longer exports `RowsResult` or `PublishedRow`. Migrate
each read to `find` for Typed nodes or `wire.find` for canonical published mappings.
Wire nodes are keyed by logical member name rather than by storage column: read
`node["payload"]`, not `row["payload_hex"]`. Their values are canonical Wire spellings
rather than native Python values. Both reads project the Entity's Value Objects, so a
row whose Value Object holds invalid stored data now arrives as `InvalidData` where
`read_rows` never looked at it, and either read inside a transaction can retain Read
Evidence where `read_rows` retained none.

The object member of `parallax.snapshot.WireValue` is now
`Mapping[str, WireValue]` rather than `dict[str, WireValue]`, so an immutable mapping
type-checks where a `WireValue` is expected, and code that treated a value as a `dict`
statically needs a `Mapping` annotation or a narrowing check. Runtime values are
unchanged.

Typed include paths now reach any depth the read engine supports:
`Ticket.parking.vehicle.dealer` authors and executes with dotted syntax, and each
name past the first relationship is resolved against the serving model's Entity
Classes when an operation binds the query. One- and two-hop class-backed includes
need no migration.

A Typed include that continues past its first relationship now needs a class-backed
serving model. On a model built without Entity Classes, such a path passed to
`db.wire.find(...)` raises `UsageError(query-expression-invalid)` instead of
composing a canonical spelling from Python names. Migrate those reads to a canonical
Wire query, which states each segment's owner. Includes of a single relationship and
canonical Wire input are unaffected.

A continuation naming no relationship of the class it reaches now raises
`UsageError(query-path-invalid)` before I/O, in place of the `ValueError`
that composed spelling reached at the read gate. Stream reads report it on entry.

`view` and `is_view_loaded` now find a narrowed view by the key the read planned, so
a path narrowed to an abstract Entity, or to a concrete sharing its local name with
another in its family, reads the view its include loaded instead of reporting it
unloaded. A retained node answers under the Model Edition that published it.

`parallax.core.db_port.JsonDocument` is removed with no application replacement,
because the database port is now internal.

Starting with `0.2.0`, Parallax no longer supports Intel macOS or musl Linux, including
Alpine, and publishes no `parallax-postgres` wheels for them. Published `0.1.0` wheels
remain available. Move Intel macOS deployments to a supported host and Alpine
deployments to a glibc-based Linux environment. Building from source on a removed
platform does not make it supported.

## 0.1.0

First coordinated release for early adopters.

The release includes the common runtime, Snapshot application API, PostgreSQL
adapter, model evolution and schema deltas, descriptor interchange, and optional
AWS credential providers. The conformance distribution remains unpublished.
Install the packages your application needs using
[Getting started](guide/01-getting-started.md#install).

The public baseline includes immutable Typed and Wire query results, explicit
transactions, bounded conflict retries, optimistic and locking writes, temporal
history, model evolution and explicit database resource ownership. The
[Python binding](../spec/python.md) and executable guide define the supported
surface, including the implemented errors and temporal-bound interfaces.

The [compatibility and maintenance policy](releasing.md#compatibility-and-maintenance)
explains coordinated versions, backward-compatible patch releases, migration
guidance for breaking pre-1.0 minor changes and newest-minor-only maintenance.
Environment support is declared by the metadata and binding links in
[Getting started](guide/01-getting-started.md#install).

All production wheels and sdists carry the Apache-2.0 licence and attribution
notice. See the [repository licence](../../../LICENSE).
