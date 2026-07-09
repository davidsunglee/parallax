---
date: 2026-07-09
topic: "Doctrine ORM EntityManager / UnitOfWork session and transaction management"
type: research
tags: [research, prior-art, doctrine, orm, entity-manager, unit-of-work, transactions, cache, parallax]
status: complete
---

# Doctrine ORM EntityManager / UnitOfWork Session and Transaction Management

## Summary

Doctrine ORM's `EntityManager` is the central ORM access point for persistence
and object queries. In the current ORM 3.6.7 source it is also the facade over
the DBAL `Connection`, `UnitOfWork`, metadata factory, repositories, proxies,
event manager, and optional second-level cache API. The `UnitOfWork` is the
object-level transaction coordinator that tracks changes and writes them in the
proper order. [D-architecture] [S-em-fields] [S-uow-fields]

The Doctrine "session" equivalent is the `EntityManager` plus its
`UnitOfWork`. A new unit of work starts when an `EntityManager` is created and
after `flush()`. `persist()` and `remove()` schedule work; only `flush()` writes
to the database. [D-working-objects] [S-em-flush-find]

The first-level cache is the identity map inside the `UnitOfWork`. Doctrine
documents that repeated retrieval of the same entity identity through the same
`EntityManager` returns the same object instance, including through repository
finders and DQL, until the identity map is cleared. The source stores managed
entities by root class name and identifier hash, and rejects a second live object
for the same identity. [D-identity-map] [S-uow-identity-map] [S-uow-add-identity]

Transactionally, Doctrine can demarcate implicitly around `flush()` or
explicitly through DBAL `Connection` transaction APIs and
`EntityManager#wrapInTransaction()`. If `flush()` or transactional work fails,
Doctrine rolls back the database transaction, closes the `EntityManager`, and
leaves previously managed objects detached with in-memory state not restored to
database state. [D-transactions] [S-em-wrap] [S-uow-commit] [S-em-interface-tx]

Doctrine separates the first-level identity map from optional caches. The
ordinary ORM cache page covers query, result, and metadata caches; the
second-level cache page covers optional entity, association, collection, and
second-level query caching. Those caches have explicit invalidation and
distributed-environment caveats, while first-level identity-map semantics do not
require process-wide coherence. [D-caching] [D-second-level-cache]

## EntityManager/session responsibilities

### Access facade and ownership

Doctrine's architecture guide calls `EntityManager` the central access point for
managing object persistence and querying persistent objects. The source matches
that description: `EntityManager` owns a DBAL `Connection`, creates a
`UnitOfWork`, exposes repositories and query builders, configures metadata
caching, and creates the optional second-level cache API only when second-level
cache is enabled. [D-architecture] [S-em-fields]

The source-level class comment describes `EntityManager` as a facade over
subsystems such as the UnitOfWork, query language, and repository API. The class
is final by contract in the docblock: extension is by decoration or interface,
not inheritance. [S-em-fields] [S-upgrade-partial]

### Entity states

Doctrine uses four lifecycle states: `NEW`, `MANAGED`, `DETACHED`, and
`REMOVED`. The architecture guide defines them relative to persistent identity,
association with an `EntityManager`, and pending deletion. The source mirrors
those as `UnitOfWork::STATE_*` constants. [D-architecture] [D-entity-state]
[S-uow-fields]

`MANAGED` means the object is associated with an `EntityManager` and is not
removed. `REMOVED` remains associated until the next flush by that same
`EntityManager`. `DETACHED` means the object has persistent identity but is not
currently associated with an `EntityManager`. `NEW` has no persistent identity
and no `EntityManager` association. [D-entity-state]

### Identity map and first-level cache

Doctrine documents the identity-map behavior directly: within the same
`EntityManager`, loading the same entity identity repeatedly returns the same
object instance, no matter whether the load uses `find`, repository methods, or
DQL. `EntityManager#clear()` clears that identity map so later reads load fresh
instances. [D-identity-map]

