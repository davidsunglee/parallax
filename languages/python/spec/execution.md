# Python execution binding

Portable execution rules belong to [Execution](../../../core/spec/m-execution.md),
[Unit of Work](../../../core/spec/m-unit-work.md),
[Execution Authority](../../../core/spec/m-execution-authority.md),
[Automatic Retry](../../../core/spec/m-auto-retry.md),
[Database Port](../../../core/spec/m-db-port.md), and
[Execution Lifecycle](../../../core/spec/m-execution-lifecycle.md).
This page owns Python composition and failure choices.

## Supported PostgreSQL

The adapter supports the PostgreSQL release range declared in its
[package configuration](../packages/parallax-postgres/pyproject.toml).
Supporting a new PostgreSQL major requires a separate compatibility decision.

## Models, roots, and scopes

`prepare_model(model, edition=...)` returns a complete immutable `ModelSelection`
or raises without exposing a partial selection. Its `model` is the original
Domain Model. Its edition is a nonempty opaque string compared only for equality;
applications must not reuse a token for a changed model within one publication
history. A `ServingModel` holds one selection. `publish(candidate, expected=...)`
atomically compares the held selection by identity and either replaces it or
raises `PublicationConflictError` with the exact `expected` and `held` values.
There is no automatic publication retry, edition ordering, or implicit DDL.
The application prepares, makes the physical schema ready, and publishes.

`connect(adapter, model, ...)` accepts a Domain Model or Serving Model and owns
one opened runtime. The Domain Model shorthand uses a static Serving Model.
`Database` is the resource root: close it explicitly or use its context manager;
closing is idempotent and invalidates derived scopes. The root exposes authority
selection and option and routing derivation, not modeled execution verbs.
`ScopedDatabase` owns those verbs and has no independent close or
authority-reselection operation.

`connect(..., read_policy=...)` and `with_routing(read_policy=...)` on both
`Database` and `ScopedDatabase` carry the read policy, spelled
`"writer_only"`, `"reader_only"`, or `"reader_preferred"` (`RoutePolicy`).
`read_policy` is keyword-only and omission resolves to the runtime's default;
`with_routing` has no omitted form. A value outside the vocabulary raises
`ValueError` before the adapter opens, and a policy the runtime's declared
routes cannot honor raises `ValueError` from `connect` or `with_routing`
without acquiring anything. `with_routing`
returns a new alias root or scope sharing the same resources; it composes in
any order with `using_principal`, `using_database_login`, and `with_options`.
A new outer `read_only` whose resolved isolation its strict policy's route
cannot begin raises `ValueError` before anything is observed or acquired; a
`"reader_only"` refusal names `with_routing(read_policy='writer_only')`.

`PostgresAdapter` and `PostgresEndpoint` are frozen configuration. An endpoint
holds where its connections go, how its login authenticates, and its retention;
the adapter holds the topology and the budgets its runtime spends. A configured
`reader` is its own endpoint, with its own credentials and retention, and must
authenticate the writer's login;
its reader route declares Read Committed and Repeatable Read for read-only
transactions, never Serializable. `reader_startup` is `"deferrable"` or
`"required"`: omitted with a reader, it defers an unreachable reader, which a
fixed `parallax.resources` warning reports; supplied without a reader, it
raises `ValueError`. `DatabaseStartupError.route` names which route failed.
`ConnectionAcquisitionError.reason` spells `m-db-port`'s acquisition reasons in
snake_case. `reader_preferred` gives the reader at most half of
`acquire_timeout`. While a reader is known to be unreachable, one
`reader_preferred` acquisition at a time tries it again, which is what re-dials
it, and the others go to the writer at once. Required `credentials=` accepts
`Password(...)`, a source with `resolve() -> Password`, or `DRIVER_MANAGED`,
never `None`. `parallax-aws` supplies
`RdsIamCredentials`; its optional `parallax.aws.postgres.rds_endpoint` composer
returns a configured endpoint with the credential source and TLS mode required
for IAM authentication, signing for its own host, which the application
composes into an adapter.

