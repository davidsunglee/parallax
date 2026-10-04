# Python execution binding

Portable execution rules belong to [Unit of Work](../../../core/spec/m-unit-work.md),
[Execution Authority](../../../core/spec/m-execution-authority.md),
[Automatic Retry](../../../core/spec/m-auto-retry.md),
[Database Port](../../../core/spec/m-db-port.md), and
[Execution Lifecycle](../../../core/spec/m-execution-lifecycle.md).
This page owns Python composition and failure choices.

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
selection and option derivation, not modeled execution verbs. `ScopedDatabase`
owns those verbs and has no independent close or authority-reselection operation.

`PostgresAdapter` is frozen configuration: constructing one opens no connection,
pool, or thread. Each `connect` opens an independent runtime; closing one root
does not close another made from the same configuration. A connection string
cannot contain a password. Required `credentials=` accepts `Password(...)`,
a source with `resolve() -> Password`, or `DRIVER_MANAGED`, never `None`.
Credential sources resolve when establishing connections, allowing credentials
to expire before the pool does. `parallax-aws` supplies `RdsIamCredentials`;
its optional `parallax.aws.postgres.rds_postgres` composer returns a configured
adapter with the credential source and TLS mode required for IAM authentication.

`read_plan_cache_capacity` controls per-root reuse of immutable read plans. It
must be a nonnegative exact built-in `int`; invalid values raise `ValueError`
before the adapter runtime opens. The default is `16`, and zero disables reuse
between deliveries while preserving the normal planning path. A positive value
bounds a true least-recently-used cache by entry count. Concurrent cold requests
for the same key share one build and its success or failure; failures are not
cached, while unrelated keys can build concurrently.

Cache identity includes the exact model edition, cataloged model and dialect,
authored query structure and ordinary predicate values, result form, and
concurrency preference. Exact container and scalar types remain distinct.
The first stream page and each continuation-coordinate NULL pattern use distinct
entries; the coordinate values and page limits are execution values rendered
into their cached template, not cache identity. Plans retain immutable planning and
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

`DatabaseOptions` is a complete immutable record. `with_options` makes a
field-wise patch; omission preserves the previous value and later patches win.
Authority selection preserves options, and option derivation preserves authority.
`connect(options=None)` and omission both select the default record, but `None`
is invalid for an individual field. `max_retries` must be a nonnegative exact
built-in integer, not `bool`; `retry_optimistic_conflicts` must be a boolean.
Python isolation spellings are `read_committed`, `repeatable_read`, and
`serializable`. Invalid field values raise plain `ValueError` before acquisition
or observation. Defaults and other closed vocabularies are declared by the
exported record and types.

## Transactions and failure boundaries

`scope.transact(fn, ...)` is callback-only. The callback receives the Transaction
and its return value is delivered only after durable commit. Python offers no
transaction context-manager demarcation because a retry must replay the body.
The public retry bound is `max_retries`; no `retries` alias exists.

Only omission inherits a transaction option. An outer call inherits the scope's
effective record; a joining call inherits the active transaction's resolved
record. Explicit `None` is invalid. `tx.options` is one resolved immutable record
shared by all attempts and joins and remains readable after the invocation ends.
Every attempt adopts the Serving Model before opening its boundary; `tx.edition`
identifies that selection. Static and cross-edition write eligibility follows
the adopted model and core evidence rules, not edition inequality alone.

Active transactions are thread-local. Joins must come from the same resource
root and an equal captured actor. Independently derived aliases may join;
another root raises `TransactionOwnershipError(transaction-owner-mismatch)`.
Unequal actor capture raises
`TransactionAuthorityError(transaction-authority-mismatch)`. A joining explicit
option may equal the active value but cannot renegotiate it; a difference raises
`TransactionOptionConflictError`. Scope defaults alone do not conflict.