The implementation stores the identity map in `UnitOfWork::$identityMap`,
grouped by root class name and identifier hash. `registerManaged()` records the
identifier, marks the object managed, stores original entity data, and adds the
object to the identity map. `EntityManager#find()` checks
`UnitOfWork#tryGetById()` before loading from the database. [S-uow-identity-map]
[S-uow-register] [S-em-flush-find] [S-uow-try-get]

The implementation also enforces the one-object-per-identity rule inside a unit
of work: adding an identity already present for a different object raises an
identity-collision exception; adding the same object again is a no-op. [S-uow-add-identity]

### UnitOfWork, dirty checking, and write-behind

Doctrine describes a unit of work as an object-level transaction. The
architecture guide says the `EntityManager` and underlying `UnitOfWork` use
transactional write-behind: SQL execution is delayed until `flush()`, so in-memory
objects are synchronized with the database in a defined unit of work.
[D-working-objects] [D-architecture]

`UnitOfWork` stores original entity data for managed objects and uses that data
for change-set calculation. The internals documentation says Doctrine keeps a
copy of fields and associations after fetch, then on `flush()` compares managed
objects against those originals and queues SQL updates only for changed fields.
[D-uow-internals] [S-uow-fields]

The default change-tracking policy is deferred implicit: Doctrine compares
managed entities at commit time and also discovers new entities reachable from
managed entities. Deferred explicit still compares properties at commit time,
but only for entities explicitly marked through `persist()` or save cascade.
[D-change-tracking]

The cost of flush is tied to the number of managed entities and the change
tracking policy. Doctrine therefore treats the UnitOfWork size as a performance
and memory concern. [D-working-objects] [D-change-tracking]

### Persist, remove, flush, and reachability

`persist()` makes a new entity managed, but does not issue SQL immediately. For
managed entities it is ignored except for cascade handling; for detached
entities, Doctrine documents that passing them to `persist()` is invalid and can
fail on flush. [D-persist-remove] [S-em-clear-persist-remove-detach]

`remove()` marks a managed entity as removed; SQL `DELETE` occurs on the next
relevant `flush()`. Removed entities retain their in-memory state, can remain
visible until synchronization, and are removed from loaded in-memory collections
during flush. Calling `remove()` on a detached entity throws. [D-persist-remove]
[S-em-clear-persist-remove-detach]

`flush()` synchronizes new, managed, and removed entities with the database.
Managed entities get SQL `UPDATE` only when persistent fields changed; new
entities get SQL `INSERT`; removed entities get their persistent state deleted.
Doctrine explicitly says `flush()` is never called implicitly by ORM application
operations. [D-synchronization] [S-em-flush-find]

Persistence by reachability is part of cascade persist: during flush, new
entities found in collections marked `cascade: persist` are persisted; new
entities found without that cascade cause an exception and rollback of the flush.
Cascade operations run in memory and can initialize lazy object graphs.
[D-association-cascade]

### Detach, clear, close, and merge removal

`detach()` causes a managed entity to become detached; unflushed changes,
including removals, are not synchronized after detachment. Existing references
from other objects continue to point at the detached object. [D-detach]
[S-em-clear-persist-remove-detach]

`clear()` detaches all currently managed entities by clearing the UnitOfWork
state. `close()` calls `clear()` and marks the `EntityManager` closed; the
interface documents that a closed entity manager may no longer be used.
[D-detach] [S-em-clear-persist-remove-detach] [S-uow-clear] [S-em-interface-tx]

Doctrine ORM 3 removed merge semantics. The upgrade notes state that merging
detached entities was removed because it fit poorly with PHP's share-nothing
architecture and caused data-integrity issues in managed graphs. `UnitOfWork`
merge was removed, and legacy `EntityManager::merge()` calls are documented as
throwing. [S-upgrade-merge]

