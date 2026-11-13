# Release notes

## Unreleased

These changes are not part of any published release.

You now have to tell Parallax where your tables live. `connect(adapter, model)`,
`prepare_model(model, edition=...)` and `evolve(...)` each take a database binding, and
without one they raise `UsageError` with code `binding-required`. In 0.1.0 your tables
were found through the connection's `search_path`, usually in `public`. To keep them
where they are, bind that schema and pass the binding everywhere:

```python
from parallax.postgres import PostgresBinding, PostgresLocation

binding = PostgresBinding(default=PostgresLocation(schema="public"))

connect(adapter, model, binding=binding)
prepare_model(model, binding=binding, edition="2026-11")
evolve(earlier, later, earlier_binding=binding, later_binding=binding)
evolve(ABSENT, model, later_binding=binding)
```

`connect` with a `ServingModel` takes no binding, because its selections already carry
one. A binding can also put some tables in other schemas or under other names, and can
be read from YAML or JSON; [Database bindings](guide/02-modeling.md#database-bindings)
shows how.

`schema_delta` no longer takes a Dialect. It renders for the later binding's backend, so
`schema_delta(evolution, POSTGRES)` becomes `schema_delta(evolution)`. Every statement
Parallax generates or runs now names its table with the schema, such as
`"public"."orders"`, so if you compare generated migrations against saved ones, expect
that diff once.

Moving a table or sequence by changing its binding shows up in `evolve` as a new
`TableRelocated` or `SequenceRelocated` operation, and `ServingModel.publish` refuses a
selection that moves one with `UsageError` code `publication-relocation-refused`. Code
that matches every evolution operation needs cases for the two new ones.
[Changing a binding](guide/07-model-evolution.md#changing-a-binding) covers this.

Parallax no longer supports Intel macOS or musl Linux, including Alpine, and publishes
no `parallax-postgres` wheels for them. The 0.1.0 wheels stay on PyPI. Move Intel Mac
deployments to a supported host and Alpine deployments to a glibc-based Linux image.
Building from source on those platforms doesn't make them supported.

Applications now import from a few fixed modules. Each distribution's root module has
everything an application calls, configures, declares or catches. Three more modules
hold types you match on or read: `parallax.core.introspection`,
`parallax.core.execution_lifecycle` and `parallax.evolution.operations`.
`parallax.aws.postgres` stays separate because it needs the `parallax-aws[postgres]`
extra. Everything else moved under `parallax.core.internal` or
`parallax.evolution.internal`, which can change in any release. The
[API snapshot](../tests/api/public_api.json) lists every public name, and each name
lives in exactly one module. Update your imports:

| 0.1.0 import | Import from now |
| -- | -- |
| `parallax.core.base`, `parallax.core.entity`, `parallax.core.execution`, `parallax.core.db_error` or `parallax.core.read_delivery` | `parallax.core` |
| `parallax.core.db_port`: credentials, pool metrics, `ConnectionAcquisitionError` and `DatabaseStartupError` | `parallax.core` |
| `parallax.core.execution_lifecycle`: Providers, Handlers, `RootExecution`, pool observers and the two lifecycle codes | `parallax.core` |
| `parallax.core.metamodel`: inheritance roles and strategies, key generation, `Document`, `Columns` and `MetamodelIssue` | `parallax.core` |
| `parallax.snapshot`: `NoResultFound` and `TooManyResultsFound` | `parallax.core` |
| `parallax.core.metamodel`: identities and read-only metadata | `parallax.core.introspection` |
| `parallax.evolution` or `parallax.evolution.model_evolution`: operation, detail, impact and fact types | `parallax.evolution.operations` |
| `parallax.evolution.model_evolution` or `parallax.evolution.schema_delta`: `evolve`, `schema_delta`, `ABSENT` and the result types | `parallax.evolution` |
| `parallax.postgres.adapter` | `parallax.postgres` |

Names an application only holds or passes along are now internal, with no public
replacement:

- `Metamodel`, `model_of`, `FacetKey` and `FailureDiagnostic`;
- the Wire codec functions, the document codec and the storage layout modules;
- the database port's adapter protocols and `JsonDocument`;
- the `Cardinality` and `PersistenceMode` classes, though their members stay public;
- the evolution `*Delta` unions, the `*_ORDER` constants and `canonical_operation_key`;
- the lifecycle outcome unions, `ActivityStarted`, `ActivityFinished`,
  `ActivityFailure`, `TransactionInvocation` and `Literal` aliases such as
  `RootExecutionKind`. Match lifecycle events on their concrete classes, and write the
  union out yourself if you need one.

`DomainModel.meta(key)` is now `DomainModel.entity(key)`. It takes the same keys and
raises the same errors, but returns resolved metadata, and `DomainModel.entities` lists
it for every Entity. `EntityMetadata`, imported from `parallax.core.introspection`, now
names this resolved type. Its `declared` profile is what the Entity declares itself, and
its `effective` profile adds the members, container, layout and primary key it inherits.
So `meta(X).declared_attributes` becomes `entity(X).declared.attributes`, and the same
goes for relationships, Value Objects, As-Of Axes, container, persistence and layout.
Also:

- A relationship is now a resolved `RelationshipMetadata` direction, not the declaration
  you wrote.
- `inheritance` gives the Entity's role (`AbstractRoot`, `AbstractSubtype` or
  `ConcreteSubtype`), and `parent` gives its resolved parent.
- There's no lookup of an index by name; search `indices` instead.

`evolve` now takes Domain Models, like `prepare_model` and descriptor export already
did. Replace `evolve(model_of(earlier), model_of(later))` with `evolve(earlier, later)`.
`ABSENT` still means starting from nothing, and anything else raises `TypeError`.

`AsOfAxisAltered` and its `StartAttributeChanged` and `EndAttributeChanged` details are
gone. No pair of valid models could produce them, because an axis always has the same
endpoint attributes. Delete any branch that handled them.

The column type `Decimal` is now `Numeric`, so it no longer clashes with Python's
`decimal.Decimal`, which is still its value type. Descriptors now spell it
`numeric(p,s)` instead of `decimal(p,s)`, and a descriptor using the old spelling no
longer loads. If you keep the deployed model as a descriptor for `evolve`, replace
`decimal(` with `numeric(` in it. Messages that print a declared type now say
`Numeric(precision=…, scale=…)`. Wire values are unchanged. `layout=Columns()` is now
accepted and means the same as leaving `layout` out.

Every error Parallax raises is now a `ParallaxError`. Each one has a `code`, such as
`query-path-invalid`, and an `is_transient` flag that says whether trying again later
could work. Most 0.1.0 error classes are gone: what used to be a class is now a code on
one of a few classes. [Errors](guide/08-errors.md) shows the whole tree and what each
class asks you to do.

Two things are easy to miss:

- Parallax errors are no longer `ValueError`, `TypeError`, `RuntimeError` or
  `LookupError`, so an `except ValueError:` that used to catch a bad query now lets it
  through. Catch the Parallax class instead. `UnloadedRelationshipError` is still an
  `AttributeError`, so `hasattr` behaves as before, and plain argument mistakes, such as
  `None` where an option belongs, still raise `TypeError` or `ValueError`.
- `ExecutionFailure` is gone. An error leaving a transaction or a standalone read now
  arrives as itself, with a note naming the model edition the work ran under. Replace
  `except ExecutionFailure as failure: handle(failure.cause)` with an `except` for the
  class you want. If you need the edition as data, read `tx.edition`.

Catch these instead of the removed classes:

| 0.1.0 class | Catch now |
| -- | -- |
| `EntityDefinitionError`, `MetamodelDefinitionError`, `MetamodelLookupError`, `QueryDefinitionError`, `QueryTargetError`, `ModelRejectedError`, `TemporalReadError`, `UndeclaredAxisError`, `StreamStateError`, `SnapshotConnectionError`, `SnapshotInspectionError`, `WireEncodingError`, `WriteAssignmentError`, `KeyedWriteValueError`, `InvalidAuthorizationError`, `InvalidPrincipalError`, `ExecutionLifecycleProviderError`, `ExecutionLifecycleReentryError` and every `Transaction*Error` | `UsageError` |
| `RollbackOnlyError`, `EscapedTransactionError`, `WriteEvidenceError`, `UnobservedVersionError`, `WriteInstructionError`, `InstructionRejectedError` and `WriteRejectedError` from the unit of work | `UsageError` |
| `WireDecodingError` | `InvalidValueError`, a `UsageError` |
| `DeferredFeatureError` | `UnsupportedError` |
| `StoredDataDecodingError`, `StreamContinuationError` and `SnapshotConsistencyError` | `InvalidDataError` |
| `OptimisticLockConflictError`, `TemporalConflictError`, `StaleWriteError` and `MissingTargetError` | `ConflictError` |
| `DescriptorSyntaxError`, `DescriptorSchemaError` and `DescriptorValueError` | `DescriptorError` |
| `GraphConstructionError`, `SnapshotMaterializationError`, `DescriptorExportError`, `PhysicalIndexNameCollisionError`, `WriteResultIntegrityError`, `WriteResultError` and `CardinalityCorruptionError` | `InternalError`, a bug in Parallax rather than something to handle |

Some classes stayed but changed:

- `EditError`, `MetamodelValidationError` and `DescriptorError` are now `UsageError`s.
  `InvalidDataError`, `TransactionRollbackError`, `NoResultFound` and
  `TooManyResultsFound` are no longer `RuntimeError`s.
- `WritePreconditionError` is now a `ConflictError`. Its `entity` is the canonical
  Entity name as a string instead of an `EntityIdentity`, and it also has `key`.
- `SnapshotConsistencyError`'s fields (`object_key`, `coordinates`, `members` and
  `fetched_rows`) have no replacement; the message carries those details.