Join refusal order is lifecycle re-entry, explicit option validation, bare
Unit-of-Work detection, root ownership, rollback-only state, actor equality,
then explicit option equality. Authority and option preflight refusals leave a
healthy transaction usable when caught. A joined callback failure marks the
outer transaction rollback-only before escaping; catching it cannot permit a
commit. A failure while a flush executes — a database error or an affected-row
`WriteEffectError`, whether the flush served a dependent read or a commit —
likewise marks the transaction rollback-only before it escapes the operation
that triggered the flush. Once rollback-only, every further read, write, or
joining callback raises `RollbackOnlyError` with the original cause, and a
callback that caught the failure and returned normally still rolls back with its
result withheld. Preparation, evidence, and planning refusals raised by a write
verb leave the transaction usable when caught. Transaction references are not thread-safe and execution through an
escaped reference after the invocation ends is refused.

An ordinary failure escaping an adopted outer transaction or standalone read
is `ExecutionFailure`, carrying the adopted edition and original `cause`.
Transactional operations raise their own errors inside the callback; the outer
boundary contextualizes a failure once. Entered standalone stream advances use
the stream edition, while stream-state misuse remains
`SnapshotStreamStateError`. Failures rejected before model adoption remain
unstamped. Interpreter control-flow exceptions keep their
ordinary behavior.

Failed rollback after an ordinary trigger raises `TransactionRollbackError`,
exposing both `triggering_error` and `rollback_error` and chaining the rollback
failure. Successful rollback preserves the original error. A fatal trigger
remains primary with rollback failure attached through native chaining.

Write verbs are on the Transaction; their snake_case temporal parameters bind
the corresponding core operations. Inserts accept fresh constructed values;
later mutations require provenance where the core evidence rules prescribe it.
Evidence is never a caller-supplied address. Set-based writes take an Object
Query; update-bearing verbs also take Assignments.

Each operation is one method: `insert`, `update`, `terminate`, `update_where`,
and `terminate_where`, on the Transaction and on `tx.wire`, take a keyword-only
`until`. Omitting it selects the core unbounded verb; stating it — `None`
included — selects the bounded one, whose window core preparation judges before
an empty update is dropped, so `until=None` and an `until` on a target without
Valid Time are refused rather than read as omission. Source-backed `update` and
`terminate` take no start: a Bitemporal one starts at its source's finite
Valid-Time pin, or where the insertion that produced its source was authored to
start, and a source read at Valid-Time `LATEST` is refused. A Typed `update`
assigns every member touched along the value's `edit` chain and a Wire `update`
every key its change document names, equal values included; a change touching
nothing writes nothing.

An insertion's authority (`m-unit-work` *Insertion authority*) rides its source
privately. `tx.insert` binds it to the instance it took, beside any Snapshot
state that instance already carries, and `edit` carries it to every value
derived from that instance afterwards; `tx.wire.insert` answers a node carrying
it in a slot of its own and no Read Origin. It is no member and no mapping key:
`model_dump`, `dict(node)`, and JSON drop it, and a pickled inserted instance or
node unpickles as plain domain data that authorizes nothing — so pickling an
inserted instance succeeds, unlike a read's node. Inserting the same instance
again once its earlier insertion was removed rebinds it; drafts derived before
keep the earlier, retired authority.
A target write addresses an existing object by key under its caller's own
revision (`m-unit-work` *Caller-addressed writes*): `tx.replace(instance, ...)`
and `tx.wire.replace(entity_name, data, ...)` state its complete writable state,
and `tx.wire.update(entity_name, changes, ...)` — the overload taking an Entity
spelling rather than a published node — patches the members `changes` names.
There is no Typed patch: a Typed value either came from a read, whose edit is an
observed update, or states the whole object. The revision is a keyword-only
argument, never a member: `if_version` for a versioned Entity, `if_tx_start` for a
temporal one, neither for an unversioned one; `None` means it is not stated. The
observed `tx.wire.update` overload takes neither, nor `valid_from`. Each target
verb returns `None`. A Bitemporal target states `valid_from`, and the keyword
`until` bounds it exactly as it bounds `insert`; a Transaction-Time-Only target
takes neither. `if_tx_start` is the milestone start the caller's query
returned, an aware `datetime`, never this transaction's own instant. A failed
precondition raises `parallax.core.unit_work.WritePreconditionError` — at the
call under Locking, at the flush under Optimistic — and is never retried; its
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
roots or rollback failures ERROR. The provider checks `isEnabledFor` before
describing an event, but summaries count transitions regardless of log level.
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