`read_plan_cache_capacity` controls per-root reuse of immutable read plans. It
must be a nonnegative exact built-in `int`; invalid values raise `ValueError`
before the adapter runtime opens. Zero disables reuse
between deliveries while preserving the normal planning path. A positive value
bounds a true least-recently-used cache by entry count. Concurrent cold requests
for the same key share one build and its success or failure; failures are not
cached, while unrelated keys can build concurrently.

Reuse is unobservable in results, statements, and binds: a read served from a
retained plan behaves as one planned for it alone. Plans retain immutable planning and
conversion data, not runtimes, connections, rows, pages, origins, or results.
The cache has the `Database` lifetime; closing the root does not promise to clear
plans while the closed root is still referenced, and eviction or release makes
otherwise unreferenced plans and retained query values collectible.

`using_principal` reads `subject` once and `database_authorization` once, captures
their values and the runtime's bound source, and does not retain the Principal.
An empty, non-string, or `db-login:`-prefixed subject and an
`InvalidAuthorizationError` from the provider become `InvalidPrincipalError`
with their cause. Application property failures and unexpected provider failures
propagate unchanged. `using_database_login()` explicitly captures the runtime's
actual authenticated login without scope-time I/O. No ambient or default
Principal exists.

`TxnOptions` is a complete immutable record. `with_options` makes a
field-wise patch; omission preserves the previous value and later patches win.
Authority selection preserves options, and option derivation preserves authority.
`connect(options=None)` and omission both select the default record, but `None`
is invalid for an individual field. Python isolation spellings are
`read_committed`, `repeatable_read`, and `serializable`. Invalid field values
raise plain `ValueError` before acquisition or observation. Defaults and other
closed vocabularies are declared by the exported record and types.
`ReadOnlyTxnOptions` is the resolved record of a read-only transaction:
`retry` and `isolation` alone, resolved and validated as `TxnOptions`
resolves and validates them.

`retry` takes a `RetryPolicy`, exported with `AdaptiveBackoff` from
`parallax.core.execution`; together their fields map one for one to the portable
Retry Policy (`m-auto-retry`). Each validates on construction and refuses with plain
`ValueError` naming the field: `max_retries` is an exact built-in `int`, so `bool`
and `int` subclasses are refused; a delay is an `int` or `float`, not `bool`, that
converts to a finite positive `float`, and is held as that `float`. A `retry` value
that is not a `RetryPolicy`, `None` included, raises `ValueError` where it is
supplied: eagerly in `with_options`, and in `transact` and `read_only` after
re-entry refusal, ahead of any join comparison.

## The database port

`parallax.core.db_port` spells the `m-db-port` behaviors for Python, and its
protocols own the signatures. `DatabaseConnection.execute` takes SQL, binds, and
the read's document cells as adjacent ordinal pairs, which an adapter folds into
one `DocumentRead` each. A bind is `object`: a structured-document bind is a
`StructuredDocument` and an array bind an `ArrayBind`, and a bind that states SQL
`NULL` is `None`, so `StructuredDocument(document=None)` spells the JSON null
document. `transaction` returns a `TransactionOutcome` rather than raising which
boundary failed. A `DatabaseRuntime` binds authority through `login_source()` or
`principal_source(authorization)`, and each `ConnectionContextSource.new_context`
is one acquisition.

## Transactions and failure boundaries

`scope.transact(fn, ...)` is callback-only. The callback receives the writable
`TxnContext` and its return value is delivered only after durable commit. Python
offers no transaction context-manager demarcation because a retry must replay
the body. `retry` is the only public retry keyword: `max_retries=` and `retries=`
raise Python's unknown-keyword `TypeError` on every entrypoint.
After the bound is exhausted the caller receives the last attempt's own failure,
inside `ExecutionFailure`, with its original chain and a note naming the attempt
count.

`scope.read_only(fn, *, retry=..., isolation=...)` is the read-only
entrypoint, callback-only on the same terms. Its callback receives a
`ReadOnlyTxnContext`: `find`, `stream`, a `wire` that is the
read-only `WireDatabaseView`, `edition`, and `options` — a
`ReadOnlyTxnOptions` — and no mutation verb. The access mode crosses the port as
`access_mode`, `"read_only"` or `"read_write"`, beside `isolation`.