Doctrine also removed partial flush and partial clear capabilities. The upgrade
notes say `flush()`/`commit()` no longer accept a single entity or entity array,
and `EntityManager#clear($entityName)` was removed because partial clear caused
integrity issues in managed graphs. [S-upgrade-partial]

## Transaction semantics

### Implicit flush transaction

Doctrine's transaction docs state that ORM write operations are queued until
`EntityManager#flush()`, and `flush()` wraps those changes in a single
transaction. This implicit mode is sufficient when all data manipulation in the
unit of work goes through the ORM domain model. [D-transactions]

The source implements this in `UnitOfWork#commit()`: it computes changesets,
checks unintended non-cascaded new associations, opens a DBAL transaction,
executes collection deletions, entity insertions, updates, extra updates,
collection updates, and entity deletions, then commits the connection.
[S-uow-commit]

If there are no scheduled insertions, updates, deletions, collection updates, or
orphan removals, `UnitOfWork#commit()` dispatches flush events, cleans transient
commit state, and returns without opening a database transaction. [S-uow-commit]

### Explicit demarcation and DBAL connection APIs

Doctrine allows explicit transaction demarcation through
`$em->getConnection()->beginTransaction()`, `commit()`, and `rollBack()`. The
ORM docs say this is required when custom DBAL operations must participate in
the same unit of work or when using EntityManager APIs that require an active
transaction. [D-transactions]

The DBAL transaction docs define the `Connection` transaction API as
`beginTransaction()`, `commit()`, and `rollBack()`, plus the
`Connection#transactional($func)` control abstraction. DBAL also exposes
transaction isolation control through `setTransactionIsolation()` and
`getTransactionIsolation()`. [D-dbal-transactions]

`EntityManager#wrapInTransaction($func)` differs from DBAL
`Connection#transactional($func)` by flushing the EntityManager before commit
and closing it on exception in addition to rolling back. The interface source
documents that `flush()` runs before transaction commit and failure rolls back
the transaction, closes the `EntityManager`, and rethrows. [D-transactions]
[S-em-interface-tx] [S-em-wrap]

DBAL nested transaction calls are savepoint-backed, not independent database
transactions. The DBAL docs state that nested `beginTransaction()` uses SQL
savepoints and there is always one real database transaction; directly bypassing
DBAL through native PDO transaction calls can corrupt DBAL's nesting state.
[D-dbal-transactions] [S-dbal-begin-commit-rollback] [S-dbal-savepoints]

### Rollback and exception lifecycle

For implicit demarcation, an exception during `flush()` rolls back the
transaction and closes the `EntityManager`. For explicit demarcation, Doctrine
instructs callers to roll back immediately, close the `EntityManager`, discard
it, and use a new `EntityManager` for later work. [D-transactions]

After rollback and close, Doctrine detaches all previously managed or removed
objects. Their PHP object state is not rolled back to database state; it remains
whatever it was when the transaction rolled back and may be inaccurate.
[D-transactions] [S-uow-commit]

The source follows that contract. On unsuccessful `UnitOfWork#commit()`,
Doctrine closes the `EntityManager`, rolls back the DBAL transaction if still
active, and runs rollback completion hooks. `EntityManager#wrapInTransaction()`
also closes the EntityManager before rolling back an active transaction when the
callback, flush, or commit fails. [S-uow-commit] [S-em-wrap]

DBAL `Connection#transactional()` rolls back if the callback or commit fails and
rethrows the exception. It does not know about ORM UnitOfWork state, which is
why the ORM wrapper adds flush and EntityManager-close behavior. [S-dbal-transactional]
[S-em-interface-tx]

### Optimistic and pessimistic locking

Doctrine supports optimistic locking with a version field. On flush, a version
conflict raises `OptimisticLockException` and the active transaction is rolled
back or marked for rollback. The docs emphasize that database transactions are
not suitable for long "user think time" workflows, so optimistic locking moves
part of concurrency control to the application. [D-transactions]

