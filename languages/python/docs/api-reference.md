# API reference

Every name an application imports from Parallax, by module, with the first line of
its docstring. Anything not listed here is private or internal.
[What each error asks of you](guide/08-errors.md#what-each-error-asks-of-you) says
when to handle each error.

This page is generated from the [API snapshot](../tests/api/public_api.json) and the
docstrings. After changing an exported name or its docstring, run
`uv run python tools/api_reference.py`.

## `parallax.aws`

AWS credentials for Parallax database connections.

### Classes

- `RdsIamCredentials`: Authenticates an RDS or Aurora Postgres login with an IAM token.

## `parallax.aws.postgres`

RDS IAM endpoints for Postgres; requires the `parallax-aws[postgres]` extra.

### Functions

- `rds_endpoint`: Configure a Postgres endpoint whose login authenticates with an RDS IAM token.

## `parallax.core`

Declare models, configure and observe execution, and handle errors.

### Functions

- `asc`: An ascending ordering term over a member; the same as naming the member alone.
- `attr`: Declare a member's options, such as its column, primary-key role or type details.
- `desc`: A descending ordering term over a member.
- `index`: Declare one local index over ``members``, in the order given.
- `prepare_model`: Prepare one complete immutable model selection without database I/O.
- `rel`: Declare a relationship: its cardinality and join, or the relationship it reverses.

### Classes

- `AbstractRoot`: Inheritance role for the abstract root of an Entity family.
- `AbstractSubtype`: Inheritance role for an abstract Entity between a family's root and its concrete subtypes.
- `AdaptiveBackoff`: The wait before each retry: a base delay doubled per attempt, up to a maximum, in seconds.
- `AllPredicate`: A predicate that matches every row of an Entity, written `Entity.all`.
- `ApplicationAssigned`: Key generation where the application supplies each primary-key value.
- `Attr`: The annotation that declares a scalar or Value Object member on an Entity class.
- `BindingIssue`: One binding problem, located by its path into the binding document.
- `Bitemporal`: Base class for an Entity with both Valid Time and Transaction Time history.
- `Boolean`: Column type for true or false values.
- `Bytes`: Column type for binary data.
- `Columns`: Storage layout that gives each attribute its own column; the default.
- `ConcreteSubtype`: Inheritance role for a concrete Entity in a family, with the tag value that marks its rows.
- `CredentialSource`: Produces the credential for one physical connection, each time one is created.
- `Date`: Column type for calendar dates without a time zone.
- `Document`: Storage layout that keeps document members in one shared JSON column.
- `DomainModel`: A complete, sealed model of Entities, built from classes or a descriptor.
- `DriverManaged`: Credential type for logins the database driver handles without a Parallax secret.
- `Edge`: Where a temporal node starts: its from-instant on each axis.
- `EditViolation`: One refused assignment, located in the model's own vocabulary.
- `Entity`: Base class for every Entity class.
- `ExecutionLifecycleHandler`: Receives the lifecycle events of one root execution.
- `ExecutionLifecycleHandlerError`: A report a Provider receives when one of its Handlers raised; it is never raised itself.
- `ExecutionLifecycleProvider`: Opens a Handler for each root execution, so an application can observe Parallax's work.
- `FanoutLifecycleProvider`: A Provider that forwards lifecycle events to several Providers.
- `Float32`: Column type for 32-bit floating-point numbers.
- `Float64`: Column type for 64-bit floating-point numbers.
- `IncludePath`: A relationship path to load with `.include(...)`, such as `Order.items`.
- `Int32`: Column type for 32-bit signed integers.
- `Int64`: Column type for 64-bit signed integers.
- `InvalidData`: One result root that stored data contradicted, with the issues found.
- `Json`: Column type for JSON values, except a bare top-level null.
- `LoggingLifecycleProvider`: A Provider that logs each root execution through a Logger you configure.
- `MetamodelIssue`: One fatal model defect, located in the model's own vocabulary.
- `ModelSelection`: A Domain Model prepared under a named edition, ready for a `ServingModel` to serve.
- `Numeric`: Column type for exact fixed-point numbers.
- `ObjectQuery`: An immutable, side-effect-free query over one target Entity.
- `Password`: A login password; its secret is kept out of every repr.
- `PhysicalIndexName`: One physical Index name as a database holds it.
- `Pin`: Where a temporal read stood: its as-of instant on each pinned axis.
- `PoolAvailable`: A pool metrics sample taken while the pool was available.
- `PoolDetached`: A pool metrics sample reported after the pool's runtime closed.
- `PoolMetricsObserver`: Implement to observe the connection pools a database runtime keeps.
- `PoolMetricsSource`: A stable, read-only handle on the bookkeeping of one pool a runtime keeps.
- `PoolObservation`: One active pool observation; `close()` ends it.
- `PoolUnavailable`: A pool metrics sample reported when this reading could not be taken.
- `Predicate`: A filter over an Entity; combine predicates with `&`, `|` and `~`.
- `Principal`: Application-supplied subject and database authorization.
- `ReadOnlyTxnOptions`: The resolved options a read-only invocation runs under.
- `Rel`: The annotation that declares a relationship on an Entity class.
- `RetryPolicy`: How a transaction retries after a transient failure.
- `RootExecution`: One top-level database operation, as a lifecycle Provider sees it.
- `Sequence`: Key generation that allocates from a named database sequence in batches.
- `ServingModel`: Holds the model selection a database serves, and publishes replacements.
- `SortKey`: One ordering term in a query's sort.
- `StoredDataIssue`: One way stored data contradicts the model; `code` says which.
- `String`: Column type for Unicode text.
- `TablePerHierarchy`: Inheritance strategy that stores a whole family in one table with a tag column.
- `TemporalBound`: The open upper bound of a temporal interval, distinct from every instant and from `None`.
- `Time`: Column type for times of day without a time zone.
- `Timestamp`: Column type for UTC instants.
- `TxTemporal`: Base class for an Entity with Transaction Time history only.
- `TxnOptions`: Transaction options: a database's defaults, and the options each transaction runs under.
- `Uuid`: Column type for UUIDs; letter case carries no meaning.
- `ValueObject`: Base class for every Value Object class.

### Errors

- `BindingError`: A database binding was refused; `issues` lists every problem.
- `ConflictError`: The work collided with stored state another writer changed.
- `ConnectionAcquisitionError`: No database connection could be acquired; `reason` says why.
- `CredentialResolutionError`: A source could not produce a credential, so no connection was authenticated.
- `DatabaseError`: The database refused a statement; `category` says what kind of failure it was.
- `DatabaseStartupError`: `connect` could not make the database ready, so no `Database` was returned.
- `EditError`: An edit broke assignment rules; `violations` lists every one.
- `InternalError`: A Parallax invariant failed; no change to the calling code avoids it.
- `InvalidDataError`: Stored data contradicts the model, so Parallax cannot read it as valid or revise it.
- `InvalidValueError`: A value you supplied does not fit its member's type, value space or requiredness.
- `MetamodelValidationError`: A model is invalid; `issues` lists every problem.
- `NoResultFound`: A single-result accessor found no result.
- `ParallaxError`: The root of every exception Parallax raises.
- `PublicationConflictError`: `publish` found a different model selection serving than the one it expected.
- `TooManyResultsFound`: A single-result accessor found more than one result.
- `TransactionRollbackError`: The transaction could not be undone after something ended it.
- `UnloadedRelationshipError`: A relationship the read did not load was accessed; add it with `.include(...)`.
- `UnsupportedError`: A reasonable request this version of Parallax, or the selected Dialect, cannot serve yet.
- `UsageError`: The request contradicts Parallax's rules; fix the code, declaration or input.
- `WritePreconditionError`: A target write's expected starting state no longer holds.

### Constants and types

- `Category`: Which kind of database failure a `DatabaseError` reports.
- `DRIVER_MANAGED`: Credential setting that leaves login entirely to the database driver.
- `LATEST`: Read the current state on a temporal axis rather than as of a fixed instant.
- `LIFECYCLE_PROVIDER_FAILED`: Code for an operation refused because a lifecycle Provider failed to open.
- `LIFECYCLE_REENTERED`: Code for an operation refused because a Handler called back into the Handle it observes.
- `MANY_TO_ONE`: Relationship cardinality: many source rows refer to one target row.
- `MAX`: Key generation that allocates from the largest stored key.
- `MISSING_STORED_VALUE`: Marks a member absent from stored data, as distinct from a stored null.
- `ONE_TO_MANY`: Relationship cardinality: one source row has many target rows.
- `ONE_TO_ONE`: Relationship cardinality: one source row has at most one target row.
- `POSTGRES`: The PostgreSQL Dialect.
- `PRINCIPAL_INVALID`: Code for a Principal whose subject or authorization the database runtime cannot accept.
- `PoolSample`: One pool metrics sample: available, unavailable or detached.
- `QUERY_TARGET_NOT_IN_MODEL`: Code for a query whose target Entity the connected model does not declare.
- `READ_ONLY`: Persistence mode for an Entity whose rows another system writes.
- `READ_WRITE`: Persistence mode for an Entity the application reads and writes; the default.
- `TABLE_PER_CONCRETE_SUBTYPE`: Inheritance strategy that gives each concrete subtype its own table.
- `TX_TIME`: The Transaction Time dimension, for temporal query arguments.
- `VALID_TIME`: The Valid Time dimension, for temporal query arguments.

## `parallax.core.execution_lifecycle`

The lifecycle events an `ExecutionLifecycleHandler` receives.

### Classes

- `AcquisitionFailed`: Connection acquisition failed; `reason` says why.
- `AcquisitionFinished`: The acquisition reached its terminal outcome.
- `AcquisitionStarted`: An activity is asking for a database connection.
- `AttemptBeginFailed`: A transaction attempt could not begin, so its callback never ran.
- `AttemptCommitted`: The attempt committed, so the invocation it belongs to is over.
- `AttemptFailure`: What ended one physical attempt.
- `AttemptRollbackFailed`: The rollback the attempt's failure required did not complete.
- `AttemptRolledBack`: Something ended the attempt and the rollback completed.
- `CausedFailure`: A failure attributed to a child activity that already finished.
- `ConnectionAcquired`: Exclusive use of a connection was granted to the activity that asked.
- `DatabaseCallFailed`: A statement failed.
- `DatabaseCallFinished`: A statement finished, however it finished.
- `DatabaseCallNotExecuted`: A statement confirmed never to have run.
- `DatabaseCallStarted`: A statement is about to be sent to the database.
- `DatabaseCallUnconfirmed`: A statement whose execution cannot be confirmed, because its transport was interrupted.
- `DatabaseFailureDiagnostic`: Details of a failed statement, including the database's own error facts.
- `DatabaseReadCompleted`: A query finished; carries the number of rows the database returned.
- `DatabaseWriteCompleted`: A write statement finished; carries the affected-row count the driver reported.
- `DatabaseWriteRowsCompleted`: A row-returning write statement finished; carries the number of rows returned.
- `DirectFailure`: A failure attributed to the activity itself rather than to a child.
- `FlushCompleted`: A flush sent all its pending writes to the database.
- `FlushFailed`: A flush failed before sending all its pending writes.
- `FlushFinished`: The Flush reached its terminal outcome.
- `FlushStarted`: Pending writes are being flushed to the database.
- `JoinedInvocation`: A transaction call that joined a transaction already running on this thread.
- `JoinedInvocationRaised`: The nested callback raised, which dooms the transaction it joined.
- `JoinedInvocationReturned`: The nested callback returned.
- `OuterInvocation`: The transaction call that opened the transaction, and so the root activity.
- `OuterInvocationCommitted`: The outer transaction committed and returned the callback's value.
- `OuterInvocationFailed`: The outer transaction did not commit.
- `ReadCompleted`: A read returned its result.
- `ReadFailed`: A read failed before returning a result.
- `ReadFinished`: The Read reached its terminal outcome.
- `ReadStarted`: A Read opened over ``target`` for ``purpose``.
- `ReleaseFinished`: The connection was let go, and ``cleanup_result`` says what that established.
- `ReleaseStarted`: The connection this activity held is being given back.
- `StreamBatchCompleted`: A stream page is ready to yield.
- `StreamBatchFailed`: A stream page failed before it was ready.
- `StreamBatchFinished`: The page reached its terminal outcome.
- `StreamBatchStarted`: One requested page opened.
- `StreamClosedEarly`: The caller stopped a stream before it was exhausted.
- `StreamExhausted`: A stream yielded its last page.
- `StreamFailed`: Parallax's own work ended a stream with an error.
- `StreamFinished`: The stream reached its terminal outcome.
- `StreamStarted`: A stream over ``target`` opened and is about to be iterated.
- `TransactionAttemptFinished`: The attempt reached its terminal outcome.
- `TransactionAttemptStarted`: A transaction attempt started.
- `TransactionInvocationFinished`: The invocation reached its terminal outcome.
- `TransactionInvocationStarted`: A `transact` or `read_only` call started.

### Constants and types

- `ExecutionEvent`: Any lifecycle event a Handler receives.

## `parallax.core.introspection`

Read-only metadata returned by `DomainModel.entity` and `DomainModel.entities`.

### Classes

- `AsOfAxisMetadata`: One temporal dimension over a half-open ``[start, end)`` Attribute pair.
- `AttributeIdentity`: One Attribute of one Entity.
- `AttributeMetadata`: Resolved metadata for one scalar Attribute.
- `Column`: A member's physical column.
- `EntityIdentity`: An Entity's canonical model-wide identity.
- `EntityMetadata`: One Entity's resolved, read-only metadata within one Domain Model.
- `EntityProfile`: One scope of an Entity's resolved metadata: what it declares, or what is in force on it.
- `IndexIdentity`: One Index of one Entity.
- `IndexMetadata`: One local Index over an ordered Attribute Identity sequence.
- `Multiplicity`: One or many: the multiplicity of a relationship side or Value Object.
- `NestedValueObjectMetadata`: Resolved metadata for one nested Value Object occurrence.
- `NotPrimaryKey`: The Attribute is not part of its Entity's primary key.
- `NullPlacement`: Where NULLs sort on one ordering key, independent of its Sort Direction.
- `PrimaryKey`: The Attribute is the Entity's primary key, with its generation.
- `RelationshipIdentity`: One Relationship, named by its source Entity.
- `RelationshipJoin`: One source-to-target Attribute equality between two resolved positions.
- `RelationshipMetadata`: Resolved metadata for one navigable relationship direction.
- `RelationshipOrder`: One resolved ordering term over a target-local Attribute.
- `SortDirection`: Ascending or descending, for relationship ordering and query sorts.
- `Table`: An Entity's physical table.
- `TemporalDimension`: The temporal axes: Valid Time and Transaction Time.
- `ValueObjectAttributeIdentity`: One scalar Attribute of one Value Object occurrence.
- `ValueObjectAttributeMetadata`: Resolved metadata for one scalar Attribute inside a Value Object.
- `ValueObjectIdentity`: One Value Object occurrence, addressed by its containment path.
- `ValueObjectMetadata`: Resolved metadata for one top-level Value Object occurrence.

## `parallax.descriptor`

Build Domain Models from JSON or YAML descriptors, and export them.

### Functions

- `domain_model_from_document`: Build a Domain Model from an already-parsed descriptor document.
- `domain_model_from_json`: Build a Domain Model from JSON descriptor text.
- `domain_model_from_yaml`: Build a Domain Model from YAML descriptor text.
- `export_document`: Export a Domain Model as a canonical descriptor document.
- `export_json`: Export a Domain Model as canonical JSON descriptor text.
- `export_yaml`: Export a Domain Model as canonical YAML descriptor text.
- `validate_inheritance_families`: Check a descriptor document's inheritance families before building a model.

### Classes

- `DescriptorViolation`: One failure of a schema-phase keyword or a value-phase rule.

### Errors

- `DescriptorError`: A descriptor document failed validation; `violations` lists every problem.

## `parallax.evolution`

Compare two Domain Models and produce the schema change between them.

### Functions

- `evolve`: Describe every difference between two Domain Models.
- `schema_delta`: Render a `UnilateralEvolution` as SQL statements for a Dialect.

### Classes

- `Absent`: The type of `ABSENT`, the empty earlier model for fresh provisioning.
- `CoordinatedEvolution`: A model change that needs code, data or rollout coordination before it is applied.
- `CoordinationReason`: Why an operation cannot be applied without coordination.
- `CoordinationRequirement`: An operation that needs coordination, with its reasons.
- `CreatedIndex`: An index a schema change creates, so a later violation can be traced to it.
- `PhysicalLocation`: The table and member, or database extension, a schema operation acts on.
- `SchemaDelta`: The ordered dialect statements carrying a database to the later model.
- `UnilateralEvolution`: A model change a live database can apply directly with `schema_delta`.
- `UnsupportedSchemaOperation`: An operation the Dialect cannot express as SQL.

### Errors

- `UnsupportedSchemaEvolutionError`: `schema_delta` cannot render some operations for this Dialect; `operations` lists them.

### Constants and types

- `ABSENT`: Pass as `evolve`'s earlier model to provision a database from nothing.
- `Evolution`: The result of `evolve`: a `UnilateralEvolution` or a `CoordinatedEvolution`.

## `parallax.evolution.operations`

The operations and behavioral impacts an evolution reports.

### Classes

- `AsOfAxisAdded`: An As-Of Axis present only in the later endpoint.
- `AsOfAxisRemoved`: An As-Of Axis present only in the earlier endpoint.
- `AttributeAdded`: A scalar Attribute present only in the later endpoint.
- `AttributeAltered`: A surviving scalar Attribute whose accepted facts differ.
- `AttributeRemoved`: A scalar Attribute present only in the earlier endpoint.
- `AttributeWriteCapability`: What caller input one Attribute admits, widest input last.
- `CardinalityChanged`: The declared cardinality of a surviving defining Relationship.
- `ComponentsChanged`: The ordered components of a surviving authored Index.
- `ConcreteSubtypeAdded`: A concrete subtype present only in the later endpoint.
- `ConcreteSubtypeRemoved`: A concrete subtype present only in the earlier endpoint.
- `ConcurrencyControlChanged`: How optimistic concurrency guards a surviving Entity's writes changed.
- `DeclarationCollection`: The local collections whose relative order one operation can describe.
- `DeclarationFormChanged`: A surviving Relationship's declaration form changed.
- `DeclarationOrderChanged`: One local collection whose surviving declarations changed relative order.
- `DeletePropagation`: The effective dependency policy of one Relationship.
- `DeletePropagationChanged`: One surviving Relationship whose effective dependency policy differs.
- `DependencyChanged`: Whether a surviving defining Relationship declares its target dependent.
- `EntityAdded`: A whole Entity present only in the later endpoint, members suppressed.
- `EntityAltered`: A surviving Entity whose own accepted facts differ.
- `EntityRemoved`: A whole Entity present only in the earlier endpoint, members suppressed.
- `EntitySelectionFacts`: The predicate-free selection rule of one Entity position.
- `EntityWriteShape`: The effective temporal shape of an enabled Entity write surface.
- `IndexAdded`: An authored secondary Index present only in the later endpoint.
- `IndexAltered`: A surviving authored secondary Index whose definition differs.
- `IndexRemoved`: An authored secondary Index present only in the earlier endpoint.
- `InheritanceChanged`: The complete Inheritance Metadata of a surviving Entity.
- `JoinChanged`: The accepted join of a surviving defining Relationship.
- `LockingFallback`: Reads take shared locks and writes carry no gate.
- `MaximumLengthChanged`: The declared String maximum length of a surviving Attribute.
- `MultiplicityChanged`: The declared multiplicity of a surviving scalar member or Value Object occurrence.
- `NullabilityChanged`: The declared nullability of a surviving value position or occurrence.
- `OccurrenceAdmissibility`: The accepted value domain of one Value Object occurrence position.
- `OptimisticLockingChanged`: Whether a surviving Attribute carries the explicit optimistic version.
- `OrderingChanged`: The declared ordering terms of a surviving Relationship.
- `PersistenceChanged`: The accepted Persistence Mode of a surviving Entity.
- `PrimaryKeyChanged`: A surviving Attribute's primary-key membership or key generation changed.
- `QueryResultMembershipChanged`: One surviving query position whose predicate-free selection rule differs.
- `QueryResultOrderingChanged`: One surviving Relationship whose normalized ordering rule differs.
- `ReadOnlyChanged`: Whether a surviving Attribute refuses caller update input.
- `RelationshipAdded`: A Relationship declaration present only in the later endpoint.
- `RelationshipAltered`: A surviving Relationship declaration whose accepted facts differ.
- `RelationshipRemoved`: A Relationship declaration present only in the earlier endpoint.
- `RelationshipSelectionFacts`: The predicate-free selection rule of one Relationship position.
- `ReverseOfChanged`: The peer a surviving reverse Relationship names.
- `ScalarAdmissibility`: The accepted value domain of one scalar position.
- `StorageChanged`: The accepted Storage Location of a surviving Attribute or top-level Value Object occurrence.
- `StorageContainerChanged`: The accepted Storage Container of a surviving Entity.
- `StorageLayoutChanged`: The accepted Storage Layout of a surviving Entity.
- `TemporalAxisFacts`: One axis of a selection's effective Temporal Shape.
- `TransactionTimeGated`: Writes gate on the Transaction-Time start Attribute.
- `TypeChanged`: The accepted Neutral Type of a surviving scalar value position.
- `UniqueTuple`: One secondary uniqueness rule, as an unordered set of Attributes.
- `UniquenessChanged`: Whether a surviving authored Index enforces uniqueness.
- `UniquenessEnforcementChanged`: The secondary uniqueness rules a surviving Entity enforces changed.
- `ValueAdmissibilityChanged`: One surviving value-bearing path whose accepted domain differs.
- `ValueObjectAttributeAdded`: A Value Object scalar leaf present only in the later endpoint.
- `ValueObjectAttributeAltered`: A surviving Value Object scalar leaf whose accepted facts differ.
- `ValueObjectAttributeRemoved`: A Value Object scalar leaf present only in the earlier endpoint.
- `ValueObjectOccurrenceAdded`: A top-level or nested occurrence present only in the later endpoint.
- `ValueObjectOccurrenceAltered`: A surviving occurrence whose accepted facts differ.
- `ValueObjectOccurrenceRemoved`: A top-level or nested occurrence present only in the earlier endpoint.
- `VersionGated`: Writes gate on an explicit version Attribute.
- `WriteCapabilityChanged`: One surviving Entity or Attribute whose effective write surface differs.
- `WritesDisabled`: The Entity admits no persistence operation.
- `WritesEnabled`: The Entity admits persistence operations of one temporal write shape.

### Constants and types

- `BehavioralImpact`: Any behavioral impact an evolution reports.
- `EvolutionOperation`: Any operation an evolution reports.

## `parallax.postgres`

Connect Parallax to PostgreSQL.

### Functions

- `isolation_spelling`: Postgres' name for ``level``, as SQL and `transaction_isolation` spell it.

### Classes

- `OnDemandOptions`: Keep no connection between operations.
- `PoolOptions`: Keep connections between operations, within a bounded capacity.
- `PostgresAdapter`: How to reach a Postgres deployment, and the budgets its runtime spends.
- `PostgresBinding`: Where one deployment places a model's tables and sequences in PostgreSQL.
- `PostgresEndpoint`: Where one route connects, how it logs in, and how it keeps connections.
- `PostgresLocation`: A PostgreSQL schema within the database the adapter's endpoint selects.
- `PostgresRole`: A non-empty PostgreSQL role name bound to principal execution.
- `PostgresSequence`: Overrides one logical allocator's schema, sequence name, or both.
- `PostgresTable`: Overrides one mapping owner's schema, table name, or both.

## `parallax.snapshot`

Connect to a database, run transactions, and read results.

### Functions

- `connect`: Open a `Database` over an adapter and a model; the same as `Database.connect`.
- `edge_of`: Where a temporal node starts, as an `Edge`.
- `is_view_loaded`: Whether the read that produced a node loaded every relationship on a path.
- `pin_of`: Where the read that published a node stood, as a `Pin`.
- `view`: The value ``path`` reaches from ``node``, using only loaded state.

### Classes

- `CheckedSnapshot`: A `Snapshot` whose roots are `T | InvalidData[T]`, so reads continue past bad rows.
- `Database`: A connected database; close it, or use it as a context manager.
- `ReadOnlyTxnContext`: The read-only transaction context handed to a ``db.read_only`` callback.
- `ScopedDatabase`: A database view bound to a principal's authority; it holds no connection.
- `Snapshot`: The result of a `find`: immutable result roots and the ways to read them.
- `SnapshotStream`: A single-pass stream of results; use it inside a `with` block.
- `TxnContext`: The writable transaction context handed to a ``db.transact`` callback.
- `WireDatabaseView`: The Wire read interface: `db.wire`, and `rtx.wire` in a read-only transaction.
- `WireEntity`: A frozen Entity node returned by a Wire read.
- `WireTransactionView`: The Wire read and write interface inside a transaction: `tx.wire`.

### Constants and types

- `SharingScope`: How far a read may share published nodes: within one result root, or across the roots of one Page.
- `WireChanges`: A Wire write's assignments: declared member names mapped to Wire values.
- `WirePredicateTarget`: The target of a Wire predicate write: an Entity and a predicate.
- `WireQuery`: What a Wire read accepts: a canonical query mapping or node, or a Typed query.
- `WireValue`: A JSON-shaped value read from or written through the Wire interface.
