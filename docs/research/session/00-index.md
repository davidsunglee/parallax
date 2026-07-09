---
date: 2026-07-09
git_commit: 5e7d99ae3a1908dc658cf440acfa95de976b6ee6
topic: "Session cache and transaction management prior art for Parallax"
type: research
tags: [research, orm, session-cache, identity-map, unit-of-work, transactions, parallax]
status: complete
---

# Research: Session Cache and Transaction Management

This directory collects prior-art research for clarifying the role of a
session-local cache in Parallax. The target Parallax slice considered here is:

- supports a session-local identity/session cache;
- does not include a process-wide identity or query cache;
- does not include cross-process cache coherence;
- still composes with Parallax's existing transaction and unit-of-work rules.

The key local spec context is that `m-unit-work` is active, while
`m-process-cache` and `m-coherence` are deferred. `m-process-cache` currently
means process-level identity and query caching, and `m-coherence` is the
multi-process extension of that process cache. A session-cache slice should not
silently claim those modules unless the spec is changed.

## Findings Index

| File | Subject | Main contribution |
|---|---|---|
| [00-candidate-orms.md](00-candidate-orms.md) | Candidate scan | Ranks EF Core, MikroORM, and Doctrine ORM as the strongest additional sources beyond the requested set |
| [sqlalchemy-session-transactions.md](sqlalchemy-session-transactions.md) | SQLAlchemy | Session-local identity map, Unit of Work, expiration/rollback behavior, explicit separation from query caching |
| [hibernate-session-transactions.md](hibernate-session-transactions.md) | Hibernate | Persistence context/first-level cache, dirty checking, write-behind, optional second-level/query cache separation |
| [prisma-transactions-no-session.md](prisma-transactions-no-session.md) | Prisma | Negative control: transaction APIs without a session identity map or managed object state |
| [reladomo-session-transactions.md](reladomo-session-transactions.md) | Reladomo | Process-wide portal identity/query cache, transaction-local query cache, JTA unit of work, detach/merge prior art |
| [ef-core-dbcontext-transactions.md](ef-core-dbcontext-transactions.md) | Entity Framework Core | `DbContext` as short-lived session, tracking/no-tracking/no-tracking-with-identity-resolution modes |
| [mikroorm-entitymanager-transactions.md](mikroorm-entitymanager-transactions.md) | MikroORM | Request-scoped identity map, explicit global-map prohibition, async request/transaction context |
| [doctrine-entitymanager-transactions.md](doctrine-entitymanager-transactions.md) | Doctrine ORM | EntityManager/UnitOfWork identity map, transactional write-behind, rollback closes manager, optional caches separated |

## Cross-ORM Synthesis

### Session Cache Is A First-Level Identity Scope

Across SQLAlchemy, Hibernate, EF Core, MikroORM, and Doctrine, the closest
common concept is a first-level cache scoped to a session-like object:
`Session`, persistence context, `DbContext`, `EntityManager`, or UnitOfWork. The
portable guarantee is one managed object for a persistent identity inside that
scope. Independent sessions may hold independent objects for the same row.

This is materially narrower than Reladomo's process-wide portal identity cache,
where live persistent objects are interned per mapped type behind a portal.
Reladomo is valuable prior art for semantics, but not the cache scope to copy
for this slice.

### Identity Map Is Not Query Cache

SQLAlchemy and MikroORM are especially clear that ordinary non-primary-key
queries can still hit the database, then coalesce returned rows through the
identity map. Doctrine similarly separates first-level identity mapping from
result caching. Hibernate and Doctrine both make second-level/query caches
optional and separate. EF Core adds an explicit no-tracking mode that bypasses
the context tracker entirely, plus a no-tracking identity-resolution mode that
deduplicates one result without enrolling objects for future flush.

For Parallax, this argues for a narrow session-cache guarantee:

- primary-key lookup may be served from the session identity map;
- SQL-producing reads may still execute and then reuse existing session objects
  for returned primary keys;
- repeated equal operations need not be query-cache hits;
- no process-wide query-result cache or invalidation protocol is implied.

### Transaction Scope And Session Scope Are Related But Not Identical

Most researched ORMs connect sessions to transactions but do not make them the
same concept in all cases:

- SQLAlchemy sessions can be reused across transactions, with autobegin and
  explicit begin patterns.
- Hibernate sessions are usually short-lived around a logical transaction, but
  also document longer conversations.
- EF Core `DbContext` can make each `SaveChanges` transactional by default, or
  participate in an explicit transaction spanning multiple saves and queries.
- Doctrine queues ORM writes until `flush()`, which implicitly wraps writes in a
  transaction unless the caller demarcates one.
- MikroORM treats `flush()` as the synchronization point and supports explicit
  transactional forks with propagation modes.
- Prisma provides transaction scopes without a session identity map, showing
  that transaction atomicity alone does not imply session caching.

Parallax should avoid defining "session cache" as a synonym for "transaction".
The spec can align them for a slice if that is the desired implementation
surface, but the behavioral contract should name both concepts separately.

### Unit Of Work State Often Shares The Same Boundary

In the managed-object ORMs, the session cache is also where Unit of Work state
lives: original snapshots, dirty flags, pending inserts/deletes, relationship
fix-up, lazy references, and flush ordering. That coupling is common, but not
inevitable. Prisma shows explicit write APIs without dirty-checking managed
objects. EF Core and MikroORM show detached/no-tracking reads that can avoid
enrolling objects in the Unit of Work.