Doctrine supports pessimistic locking using database row-level lock mechanisms,
not an in-ORM lock manager. Pessimistic locks require an active transaction; the
docs say Doctrine throws if a pessimistic lock is requested without one, and
the source enforces that requirement for pessimistic read/write lock modes.
[D-transactions] [S-em-lock-requirements]

## Cache/identity semantics

### First-level identity map guarantees

The identity map guarantees object identity only inside the current
`EntityManager`/UnitOfWork scope. It deduplicates objects by entity identity and
returns the same managed object for repeated reads in that scope. It is cleared
by `clear()` and by `close()`, after which the affected objects are detached.
[D-identity-map] [D-detach] [S-uow-clear]

This first-level behavior is not a query-result cache. Doctrine may execute a
query and still materialize rows into existing managed objects because the
identity map already owns those identities. The separate result cache is an
optional configured cache for query results. [D-identity-map] [D-caching]

Doctrine's first-level identity map does not require process-wide coherence.
The documented scope is the identity map held by the current EntityManager
during a PHP request, and the implementation storage lives in one UnitOfWork
instance. [D-identity-map] [S-uow-identity-map]

### Optional caches

Doctrine ORM can use PSR-6 cache adapters for query, result, and metadata
caches. Query cache stores DQL-to-SQL transformation results; result cache stores
query results so the database need not be queried again for the same configured
result; metadata cache stores parsed mapping metadata. [D-caching]

Second-level cache is optional and separate from the UnitOfWork identity map.
It can cache entities, associations, and collections. Its second-level query
cache stores query results as identifiers while entity values live in the
second-level cache. The second-level cache examples explicitly call
`EntityManager#clear()` between cache-backed reads and note that cached reloads
produce different object instances. [D-second-level-cache]

Second-level cache is not transparent process-wide coherence. The docs state
that caches are not aware of changes made by another application and must be
checked or invalidated through the cache API. In distributed deployments,
Doctrine warns that local cache drivers such as APC or file-based caches do not
reflect updates made on other machines unless a shared distributed cache is
used. [D-second-level-cache]

DQL `UPDATE` and `DELETE` bypass the second-level cache and do not invalidate
already cached entities automatically; eviction requires a query hint or cache
API calls. [D-second-level-cache]

## Failure modes and lifecycle edge cases

The database and UnitOfWork are intentionally out of sync between state changes
and flush. Doctrine documents that scheduled removals can still be returned by
queries and collections, new persisted entities do not appear in query results,
and changed entities are not overwritten by database state because the identity
map treats the current managed object as authoritative in that scope.
[D-synchronization]

Failed flush can leave generated identifiers in memory even though the database
transaction failed. The persist docs warn not to assume generated identifiers
are unavailable after failed flush, just as they are not guaranteed before a
successful flush. [D-persist-remove]

Detached objects are not tracked. Changes to a detached object are not flushed,
Doctrine no longer holds references to detached entities, and serialization can
produce detached entities. The architecture guide also warns that serialized
managed/proxy graphs are problematic because unserialized objects are detached
and cannot initialize proxies through the old EntityManager. [D-detach]
[D-architecture]

Read-your-own in-memory state is local to the identity map, not a database
commit guarantee. Before flush, managed object changes can be observed through
the same object instance, but the database is not synchronized until flush.
[D-identity-map] [D-synchronization]

Identity collision is a hard error in the implementation: if an object with the
same root class and identifier hash is already in the identity map and is not
the same object, `UnitOfWork#addToIdentityMap()` raises an
`EntityIdentityCollisionException`. [S-uow-add-identity]

## Implications for Parallax session-cache slice

For a Parallax slice that supports session caching while intentionally excluding
process-wide cache and coherence concerns, Doctrine provides a narrow prior-art
shape: the session cache can be one identity map per session/unit of work, with
one object per persistent identity only inside that scope. Doctrine's guarantee
does not require same-object identity across independent EntityManagers or
processes. [D-identity-map] [S-uow-identity-map]