- `DescriptorSchemaViolation` and `DescriptorValueViolation` are merged into
  `DescriptorViolation`.

`InvalidValueError` is a new `UsageError` for a value your code passed that doesn't fit
its member: the wrong type, out of range, or missing where the member needs one. It
covers the `neutral-literal-*` codes, `write-value-type-mismatch`,
`write-required-attribute-missing`, `write-required-value-object-missing`,
`write-assignment-value-type-mismatch` and a Typed query operand of the wrong type
(`query-expression-invalid`), for both Typed and Wire calls. Catch it around client
input and answer 422. A Wire assignment whose value doesn't fit now reports
`write-assignment-value-type-mismatch` instead of `write-instruction-invalid`.

Transactions now decide whether to retry from `is_transient` rather than from the error's
class. `DatabaseError.is_retriable` is gone; use `is_transient`. It is broader: it is
also true for a lock wait timeout, which Parallax itself doesn't retry. A `UsageError`
with code `transaction-rollback-only` takes `is_transient` from the failure that doomed
the transaction, so a transient conflict that outlasts the retries still reads as worth
trying later.

Nine code constants are gone from `parallax.core`: `WRITE_VALUE_NOT_STORED`,
`WRITE_VALUE_ALREADY_STORED`, `WRITE_VALUE_FOREIGN_LIFECYCLE`,
`TRANSACTION_ACCESS_MODE_MISMATCH`, `TRANSACTION_AUTHORITY_MISMATCH`,
`TRANSACTION_OPTION_CONFLICT`, `TRANSACTION_OWNER_MISMATCH`,
`TRANSACTION_TIME_PIN_READ_ONLY` and `EXECUTION_FEATURE_DEFERRED`. Branch on the error's
class and fields instead. If a log, alert or test needs a code, compare `code` with the
string. `QUERY_TARGET_NOT_IN_MODEL`, `PRINCIPAL_INVALID`, `LIFECYCLE_PROVIDER_FAILED`
and `LIFECYCLE_REENTERED` stay, and `StoredDataIssue` and `MISSING_STORED_VALUE` are new
there, next to `InvalidData`.

