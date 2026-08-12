# Principal is required at every database operation boundary

Every handle-level read and outermost unit of work requires a caller-supplied Principal before its query or transaction body; Parallax obtains and validates the Principal's nonempty Subject Identity once at that boundary, before opening a connection, obtaining a Transaction Instant, executing a query, or invoking a transaction body. This capture surrounds the complete retry loop rather than each attempt. A non-string or empty result fails with the language implementation's stable invalid-principal error, while an exception raised by application code inside the Principal propagates unchanged and no database interaction begins.

There is no compatibility overload, implicit system identity, ambient
thread-local fallback, or default Principal. Production callers and tests pass
one explicitly at every public boundary; tests may reuse a deterministic test
implementation but do not bypass the argument. An unaudited model has the same
requirement because Principal context belongs to database execution and future
entitlements, not only audit stamping.

The boundary is the public modeled domain-data surface, not the abstract
database port as a whole. Schema provisioning and migration, descriptor and
model formation, connection health checks, adapter startup and shutdown, and
conformance fixture loading do not require a Principal because they do not read
or mutate domain rows through a Parallax Entity operation.

The operation context retains both the opaque application Principal and its captured Subject Identity for the operation's lifetime. Audit Provenance consumes only the string. The Principal is neither copied, serialized, persisted, nor otherwise inspected by this module, but retaining it lets a future entitlement module define and consume a richer provider-specific protocol without reconstructing authorization claims from stored audit text. Joined operations and retries reuse the same object and string; snapshotting mutable claims is deliberately left to the future entitlement contract.

Operations invoked on the Parallax Transaction inherit the captured Subject Identity without accepting or reevaluating a Principal. A nested call through the joinable database demarcation method is itself an explicit boundary: it evaluates its required Principal once, compares the result verbatim with the root transaction's captured Subject Identity, and raises the language implementation's stable principal-mismatch error before invoking the inner body when they differ. A matching joined boundary receives the same Parallax Transaction. If its Principal is a different object with the same Subject Identity, that object proves identity continuity and is then discarded; the root boundary's retained rich Principal remains authoritative for the whole transaction. Automatic retries retain the outer boundary's originally captured object and identity and do not reevaluate either. The foundational `m-principal` module owns this propagation contract so Audit Provenance and future authorization modules can depend on it without coupling Parallax to ambient authentication state; `m-audit-provenance` remains the separate consumer that stamps audited writes.

When a joining boundary has multiple invalid conditions, validation is deterministic. Exact originating-Database ownership is checked first and a foreign transaction raises `TransactionOwnershipError`. An already rollback-only transaction is checked second and fails without invoking the joining Principal. Principal resolution and validation then run, followed by verbatim Subject Identity comparison and `PrincipalMismatchError`, conflicting explicit transaction options, and only then the inner body.

Language-neutral compatibility cases carry only the already-resolved Subject
Identity, at the location representing its executable database boundary. A
single-boundary read, conflict, or boundary case uses `when.subjectIdentity`.
Each `writeSequence` entry carries one `subjectIdentity` because each entry is
already one unit of work; every row in a multi-row entry shares it. Scenario
read and write steps carry `subjectIdentity`, and steps sharing one `uow` label
MUST repeat the same value because they execute under one root Principal
context. In-memory lifecycle actions such as mutation, cached access,
`detachCopy`, and equivalent steps carry no identity and inherit their owning
operation context. Concurrency cases assign identity to the held A and B
participants rather than repeating it on every round step. Automatic retry
attempts inherit the outer boundary's identity rather than declaring an
attempt-local value. A nested boundary step may repeat or vary the root value
only to prove a matching or mismatching join. The corpus never serializes an
application Principal. Each language's API Conformance Suite supplies
provider-shaped Principal implementations and proves resolution count,
invalid-result, ownership, mismatch, and application-exception behavior around
the same Subject Identity cases.

A lazy read boundary captures and validates its Principal context when the read API creates the query-backed view, not when later access first resolves it. The view retains the opaque Principal and captured Subject Identity until resolution or scope end, and first access never reevaluates identity. Existing lifecycle errors still govern access after the owning scope closes.

Authored Object Queries, predicates, includes, canonical serialization, and query equality remain Principal-free. A future entitlement module receives the immutable query, retained Principal context, and accepted Metamodel at execution and enriches a new internal query before deep-fetch and SQL planning. That seam can constrain the root, inject relationship-navigation predicates, and constrain included relationship reads without mutating or identity-keying the authored query. Future plan and result caches must partition entitlement-sensitive state by the policy context they define.