The cache boundary should align with the UnitOfWork lifecycle. Doctrine starts a
new unit of work after flush, clears identity and scheduling state on clear, and
closes/detaches all managed objects after transactional failure. That supports a
session-cache design where rollback or close invalidates the session-local
identity map rather than trying to repair object state in place. [D-working-objects]
[D-transactions] [S-uow-clear] [S-uow-commit]

Persistence operations should be scheduling operations until flush. Doctrine's
`persist()` and `remove()` do not execute SQL immediately; flush computes
changes, handles reachability/cascade rules, and executes database work inside a
transaction. A Parallax session-cache slice can separate local object identity
and pending work from durable database state in the same way. [D-persist-remove]
[D-synchronization] [D-association-cascade] [S-uow-commit]

Dirty checking can be snapshot-based or explicit-tracking-based, but it has a
cost proportional to managed state. Doctrine's default compares managed objects
against original data and its deferred explicit policy narrows the set of
checked objects. That distinction matters for a session cache because cache size
is also change-detection cost. [D-uow-internals] [D-change-tracking]
[S-uow-fields]

Optional process-wide or distributed cache semantics should remain out of scope
for the session-cache slice. Doctrine treats query/result/metadata caches and
second-level cache as separate configured systems, with explicit distributed
cache and invalidation caveats. Those concerns are not necessary for first-level
identity-map semantics. [D-caching] [D-second-level-cache]

Doctrine's removal of merge is a cautionary lifecycle data point: detached graph
merge semantics were removed for data-integrity reasons. A Parallax session
slice can document detach/clear/close behavior without implying automatic
reattachment or graph merge unless that behavior is explicitly specified.
[S-upgrade-merge] [D-detach]

Session cache is not concurrency control. Doctrine keeps optimistic version
checks and pessimistic row locks in transaction/locking APIs, not in the
identity map itself. A Parallax session cache should therefore avoid claiming
freshness or cross-session conflict detection without an explicit locking or
versioning layer. [D-transactions] [S-em-lock-requirements]

## Source map

Doctrine ORM documentation:

