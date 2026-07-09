---
date: 2026-07-09
topic: "MikroORM EntityManager, UnitOfWork, identity map, and transaction management"
type: research
tags: [research, orm, mikroorm, entity-manager, unit-of-work, identity-map, transaction, session-cache]
status: complete
---

# MikroORM EntityManager and Transaction Management

## Summary

MikroORM's `EntityManager` is the central runtime facade over ORM subsystems,
including the `UnitOfWork`, query APIs, repositories, entity loading, entity
factory, transaction context, and result cache. In the v7.1.5 source, each
`EntityManager` instance constructs its own `UnitOfWork`, `EntityLoader`,
`EntityFactory`, comparator, and result-cache adapter handle.
([EntityManager docs](https://mikro-orm.io/docs/entity-manager),
[EntityManager source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L101-L151))

The session-like cache is MikroORM's identity map. The docs explicitly describe
it as an in-memory cache only in a narrow sense: it starts empty, is filled as
the entity manager loads or registers entities, returns known instances on
identity hits, and is intended for one request rather than cross-request result
caching. MikroORM requires a unique identity map per request, blocks use of the
global identity map by default, and routes global `EntityManager` calls through
an async-local request or transaction fork when available.
([Identity Map docs](https://mikro-orm.io/docs/identity-map#what-is-an-identity-map),
[Global Identity Map docs](https://mikro-orm.io/docs/identity-map#global-identity-map),
[RequestContext docs](https://mikro-orm.io/docs/identity-map#requestcontext-helper),
[EntityManager.getContext source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L2615-L2637))

Flush is both the Unit of Work synchronization point and the default transaction
boundary. `em.flush()` computes change sets from managed entities and writes
them to the database, and implicit transaction demarcation wraps queued
INSERT/UPDATE/DELETE operations in a transaction when the driver supports it.
Explicit `em.transactional(cb)` creates a transactional fork, flushes before
commit, and supports propagation modes including nested savepoints.
([EntityManager docs, Persist and Flush](https://mikro-orm.io/docs/entity-manager#persist-and-flush),
[Unit of Work docs, Implicit Transactions](https://mikro-orm.io/docs/unit-of-work#implicit-transactions),
[Transactions docs](https://mikro-orm.io/docs/transactions#transaction-demarcation),
[TransactionManager source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionManager.ts#L21-L57))

## EntityManager/session responsibilities

### Identity map ownership

MikroORM keeps fetched objects inside the `UnitOfWork`; a repeated primary-key
lookup returns the same object instance and can skip the second database round
trip. For non-primary-key criteria, the query still goes to the database, but
the row primary key is checked against the Unit of Work so the returned object
reference is still the existing managed instance.
([Unit of Work docs](https://mikro-orm.io/docs/unit-of-work#unit-of-work-and-transactions),
[UnitOfWork source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L43-L90),
[IdentityMap source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/IdentityMap.ts#L3-L77))

`em.clear()` clears the identity map and makes currently managed entities
detached. `em.fork()` returns a new `EntityManager` with its own identity map;
by default it starts clear, while `clear: false` copies managed entities and
pending persist/orphan-removal state into the fork. Disabling identity-map
tracking for a query creates a temporary context, loads there, clears it, and
returns detached entities that must be merged before flush can affect them.
([Identity Map docs](https://mikro-orm.io/docs/identity-map#forking-entity-manager),
[EntityManager docs, Disabling identity map](https://mikro-orm.io/docs/entity-manager#disabling-identity-map-and-change-set-tracking),
[EntityManager.clear/fork source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L2450-L2577))

### UnitOfWork and change-set computation

The Unit of Work stores the identity map, persist/remove/orphan-remove stacks,
computed change sets, collection updates, extra updates, queued action metadata,
and loaded entities. It constructs `ChangeSetComputer` and
`ChangeSetPersister` helpers for diffing and write execution.
([UnitOfWork source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L43-L90))

For dirty checking, the docs say MikroORM keeps a copy of all properties and
associations when an object is fetched, then compares original values with
current object values during flush. The `WrappedEntity` also stores entity state
from load or flush time, and that state is used by the Unit of Work to compute
differences. In source, `merge()` and `register()` store identity-map entries
and snapshots, and `computeChangeSets()` walks removal stacks, identity-map
entities, persisted entities, and orphan removals to prepare changes.
([Unit of Work docs, How MikroORM Detects Changes](https://mikro-orm.io/docs/unit-of-work#how-mikroorm-detects-changes),
[Entity state docs](https://mikro-orm.io/docs/entity-manager#entity-state-and-wrappedentity),
[UnitOfWork merge/register source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L93-L201),
[UnitOfWork computeChangeSets source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L725-L771))

`em.persist(entity)` marks new entities for future persistence and makes them
managed by the given `EntityManager`; managed entities loaded from the database
do not need another `persist()` call for ordinary updates before `flush()`.
Persist decides insert versus update and computes the relevant change set, with
cascade persist for not-yet-persisted references. `em.remove(entity)` marks an
entity instance or reference for deletion; `em.nativeDelete()` is documented as
the direct DELETE-query alternative.
([EntityManager docs, Persist and Flush](https://mikro-orm.io/docs/entity-manager#persist-and-flush),
[EntityManager docs, Persisting and Cascading](https://mikro-orm.io/docs/entity-manager#persisting-and-cascading),
[EntityManager docs, Removing entities](https://mikro-orm.io/docs/entity-manager#removing-entities),
[Unit of Work docs, Persisting Managed Entities](https://mikro-orm.io/docs/unit-of-work#persisting-managed-entities))

`em.flush()` delegates to `UnitOfWork.commit()`. The source dispatches
`beforeFlush`, computes change sets, skips opening a transaction if there is
nothing to do, otherwise runs `persistToDatabase()` inside an implicit
transaction when there is no active transaction, the platform supports
transactions, and `implicitTransactions` is enabled.
([EntityManager.flush source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L2420-L2427),
[UnitOfWork.commit source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L592-L667))

### Entity states, references, and population

The docs define a managed entity as one fetched from the database through
`em.find()`, `em.findOne()`, or another managed entity, or one registered as new
through `em.persist()`. Entities loaded with `disableIdentityMap` are detached;
calling `flush()` after modifying them has no effect unless they are merged
first. Entities with explicit primary keys may be added to the identity map but
still remain unmanaged until they get an `EntityManager` reference.
([EntityManager docs, Persist and Flush](https://mikro-orm.io/docs/entity-manager#persist-and-flush),
[EntityManager docs, Disabling identity map](https://mikro-orm.io/docs/entity-manager#disabling-identity-map-and-change-set-tracking),
[Unit of Work docs, Entities with explicit primary key](https://mikro-orm.io/docs/unit-of-work#entities-with-explicit-primary-key))

MikroORM's documented lazy identity placeholder is an entity reference: a normal
entity class instance with only the primary key available, not a fully loaded
object. References are stored in the identity map like other entities and can be
used for relation assignment, removal, and collection membership. `wrap()` or
`BaseEntity` methods expose initialized-state checks and initialization.
([EntityManager docs, Entity references](https://mikro-orm.io/docs/entity-manager#entity-references),
[EntityManager docs, Entity state](https://mikro-orm.io/docs/entity-manager#entity-state-and-wrappedentity))

Population is an `EntityManager` responsibility at query time and after load.
`populate` options on find calls initialize requested relation paths, and
`em.populate()` can populate relations on already loaded entities. The docs also
show that search joins used for filtering by referenced entity fields do not
automatically populate those relations unless `populate` is specified.
([EntityManager docs, Fetching Entities](https://mikro-orm.io/docs/entity-manager#fetching-entities-with-entitymanager),
[EntityManager docs, Searching by referenced entity fields](https://mikro-orm.io/docs/entity-manager#searching-by-referenced-entity-fields))

`em.refresh(entity)` reloads an entity from the database with `refresh: true`
and disabled auto-flush; the docs warn that changes made to that entity are
lost. Streaming is a documented exception to normal managed-entity behavior:
streamed entities are not managed, and identity holds only within the returned
entity graph.
([EntityManager docs, Refreshing entity state](https://mikro-orm.io/docs/entity-manager#refreshing-entity-state),
[EntityManager docs, Streaming](https://mikro-orm.io/docs/entity-manager#streaming))

## Transaction semantics

### Implicit and explicit boundaries

MikroORM queues writes until `em.flush()`, and transaction docs state that this
flush starts and commits or rolls back a transaction for implicit demarcation.
The Unit of Work docs describe the same behavior: `flush()` runs computed
changes inside a database transaction if the driver supports transactions.
([Transactions docs, Approach 1](https://mikro-orm.io/docs/transactions#approach-1-implicitly),
[Unit of Work docs, Implicit Transactions](https://mikro-orm.io/docs/unit-of-work#implicit-transactions))

The explicit API is `em.transactional(cb)` or manual `begin()` / `commit()` /
`rollback()`. The docs state that `commit()` flushes before the actual commit
query, and that `em.transactional(cb)` and `@Transactional()` flush the inner
`EntityManager` before transaction commit. The source matches this: `commit()`
calls `em.flush()` before connection commit, while `transactional()` delegates
to `TransactionManager`.
([Transactions docs, Approach 2](https://mikro-orm.io/docs/transactions#approach-2-explicitly),
[EntityManager transaction source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L1670-L1746))

Flush behavior is configurable by flush mode. `COMMIT` delays flush until the
current transaction commits, `AUTO` is the default and flushes only when needed,
and `ALWAYS` flushes before every query. The docs say `AUTO` detects overlap
with the entity being queried, but managed-entity changes need `em.persist()` to
trigger auto-flush detection.
([Unit of Work docs, Flush Modes](https://mikro-orm.io/docs/unit-of-work#flush-modes),
[FlushMode source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/enums.ts#L5-L13),
[EntityManager.tryFlush source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L2432-L2447))

### Propagation, nesting, and async transaction context

For `em.transactional`, MikroORM defaults to `NESTED` propagation: if a
transaction already exists, it creates a savepoint rather than joining the
outer transaction. `@Transactional()` defaults to `REQUIRED`, which joins an
existing transaction or creates a new one. The docs list `NESTED`, `REQUIRED`,
`REQUIRES_NEW`, `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, and `NEVER` behavior.
([Transactions docs, Transaction Propagation](https://mikro-orm.io/docs/transactions#transaction-propagation),
[TransactionPropagation source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/enums.ts#L330-L346))

The source-level transaction manager implements those propagation modes by
choosing between callback reuse, a new transaction, a nested transaction with
the existing transaction context passed as `ctx`, a suspended transaction, or
error states. It creates transaction forks with `clear: options.clear ?? false`
and runs transactional work under `TransactionContext.create(fork, ...)`.
([TransactionManager source, dispatch](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionManager.ts#L21-L80),
[TransactionManager source, nested](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionManager.ts#L162-L186),
[TransactionManager source, processing](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionManager.ts#L258-L303))

Transaction contexts and request contexts are async-local. `RequestContext`
uses `AsyncLocalStorage` to hold request-scoped `EntityManager` forks, and
`TransactionContext` uses the same async-context helper to maintain the
transaction-scoped `EntityManager` across async operations. `EntityManager`
context resolution prefers transaction context first, then configured request
context, then the current entity manager, with global-context validation.
([Identity Map docs, RequestContext helper](https://mikro-orm.io/docs/identity-map#requestcontext-helper),
[RequestContext source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/RequestContext.ts#L1-L76),
[TransactionContext source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionContext.ts#L1-L35),
[EntityManager.getContext source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L2615-L2637))

Transactional context propagation defaults to sharing managed entities from the
upper context into the inner fork (`clear: false`). The docs warn that parallel
transactions should use a fresh fork or `clear: true`; otherwise entity
instances are shared across transactions and can interfere, including unexpected
reinsertion of a removed entity. Changes made in the transaction callback are
propagated back to the upper context.
([Transactions docs, Context propagation](https://mikro-orm.io/docs/transactions#context-propagation),
[TransactionManager source, merge back to parent](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionManager.ts#L189-L235))

MikroORM exposes transaction isolation choices through transaction options:
`READ_UNCOMMITTED`, `READ_COMMITTED`, `SNAPSHOT`, `REPEATABLE_READ`, and
`SERIALIZABLE`. Transactions can also be disabled globally, for a transactional
call, or for a fork; when disabled, `transactional()` and `begin()` become
no-ops, while `commit()` still calls `flush()`.
([Transactions docs, Isolation levels](https://mikro-orm.io/docs/transactions#isolation-levels),
[Transactions docs, Disabling transactions](https://mikro-orm.io/docs/transactions#disabling-transactions),
[IsolationLevel source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/enums.ts#L259-L270))

## Cache/identity semantics

The identity map guarantees object identity only within the current
request/session context. The docs emphasize one identity map per request and
state that the identity map is different from a result cache: result caches are
for performance across requests, while identity maps are for object identity,
batching, and memory reduction within a single request.
([Identity Map docs](https://mikro-orm.io/docs/identity-map#what-is-an-identity-map),
[Global Identity Map docs](https://mikro-orm.io/docs/identity-map#global-identity-map))

The identity map does not guarantee process-wide coherence. MikroORM explicitly
disallows global identity-map use by default because using the global
`EntityManager` without request context is almost always wrong and lets request
handlers interfere with each other. The docs identify two concrete shared-map
failures: unbounded memory growth because one request cannot safely clear a map
used by another request, and unstable API responses because population state is
stored in the identity map and can leak between handlers.
([Identity Map docs, Why Request Context is needed](https://mikro-orm.io/docs/identity-map#why-is-request-context-needed))

The documented cross-request cache is a separate result cache. It applies to
`EntityManager` find/count methods and QueryBuilder result methods; the default
in-memory cache is shared for the whole `MikroORM` instance with a default
one-second expiration, can be enabled globally, and can be cleared by explicit
cache key. In source, `EntityManager.tryCache()` and `storeCache()` use the
configured `resultCache` adapter and can merge cached data back into entity
instances.
([Result cache docs](https://mikro-orm.io/docs/caching),
[EntityManager result-cache source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L3132-L3192))

## Failure modes and lifecycle edge cases

Using the global identity map is blocked by default. It can be disabled with
`allowGlobalContext` or `MIKRO_ORM_ALLOW_GLOBAL_CONTEXT`, but the docs frame
global identity-map use as a source of "weird bugs" because request handlers
need dedicated contexts to avoid interference.
([Global Identity Map docs](https://mikro-orm.io/docs/identity-map#global-identity-map))

After an exception during implicit flush, MikroORM rolls the transaction back
automatically. For explicit demarcation, the docs say rollback should happen
immediately and exceptions should generally be rethrown. Previously managed or
removed instances become detached; their object state is not rolled back and can
be out of sync with the database. Starting a new unit of work after an exception
should use a new `EntityManager` fork with a cleared identity map.
([Transactions docs, Exception Handling](https://mikro-orm.io/docs/transactions#exception-handling))

`disableIdentityMap` returns detached entities, so mutating them followed by
`flush()` has no effect until they are merged. `em.refresh(entity)` discards
in-memory changes to that entity. Streaming returns unmanaged entities, with
identity only within the returned graph.
([EntityManager docs, Disabling identity map](https://mikro-orm.io/docs/entity-manager#disabling-identity-map-and-change-set-tracking),
[EntityManager docs, Refreshing entity state](https://mikro-orm.io/docs/entity-manager#refreshing-entity-state),
[EntityManager docs, Streaming](https://mikro-orm.io/docs/entity-manager#streaming))

Pessimistic locks require an open transaction; MikroORM throws if a pessimistic
lock is requested without one. Optimistic version conflicts during `em.flush()`
throw `OptimisticLockError` and roll back or mark the active transaction for
rollback.
([Transactions docs, Optimistic Locking](https://mikro-orm.io/docs/transactions#optimistic-locking),
[Transactions docs, Pessimistic Locking](https://mikro-orm.io/docs/transactions#pessimistic-locking))

## Implications for Parallax session-cache slice

MikroORM is direct prior art for a Parallax slice that supports session caching
without process-wide cache or coherence concerns. Its identity map is explicitly
request/session-local, starts empty, is clearable, and is separated from the
documented result cache. The global identity-map prohibition is the main design
signal: object identity belongs to an explicit session/request boundary, not to
the process.
([Identity Map docs](https://mikro-orm.io/docs/identity-map#what-is-an-identity-map),
[Global Identity Map docs](https://mikro-orm.io/docs/identity-map#global-identity-map),
[Result cache docs](https://mikro-orm.io/docs/caching))

The useful cache guarantee is per-session identity resolution, not query-result
memoization. MikroORM can skip a primary-key lookup already present in the Unit
of Work, but non-primary-key queries still hit the database and then coalesce by
primary key. For Parallax, that separates "same row maps to same in-memory
object in this session" from "same query is cached."
([Unit of Work docs](https://mikro-orm.io/docs/unit-of-work#unit-of-work-and-transactions))

The Unit of Work coupling is also relevant: the same session cache owns original
snapshots, dirty checking inputs, managed/detached status, remove/persist
queues, and flush ordering. A Parallax session-cache slice can stay small if it
defines cache ownership together with the minimal Unit of Work lifecycle:
load/register, original snapshot, mark persist/remove, clear/detach, and flush.
([Unit of Work docs, How MikroORM Detects Changes](https://mikro-orm.io/docs/unit-of-work#how-mikroorm-detects-changes),
[UnitOfWork source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L43-L90))

Transaction scope does not need a process-wide cache. MikroORM's implicit flush
transaction and explicit transactional fork show that transaction state can be
session-local and async-local, with nested transaction behavior modeled by
savepoints and by whether inner forks share or clear the parent identity map.
The important edge for Parallax is to specify whether a transaction callback
reuses/copies the parent session cache or starts with a clear cache; MikroORM's
default `clear: false` gives convenience but creates documented interference
risks for parallel transactions.
([Transactions docs, Context propagation](https://mikro-orm.io/docs/transactions#context-propagation),
[TransactionManager source](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionManager.ts#L177-L186))

Detached/no-tracking reads are a separate behavioral mode. MikroORM's
`disableIdentityMap` path is useful prior art for a Parallax option that keeps
the session cache clean and returns objects that are not dirty-checked or
flushed unless explicitly merged.
([EntityManager docs, Disabling identity map](https://mikro-orm.io/docs/entity-manager#disabling-identity-map-and-change-set-tracking),
[EntityManager source, disableIdentityMap path](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L224-L231))

## Source map

Primary docs:

- [Working with Entity Manager](https://mikro-orm.io/docs/entity-manager)
- [Unit of Work and Transactions](https://mikro-orm.io/docs/unit-of-work)
- [Identity Map and Request Context](https://mikro-orm.io/docs/identity-map)
- [Transactions and Concurrency](https://mikro-orm.io/docs/transactions)
- [Result cache](https://mikro-orm.io/docs/caching)

GitHub source permalinks, resolved to MikroORM v7.1.5 commit
`da2e8f8510b55fc8c42f9587d53c47b11f6f5381`:

- [EntityManager construction and owned subsystems](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L101-L151)
- [EntityManager transaction methods](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L1670-L1746)
- [EntityManager flush, clear, fork, getUnitOfWork, getContext](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L2420-L2637)
- [EntityManager result cache helpers](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/EntityManager.ts#L3132-L3192)
- [UnitOfWork fields and constructor](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L43-L90)
- [UnitOfWork merge/register snapshots](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L93-L201)
- [UnitOfWork commit and implicit transaction decision](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L592-L667)
- [UnitOfWork change-set computation](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/UnitOfWork.ts#L725-L771)
- [IdentityMap implementation](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/unit-of-work/IdentityMap.ts#L3-L77)
- [RequestContext implementation](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/RequestContext.ts#L1-L76)
- [TransactionContext implementation](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionContext.ts#L1-L35)
- [TransactionManager propagation and transaction flow](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/utils/TransactionManager.ts#L21-L303)
- [FlushMode enum](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/enums.ts#L5-L13)
- [IsolationLevel enum](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/enums.ts#L259-L270)
- [TransactionPropagation enum](https://github.com/mikro-orm/mikro-orm/blob/da2e8f8510b55fc8c42f9587d53c47b11f6f5381/packages/core/src/enums.ts#L330-L346)
