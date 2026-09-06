# Transactions adopt one prepared Model Edition at open

A running Parallax process adopts evolved models without restarting, but a
candidate that fails runtime preparation must leave the previously published
model available to serve. Parallax therefore prepares each Model Selection
before publication, and each execution retains the published selection it
adopts. Preparation, publication, and adoption have distinct owners: Parallax
constructs the selection, the application controls publication, and the
execution owns retention.

`prepare_model(model, edition=edition)` accepts a Domain Model and a Model Edition and
returns one opaque, fully prepared `ModelSelection`, or raises. Its read-only
`model` is the original Domain Model and its read-only `edition` is an opaque,
nonempty string. Editions are compared only for equality, never ordered; the
same token must identify the same model throughout a Serving Model's history.
`ModelSelection` is the prepared artifact itself, with no additional
`PreparedModel` wrapper.

Preparation completes every fallible, finite derivation determined solely by
the model before the selection can be published, including Entity layouts and
facts currently derived lazily. Its private `SelectedReadModel` carries a
shared `CatalogedModel` and optional graph construction; its private
`SelectedWriteModel` carries that same catalog, the row codec, and the write
planner. This composition belongs in the snapshot module because it already
joins those dependencies; core model formation must not import the snapshot
planner. Selections are process-local and immutable in their model, edition,
and prepared composition. Preparation guarantees structural readiness, not
physical schema readiness, valid stored data, or the success of a future query
or database operation.

The single concrete `ServingModel(initial)` owns the current selection.
`current()` returns that exact ready selection without compilation, I/O, or
application callbacks. `publish(candidate, expected=base)` replaces it
atomically only when the current selection is the exact `base` object; a stale
publication is refused with `PublicationConflictError`, which carries the
expected and the actually held selection, and leaves the current selection
unchanged. The comparison is selection identity, not edition equality or
ordering. "Serving" is the vocabulary's own word for a Database's relationship
to its model, and the holder is a separate object rather than a `Database`
verb so that holding a handle confers no authority to change the model it
serves. There is no custom Serving Model protocol, separate constant holder,
or generic updater seam, and a Database keeps no additional current-selection
cache.

The application owns source refresh, schema migration, and durable coordination
between processes. It prepares B before changing the schema and publishes B
only once the schema satisfies it; preparation failure leaves A published and
serving. Conditional publication protects this process's selection, not a
cross-process migration sequence. A new process needs an initial successfully
prepared selection before it can serve. The static
`Database.connect(adapter, model)` signature remains: it prepares once and
holds a private Serving Model with a generated edition stable for that holder's
lifetime. Separate static Database instances may have different editions even
when given the same Domain Model.

Each Parallax Transaction attempt adopts once before physical database begin
and retains that selection until completion. A joining nested transaction
inherits it; a retry reads the Serving Model's current ready selection afresh.
`Transaction.edition` is read-only. A standalone eager read adopts once, while
a standalone stream adopts on context entry and retains its selection for all
pages. Model-independent stream arguments are checked when the stream is
created; model-aware validation occurs on entry against the adopted selection.
A stream that is never entered adopts nothing.

Read, checked, row, and Wire result envelopes, and streams, expose their retained
edition through a public `.edition`. This does not introduce a page interface
or add fields to Entity mappings. A write source from another edition is
permitted when validation against the adopted model and the source's original
evidence permit the operation: edition equality alone is neither permission
nor a refresh mechanism. Delayed `InvalidDataError` remains its own type and
carries the original result's edition, even when the result is inspected after
its execution has ended.

Failure reporting belongs to the execution that adopted the selection.
`ExecutionFailure` pairs an ordinary exception escaping an owning adopted
execution with its nonoptional adopted edition, including an exception raised
by the application's transaction callback. Wrapping follows retry and
rollback resolution; joins of the same transaction do not introduce repeated
wrappers. Retry exhaustion reports the final attempt's edition. Fatal and
control-flow exceptions retain their existing behavior, and a failed rollback
retains both the triggering and rollback errors. Failures before adoption,
including preparation, startup, and lifecycle-provider opening failures, keep
their own types rather than acquiring an edition of `None`. If an
`InvalidDataError` from result A escapes transaction B, the outer
`ExecutionFailure` carries B and preserves the A-bearing error as its cause.

The database seam preserves neutral failure facts, including the violated
Physical Index Name when supplied by the database, and the execution failure
preserves the database failure in its cause chain. The failure path does not
consult the Serving Model and a unique-index violation is not automatically
retriable. The host may correlate these facts with rollout state and decide
whether replaying the whole use case is safe.

Execution lifecycle reports adoption on the Started event of its owner:
transaction attempt, standalone read, or standalone stream. Each carries the
adopted edition and descendants inherit that context; the transaction invocation
root can span attempts on A and B and therefore has no single edition. There
is no first-publication adoption event or comparison of previous and new
editions. `AttemptStarted` follows adoption and precedes physical begin, so a
begin failure is a terminal `begin_failed` attempt outcome with no callback and
no retry.

Edition Overlap is classified, not prevented. Only a Unilateral Evolution may
be applied to a live tenant, and publication asserts that the physical schema
already satisfies it, so a transaction on an earlier edition retains a valid
model-facing operation surface even where behavior or enforcement differs.
Some unilateral operations are nevertheless Overlap-Visible: nullability or
String-length widening, or a Concrete Subtype added to a shared
table-per-hierarchy family, can introduce rows that the earlier model does not
admit. An earlier-edition read reports those rows as stored data violating its
model at the result root, like other stored-data violations. The retained
edition supports correlation with rollout state and an application decision
to rerun the transaction. Processes publish independently, so a single-process
drain cannot eliminate the overlap window.

Preparing on first adoption was rejected because a structurally accepted but
unpreparable candidate would fail requests after publication. Falling back
inside Database would instead give the Serving Model and the handle competing
notions of the current edition. Publishing opaque ready selections makes
readiness a construction guarantee while keeping refresh and rollout policy
with the application. Resolving per operation was rejected because one
transaction could then mix models; rebuilding inside `current()` or a custom
holder would move fallible preparation and dependency knowledge into the
adoption path. The holder was first spelled `PublishedModelProvider`; it is
renamed `ServingModel` because "provider" implied a pluggable seam this
decision forbids.

[Reladomo prior art](../research/reladomo/31-runtime-model-replacement-and-schema-evolution.md)
uses replaceable generated-Finder portal slots without an adoption guard for
in-flight transactions. Its replacement mechanism is not adopted here.

This decision extends the existing contracts. The
[planned Python surface](../../languages/python/spec/python.md#prepared-model-publication)
records the concrete interface; implementation requires a coordinated migration
of the active core specifications, lifecycle schemas, and compatibility corpus.
This decision does not claim that those contracts or runtime behavior have
already migrated.