- [D-architecture] [Architecture](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/architecture.html): package responsibilities, entity states, EntityManager, transactional write-behind, UnitOfWork.
- [D-working-objects] [Working with Objects](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-objects.html): EntityManager/UnitOfWork lifecycle, flush-only writes, identity map, persist/remove/detach/synchronization/entity state.
- [D-identity-map] [Working with Objects: Entities and the Identity Map](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-objects.html#entities-and-the-identity-map).
- [D-persist-remove] [Working with Objects: Persisting and Removing entities](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-objects.html#persisting-entities).
- [D-detach] [Working with Objects: Detaching entities](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-objects.html#detaching-entities).
- [D-synchronization] [Working with Objects: Synchronization with the Database](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-objects.html#synchronization-with-the-database).
- [D-entity-state] [Working with Objects: Entity State](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-objects.html#entity-state).
- [D-uow-internals] [Doctrine Internals explained](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/unitofwork.html): identity map and change detection internals.
- [D-change-tracking] [Change Tracking Policies](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/change-tracking-policies.html).
- [D-association-cascade] [Working with Associations: Transitive persistence / Cascade Operations](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-associations.html#transitive-persistence-cascade-operations).
- [D-transactions] [Transactions and Concurrency](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/transactions-and-concurrency.html): implicit/explicit demarcation, rollback behavior, optimistic and pessimistic locking.
- [D-caching] [Caching](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/caching.html): query, result, and metadata caches.
- [D-second-level-cache] [The Second Level Cache](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/second-level-cache.html): entity/association/collection/query cache, cache modes, invalidation caveats, distributed environment limitations.

Doctrine DBAL documentation:

- [D-dbal-transactions] [DBAL Transactions](https://www.doctrine-project.org/projects/doctrine-dbal/en/current/reference/transactions.html): `Connection` transaction API, `transactional()`, isolation levels, savepoint-based nesting, auto-commit, retryable transaction exceptions.

Doctrine ORM source, tag `3.6.7`:

- [S-em-fields] [`EntityManager.php` facade fields and construction](https://github.com/doctrine/orm/blob/3.6.7/src/EntityManager.php#L34-L151).
- [S-em-wrap] [`EntityManager#beginTransaction`, `wrapInTransaction`, `commit`, `rollback`](https://github.com/doctrine/orm/blob/3.6.7/src/EntityManager.php#L170-L213).
- [S-em-flush-find] [`EntityManager#flush`, `find`, identity-map lookup](https://github.com/doctrine/orm/blob/3.6.7/src/EntityManager.php#L253-L367).
- [S-em-clear-persist-remove-detach] [`EntityManager#clear`, `close`, `persist`, `remove`, `detach`](https://github.com/doctrine/orm/blob/3.6.7/src/EntityManager.php#L411-L480).
- [S-em-lock-requirements] [`EntityManager` lock requirement checks](https://github.com/doctrine/orm/blob/3.6.7/src/EntityManager.php#L592-L612).
- [S-em-interface-tx] [`EntityManagerInterface` transaction wrapper and close contract](https://github.com/doctrine/orm/blob/3.6.7/src/EntityManagerInterface.php#L59-L91) and [`close()` contract](https://github.com/doctrine/orm/blob/3.6.7/src/EntityManagerInterface.php#L165-L170).
- [S-uow-fields] [`UnitOfWork` responsibility, states, identity map, original data, schedules](https://github.com/doctrine/orm/blob/3.6.7/src/UnitOfWork.php#L78-L214).
- [S-uow-identity-map] [`UnitOfWork::$identityMap` storage](https://github.com/doctrine/orm/blob/3.6.7/src/UnitOfWork.php#L119-L148).
- [S-uow-commit] [`UnitOfWork#commit` transaction and rollback path](https://github.com/doctrine/orm/blob/3.6.7/src/UnitOfWork.php#L325-L475).
- [S-uow-add-identity] [`UnitOfWork#addToIdentityMap`](https://github.com/doctrine/orm/blob/3.6.7/src/UnitOfWork.php#L1536-L1567).
- [S-uow-register] [`UnitOfWork#registerManaged`](https://github.com/doctrine/orm/blob/3.6.7/src/UnitOfWork.php#L2956-L2972).
- [S-uow-try-get] [`UnitOfWork#tryGetById`](https://github.com/doctrine/orm/blob/3.6.7/src/UnitOfWork.php#L2851-L2866).
- [S-uow-clear] [`UnitOfWork#clear`](https://github.com/doctrine/orm/blob/3.6.7/src/UnitOfWork.php#L2281-L2309).
- [S-upgrade-merge] [`UPGRADE.md`: removed merge of detached entities](https://github.com/doctrine/orm/blob/3.6.7/UPGRADE.md#L836-L845).
- [S-upgrade-partial] [`UPGRADE.md`: removed partial flush/clear and deprecated old signatures](https://github.com/doctrine/orm/blob/3.6.7/UPGRADE.md#L846-L865) and [`clear($entityName)` / `flush($entity)` deprecations](https://github.com/doctrine/orm/blob/3.6.7/UPGRADE.md#L1895-L1910).

Doctrine DBAL source, tag `4.4.3`:

- [S-dbal-transactional] [`Connection#transactional`](https://github.com/doctrine/dbal/blob/4.4.3/src/Connection.php#L941-L980).
- [S-dbal-begin-commit-rollback] [`Connection#beginTransaction`, `commit`, `rollBack`](https://github.com/doctrine/dbal/blob/4.4.3/src/Connection.php#L1049-L1155).
- [S-dbal-savepoints] [`Connection` savepoint operations](https://github.com/doctrine/dbal/blob/4.4.3/src/Connection.php#L1165-L1214).