Only omission inherits a transaction option. Explicit `None` is invalid.
`tx.options` is one resolved immutable record shared by all attempts and joins
and remains readable after the invocation ends. `tx.edition` identifies the
adopted selection. Static and cross-edition write eligibility follows
the adopted model and core evidence rules, not edition inequality alone.

Active transactions are thread-local. Joins must come from the same resource
root and an equal captured actor, through the active transaction's own
entrypoint. Independently derived aliases may join;
another root raises `TransactionOwnershipError(transaction-owner-mismatch)`.
Unequal actor capture raises
`TransactionAuthorityError(transaction-authority-mismatch)`. A `transact` call
while a read-only transaction is active, or a `read_only` call while a writable
one is, raises `TransactionAccessModeError(transaction-access-mode-mismatch)`. A
joining explicit option may equal the active value but cannot renegotiate it; a
difference raises `TransactionOptionConflictError`. Scope defaults alone do not
conflict.

Lifecycle re-entry and explicit option validation precede the core join refusal
order (`m-execution-authority` *Join authority*). Authority, access-mode, and option preflight refusals leave a
healthy transaction usable when caught. A joined callback failure marks the
outer transaction rollback-only before escaping; catching it cannot permit a
commit. A failure while a flush executes — a database error or an affected-row
refusal, whether the flush served a dependent read or a commit —
likewise marks the transaction rollback-only before it escapes the operation
that triggered the flush. Once rollback-only, every further read, write, or
joining callback raises `UsageError(transaction-rollback-only)` with the original
cause, and a
callback that caught the failure and returned normally still rolls back with its
result withheld. Preparation, evidence, and planning refusals raised by a write
verb leave the transaction usable when caught. Transaction context references
are not thread-safe, and execution through an escaped reference after the
invocation ends is refused.

An ordinary failure escaping an adopted outer transaction or standalone read
is `ExecutionFailure`, carrying the adopted edition and original `cause`.
Transactional operations raise their own errors inside the callback; the outer
boundary contextualizes a failure once. Entered standalone stream advances use
the stream edition, while stream-state misuse remains
`StreamStateError`. Failures rejected before model adoption remain
unstamped. Interpreter control-flow exceptions keep their
ordinary behavior.

A failed statement's `cause` is a `parallax.core.db_error.DatabaseError`. Its
`category` is a `Category`, the closed set
[Database Error Classification](../../../core/spec/m-db-error.md) owns, or
`None` when the failure is uncategorized. Its `constraint_name` is the name the
database reported for the violated constraint, or `None`. Its `violated_index`
is that name as a `PhysicalIndexName` for a `uniqueViolation`, and `None`
otherwise, a unique violation naming no constraint included. Handlers narrow
with `isinstance(failure.cause, DatabaseError)`; a handler meant for one
constraint compares `violated_index` or `constraint_name` with that
constraint's name rather than treating every failure of a category as its own.

Constructing a `DatabaseError` directly accepts `violated_index=` as a spelling
of `constraint_name=`, and raises `ValueError` when the two name different
constraints. `violated_index` reads `None`
for every category but `"uniqueViolation"` whatever the constructor received.

Failed rollback after an ordinary trigger raises `TransactionRollbackError`,
exposing both `triggering_error` and `rollback_error` and chaining the rollback
failure. Successful rollback preserves the original error. A fatal trigger
remains primary with rollback failure attached through native chaining.