For Parallax, session identity and dirty checking should be separate decisions.
A session-cache slice could require identity interning and managed/detached
state without requiring every implementation to support implicit dirty checking
unless that is part of the slice.

### Failure Boundaries Matter

The researched ORMs put real semantics at rollback, flush failure, close, clear,
and detach:

- Hibernate, Doctrine, and MikroORM warn that rollback does not restore in-memory
  object graphs and the session/entity manager should be discarded or cleared.
- Doctrine closes the EntityManager after transactional failure.
- SQLAlchemy expires/expunges objects on rollback and requires an explicit
  rollback after a flush failure before normal use resumes.
- EF Core uses savepoints for failed `SaveChanges` inside an active transaction,
  but also documents unrecoverable context states after some EF exceptions.
- Reladomo's detached copies are independent object snapshots; merge-back
  resolves the original and drives normal transactional work.

The session-cache slice should specify what happens to cached objects and
pending work after rollback or failure. The simplest portable rule is
fail-closed: after rollback or a failed flush/commit, the session cache is no
longer valid for normal managed-object work unless explicitly cleared/reopened.

### Concurrency Is Session-Local

None of the session-style ORMs treat the session object as a thread-safe shared
process cache. SQLAlchemy sessions, Hibernate sessions, EF Core `DbContext`, and
MikroORM entity managers are documented as scoped, mutable objects. MikroORM is
the strongest warning case: it blocks global identity-map use by default and
uses async-local request/transaction contexts to route work to the right fork.

For Parallax, session cache ownership should be explicit in the API surface,
especially for async runtimes. A process-wide client, pool, or adapter can be
shared; the identity map should not be shared accidentally across requests or
concurrent tasks.

## Parallax Design Considerations

### 1. Do Not Overload `m-process-cache`

The current module catalog defines `m-process-cache` as process-level identity
and query cache with invalidation on write. That does not match the
session-local first-level cache in SQLAlchemy, Hibernate, EF Core, MikroORM, or
Doctrine. If Parallax wants a slice with session caching but no process-wide
cache, it likely needs one of these clarifications:

- add a narrower module such as `m-session-cache` or `m-session-identity`;
- move the minimum per-unit identity guarantee into `m-unit-work`;
- define the slice as claiming only selected scenario cases, while documenting
  that it does not claim `m-process-cache`.

The first option is the cleanest vocabulary if the behavior is intended to be a
real reusable module rather than a one-off slice note.

### 2. Define The Minimum Identity Contract

A compact, ORM-aligned session-cache floor could be:

- within one open session, a persistent identity maps to at most one managed
  object;
- repeated primary-key lookup for an already managed object returns that object;
- query materialization reuses an existing managed object for returned primary
  keys;
- independent sessions make no same-instance promise;
- no repeated-operation query-cache hit is required;
- no cross-session or cross-process freshness is promised.

This floor is compatible with SQLAlchemy, Hibernate, EF Core tracking queries,
MikroORM, Doctrine, and a session-scoped subset of Reladomo semantics.

### 3. Choose Read Enrollment Modes Deliberately

The research suggests at least three read modes worth naming, even if only one
is in the first slice:

- tracked read: materialized entities enter the session identity map and Unit of
  Work state;
- detached/no-track read: materialized entities are values or snapshots and are
  not flushed by session dirty checking;
- query-local identity resolution: one result graph is deduplicated without
  enrolling objects into a long-lived session cache.

EF Core and MikroORM provide concrete prior art for keeping these modes distinct.

### 4. Specify Rollback, Clear, Close, And Detach

Session caching needs lifecycle rules, not just lookup rules. Parallax should
decide:

- whether rollback expires, clears, or invalidates the session cache;
- whether failed flush/commit makes the session unusable;
- whether `clear` detaches all managed objects;
- whether `detach` creates a snapshot, removes the live object, or only changes
  managed state;
- whether merge-back exists at all, and if so whether it copies state into the
  managed instance rather than adopting the detached object.

Doctrine's removal of merge is useful prior art: automatic detached-graph merge
is not a free feature and can be a data-integrity hazard.

### 5. Keep Process Cache And Coherence Out Of This Slice

This slice should explicitly exclude:

- process-wide identity interning;
- operation-to-result query caching;
- query-cache invalidation tokens;
- second-level cache regions;
- distributed cache backends;
- cross-process notification or coherence;
- Reladomo full/partial cache loading, off-heap cache, or master-cache replication.

Those belong to `m-process-cache` and `m-coherence` or later implementation
modules, not the session-local cache slice.

### 6. Add Conformance Cases Around Observable Edges

Useful future compatibility cases for a session-cache slice would test:

- same primary key read twice in one session returns the same logical object;
- same primary key read in two sessions does not require same object identity;
- a non-primary-key query that returns an already managed row reuses the managed
  object while still allowing a database round trip;
- a no-track/detached read does not enroll objects for dirty-check flush;
- rollback/failed flush invalidates or clears cached pending state according to
  the chosen lifecycle rule;
- close/clear/detach behavior is observable and deterministic;
- concurrent tasks cannot share one mutable session implicitly.

These cases should not assert process-wide query-cache hits or cross-process
freshness.

## Bottom Line

The prior art points to a distinct Parallax concept: **session-local identity
cache**. It is related to the Unit of Work, often shares its state, and must
have clear lifecycle semantics, but it is not the same as transaction scope and
not the same as `m-process-cache`.

For Parallax, the most defensible slice is a small first-level cache contract:
one managed object per persistent identity inside an explicit session boundary,
query materialization through that identity map, deterministic clear/detach/
rollback behavior, and no claims about process-wide caching or coherence.