`read_rows` is gone from `ScopedDatabase`, `TxnContext` and `ReadOnlyTxnContext`, along
with `RowsResult` and `PublishedRow`. Use `find` for Typed results or `wire.find` for
Wire nodes. A few things differ from `read_rows`:

- Wire nodes are keyed by member name, not storage column: `node["payload"]`, not
  `row["payload_hex"]`.
- Values are canonical Wire spellings, not native Python values.
- Both reads decode the Entity's Value Objects, so a row whose Value Object holds bad
  stored data now comes back as `InvalidData`.
- Inside a transaction, either read can retain Read Evidence, which `read_rows` never
  did.

Typed include paths can now go as deep as the read engine supports, such as
`Ticket.parking.vehicle.dealer`. Each name after the first relationship is looked up on
the serving model's Entity Classes when the query runs. One- and two-hop includes on a
class-backed model need no changes. A path that goes past its first relationship now
needs a class-backed serving model, though: on a model built without Entity Classes,
passing one to `db.wire.find(...)` raises `UsageError` code `query-expression-invalid`.
Write those reads as canonical Wire queries, which name each step's owner. Single-hop
includes and canonical Wire input are unaffected.

A continuation that names no relationship of the class it reaches now raises `UsageError`
code `query-path-invalid` before anything is read, instead of a `ValueError` during the
read. Streams raise it when you start them.

`view` and `is_view_loaded` now look up a narrowed view by the key the read planned. A
path narrowed to an abstract Entity, or to a concrete that shares its local name with
another in its family, now finds the view its include loaded instead of reporting it
unloaded. A retained node answers under the Model Edition that published it.

A Wire node from an inheritance family now says its concrete type under `_type`, not
`familyVariant`, and the value is the Entity's canonical name. For an Entity in a
namespace that includes the namespace: `billing.CardPayment`, where 0.1.0 said
`CardPayment`. Read `node["_type"]` instead of `node["familyVariant"]`. Because `_type`
is now reserved, a model may no longer store an attribute, a Value Object or a
table-per-hierarchy tag in a column named `_type`. Rename such a column in the database
and declare the new name with `column=` or `TablePerHierarchy(tag_column=...)`.
`familyVariant` is now an ordinary name you can use.

The object member of `parallax.snapshot.WireValue` is now `Mapping[str, WireValue]`
instead of `dict[str, WireValue]`, so an immutable mapping type-checks as a
`WireValue`. Code that treats one as a `dict` needs a `Mapping` annotation or a
narrowing check to pass a type checker. Runtime values haven't changed.

`pin_of` now accepts a Wire node, as `edge_of` does. Any node a Wire read published,
directly or through a projection, returns the `Pin` its read kept, with no I/O and no
write authority. A non-temporal node raises `snapshot-pin-unavailable`, and anything a
read didn't publish raises `snapshot-node-required`.

Lifecycle events say why a read ran with `purpose` instead of `interface`.
`ReadStarted.purpose` is `"typed"`, `"wire"` or `"row-acquisition"` (0.1.0 said
`"rows"`), and `StreamStarted.purpose` is `"typed"` or `"wire"`. The structured log field
is renamed to `purpose` too, so update any log query or alert that filters on
`interface`.

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