Write verbs are on the `TxnContext`; their snake_case temporal parameters bind
the corresponding core operations. Inserts accept fresh constructed values;
later mutations require provenance where the core evidence rules prescribe it.
Evidence is never a caller-supplied address. The set-based writes are
`amend_where(query, *assignments)`, `replace_where(query, payload)`, and
`delete_where(query)`, taking a mutation-compatible Typed Object Query,
`Attr.set(...)` Assignments, and an instance of the queried Entity used only as
data, and `tx.wire.amend_where(target, changes, /)`,
`tx.wire.replace_where(target, data, /)`, and `tx.wire.delete_where(target, /)`,
taking that Typed query, kept as authored, or the canonical `{entity, predicate}`
selection document — never an Object Query node or its document — and a
replacement's data as a document or as a node Parallax published for the
selected Entity. A replacement payload's key addresses nothing and is never
written. A set-based write is one readless statement, so it takes no window, and
over a versioned or temporal Entity it is refused at the call with an
`InstructionRejectedError`, the `WriteInstructionError` whose `rule` is
`set-based-write-target-unsupported`, naming the keyed and target verbs that
write such an Entity (`m-batch-write`). Every verb of the family returns an `int`, the
affected-row count `m-batch-write` defines: the statement runs at the call,
after the writes the transaction buffered before it, so its database errors
raise there.

The method names the authority. `amend`, `replace`, `delete`, and `terminate`
take a source — a value a read of the writing transaction attempt published, a
joined callback's included, or the value or node an insertion of that attempt
took or answered — and state no condition and no `valid_from`: a Bitemporal one
starts at its source's finite Valid-Time pin, or where the insertion that
produced its source was authored to start, and a source read at Valid-Time
`LATEST` is refused. A value a standalone read, a read-only transaction, or an
earlier attempt published raises `WriteEvidenceError(write-evidence-unavailable)`
at the call under either concurrency preference, an amendment naming nothing
included (`m-unit-work` *Current-attempt source admission*); its caller states
the revision that value carries through a target verb instead.
`amend_if`, `replace_if`, `delete_if`, and `terminate_if` address an object
themselves and require exactly one keyword-only revision: `version` for a
versioned Entity or `tx_start` for a temporal one. Presence is counted before
any value is judged: none, both, a stated `None`, or a revision the Entity does
not take is refused, and no missing revision falls back on a source. An
unversioned Non-Temporal Entity has no revision, so every target verb
refuses it with `WriteInstructionError`; it is written through a read of the
writing transaction, whose shared lock the Locking fallback takes. The keyword
names a revision, never a value to store; the canonical instruction keeps
`ifVersion` and `ifTxStart`.

Every windowed verb — `insert`, `amend`, `amend_if`, `replace`, `replace_if`,
`terminate`, and `terminate_if`, on the `TxnContext` and on `tx.wire` — takes a
keyword-only `until`. Omitting it selects the core unbounded
verb; stating it — `None` included — selects the bounded one, whose window core
preparation judges before an empty amendment is dropped. Every verb taking
`valid_from` treats omission alone as absence: a stated `None` is refused, so a
caller forwarding optional bounds omits an unavailable one.

A Typed `amend(source)` assigns every member touched along the value's `edit`
chain; `amend(source, *assignments)` assigns exactly the given `Attr.set(...)`
assignments instead and refuses a source with any edit history, restored or
equal edits included. `amend_if(EntityClass, *assignments, key=...)`,
`delete_if(EntityClass, key=...)`, and `terminate_if(EntityClass, key=...)`
take the concrete class and the scalar primary-key value, whatever the key
Attribute is called; a mapping or tuple key is refused. Assignment references are judged
against the class's own ancestry before they are flattened, so an inherited
member applies and a foreign or duplicated one is refused. A Wire `amend`
assigns every key its change document names. Equal values are assigned either
way, and a change naming nothing writes nothing.

Each representation names a target write's object by one rule. A Wire
document names it by its key entries: `amend_if` and `replace_if` take the key
beside changes or a whole state, and `delete_if` and `terminate_if` a key-only
document. A Typed call names it with `key=`, unless its payload is an instance,
which always holds its own key, so `replace_if(instance)` takes no `key=`.

A Typed `replace(source)` and `replace_if(payload, ...)` state the value's
complete writable state. A Wire `replace(source, data)` states `data` alone;
omitting `data` states the writable state `source` published, while `{}` is a
stated, completed state. `replace_if` takes an Entity spelling with `data`, or a
published node — current or historical — alone. A Wire source write's document
may repeat the source's primary key, which must name the source's object and is
never assigned; an entity-spelled write names its key in its document.
`tx.wire.delete_if` and `tx.wire.terminate_if` take an Entity spelling and a
key-only document. `delete_if` applies to a Non-Temporal Entity and
`terminate_if` to a temporal one; each refuses the other's and names it.
`tx.wire.editable_data(source)` copies a published node's key and writable
members into fresh mutable mappings and lists, preserving Wire spellings and
absent members; it queries, completes, and authorizes nothing, and records no
edit history.

An insertion's authority (`m-unit-work` *Insertion authority*) rides its source
privately. `tx.insert` binds it to the instance it took, beside any Snapshot
state that instance already carries, and `edit` carries it to every value
derived from that instance afterwards; `tx.wire.insert` answers a node carrying
it and no Read Evidence. It is no member and no mapping key:
`model_dump`, `dict(node)`, and JSON drop it, and a pickled inserted instance or
node unpickles as plain domain data that authorizes nothing — so pickling an
inserted instance succeeds, unlike a read's node. Inserting the same instance
again once its earlier insertion was removed rebinds it; drafts derived before
keep the earlier, retired authority.
A target write addresses an existing object by key under its caller's own
revision (`m-unit-work` *Target writes*). Each returns `None`. A
Bitemporal one states `valid_from`, and `until` bounds it exactly as it bounds
`insert`; a Transaction-Time-Only one takes neither. `tx_start` is the
milestone start the caller's query returned, an aware `datetime`, never this
transaction's own instant, and describes the coverage at `valid_from` alone. A
retried callback states the same revision again. A missing or revised target
raises `parallax.core.unit_work.WritePreconditionError` — at the call under
Locking, at the flush under Optimistic — a deletion or termination included,
which never succeeds by removing nothing; it is never retried, and its
`expected` is the stated revision. An object the attempt inserted is refused
with `WriteEvidenceError(write-evidence-inserted)`.
`tx.wire` is the Wire ingress, sharing transaction state and policy. Public
write-plan and flush operations are absent. Framework-owned attributes cannot
be authored by construction, `edit`, assignments, or Wire changes.

## Observation and representation

Lifecycle protocols and providers are exported by
`parallax.core.execution_lifecycle`; the Snapshot package does not re-export
them. Providers are installed at root composition. Results and transaction
objects expose no retained lifecycle event record. Observer callbacks follow
core re-entry and failure containment rules.

An ordinary provider `open` failure is `ExecutionLifecycleProviderError` with
the original `__cause__`. Ordinary handler failures produce detached
`ExecutionLifecycleHandlerError` reports; an ordinary reporting failure writes
one sanitized correlation-only line to `sys.__stderr__`, or is dropped if that
path is unavailable. `BaseException` from handling or reporting aborts delivery
and propagates unchanged. Root-local callback re-entry raises
`ExecutionLifecycleReentryError`; other Database Roots remain usable.

`LoggingLifecycleProvider` uses an application-owned standard-library Logger,
with no queue, sink, or shutdown ownership. Both detail modes exclude SQL and
binds; default `safe` excludes error messages and stacks, while `diagnostic`
adds their bounded projections. Started and non-root Finished records use DEBUG,
successful root summaries INFO, retry-eligible rollbacks WARNING, and failed
roots or rollback failures ERROR. A disabled level pays for no event description,
but summaries count transitions regardless of log level.
Pool observation is an optional protocol on the same provider, independent of
root acceptance; its registration stays live through runtime close and is closed
exactly once afterward.

Core-authored names and serialized tokens keep their core spelling. Python-only
runtime classifications use lowercase snake_case, including lifecycle event
classifications and structured logging fields. Stable diagnostic codes use
hyphens, whether authored by core or Python. Database-native codes and messages
preserve their original spelling. Translation between Python and core tokens
is explicit at the projection boundary.

Driver failures raised by port work are translated to fresh Parallax database
errors with neutral category and preserved native SQLSTATE/message. A unique
violation's physical index name comes from the driver's structured diagnostic.
Exceptions raised by the caller's transaction body retain their identity unless
rollback itself fails; body errors do not become driver failures by type alone.
Provider-specific composition and lifecycle examples are in the
[PostgreSQL lifecycle guide](../docs/postgresql-lifecycle.md).
