---
date: 2026-07-09
topic: "Hibernate ORM Session and transaction management"
type: research
tags: [research, orm, hibernate, session, transaction, cache, parallax]
status: complete
---

# Hibernate ORM Session and Transaction Management

## Summary

Hibernate's `Session` is the main runtime interface between an application and
Hibernate and represents a persistence context: the set of managed entity
instances associated with a logical transaction. Its documented responsibilities
combine identity management, entity lifecycle transitions, first-level caching,
dirty checking, lazy loading, and write-behind flushing to the database.
([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html),
[User Guide, Persistence Context](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The first-level cache is the persistence context itself. It is scoped to a
`Session`, provides application-level repeatable reads, and is short-lived. The
optional second-level cache is tied to the `EntityManagerFactory`/`SessionFactory`
and query caching is separately optional and disabled by default. Hibernate's
first-level semantics do not require a process-wide cache or cross-session
coherence layer. ([User Guide, Caching lines 28465-28474](https://docs.hibernate.org/orm/7.2/userguide/html_single/),
[User Guide, Second-level cache lines 16644-16662](https://docs.hibernate.org/orm/7.2/userguide/html_single/),
[User Guide, Query cache lines 16793-16808](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Transactionally, Hibernate exposes a `Transaction` abstraction over JDBC
resource-local and JTA-backed environments. Flush, commit, rollback, and
exception behavior are part of the session lifecycle: a flush synchronizes
in-memory changes with the database, commit normally triggers flush depending on
flush mode, rollback does not restore Java object state, and after transaction
rollback the persistence context must be discarded. ([Transaction Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html),
[FlushMode Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/FlushMode.html),
[Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

## Session/persistence-context responsibilities

### Persistence context and lifecycle states

The Hibernate User Guide defines a persistence context as the context for
dealing with persistent data represented by `Session` or `EntityManager`.
Persistent data has states relative to both that context and the database:
`transient`, `managed`/`persistent`, `detached`, and `removed`.
([User Guide, Persistence Context lines 12233-12251](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The `Session` Javadocs describe the same model in Hibernate API terms. A session
offers create, read, and delete operations, and an entity instance is transient
when never persistent and not associated with the session, persistent when
currently associated, and detached when previously persistent but not currently
associated. `persist()` makes a transient instance persistent, `detach()` makes
a persistent instance detached, and `remove()` marks a persistent instance for
removal. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

`refresh()` reloads database state into a managed entity and discards in-memory
modifications for that entity. The User Guide notes this is useful when database
state changed after the entity was read or when database triggers initialized
properties. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html#refresh(java.lang.Object)),
[User Guide, Refresh lines 13510-13538](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Identity guarantee

Within a given open `Session`, Hibernate guarantees at most one persistent
instance for a persistent identity, where persistent identity is determined by
entity type and identifier value. Distinct sessions may represent the same
persistent identity with distinct Java object instances. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

The implementation shape matches that contract: `SessionImpl` owns a
`PersistenceContext`, and the source describes `StatefulPersistenceContext` as
the first-level cache associated with the session. `StatefulPersistenceContext`
stores loaded entity instances by `EntityKey` and by `EntityUniqueKey`.
([SessionImpl source lines 2505-2519](https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/internal/SessionImpl.java#L2505-L2519),
[StatefulPersistenceContext source lines 2381-2392 and 2444-2459](https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/engine/internal/StatefulPersistenceContext.java#L2381-L2459))

### Dirty checking and read-only state

Persistent instances are held in managed state by the persistence context. Any
change to a persistent instance is automatically detected and eventually flushed
to the database; Hibernate names this automatic change detection "dirty
checking". The Session Javadocs also document ways to avoid dirty checking for
specific entities: mark an entity read-only, set a session or query to load
read-only entities, or detach/evict the entity from the persistence context.
([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html),
[Session Javadocs, `setDefaultReadOnly`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html#setDefaultReadOnly(boolean)))

The User Guide says entity queries are useful when the fetched entities need to
be modified because they benefit from automatic dirty checking; for read-only
transactions, DTO projections reduce load on the persistence context because
DTOs do not need to be managed. ([User Guide, Fetching lines 28442-28447](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Write-behind and unit of work

Hibernate describes flushing as synchronizing persistence-context state with the
underlying database. The persistence context acts as a transactional write-behind
cache: changes are applied in memory first and are translated to `INSERT`,
`UPDATE`, or `DELETE` during flush. Grouping DML statements allows batching.
([User Guide, Flushing lines 14094-14099](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The `Session` Javadocs make the same point from the API side: SQL statements are
often not executed synchronously by `Session` methods, and a flush operation
eventually synchronizes in-memory state with database state by executing SQL
`insert`, `update`, and `delete` statements. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

The source-level implementation is centered on an `ActionQueue`. `SessionImpl`
raises events whose listeners place entity actions on the session's
`ActionQueue`; those actions execute when the session is flushed. The
`ActionQueue` source describes itself as holding DML operations queued as part of
transactional write-behind until flush forces execution against the database.
([SessionImpl source lines 2505-2519](https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/internal/SessionImpl.java#L2505-L2519),
[ActionQueue source lines 2336-2345](https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/engine/spi/ActionQueue.java#L2336-L2345))

Flush order is not simply the order in which application code called state
transition methods. The User Guide says the order is given by `ActionQueue`, and
lists orphan removal, entity insert, entity update, collection operations, and
entity delete ordering. ([User Guide, Flush operation order lines 14340-14391](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Proxy and lazy loading

Instances returned by `get()`, `find()`, or a query are persistent. A persistent
instance may hold references to other entities, and unfetched associated
entities may be represented by uninitialized proxies. Hibernate fetches proxy
state when a proxy method is invoked only if the proxy is associated with an
open session. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

The User Guide describes `getReference()` as obtaining an entity reference
without initializing its data, generally using runtime proxies, and notes that
an exception is thrown later if the referenced database row does not exist when
application access requires proxy data. ([User Guide, Obtain an entity reference lines 12402-12418](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The User Guide's performance section states that `LAZY` associations must be
initialized before access; otherwise Hibernate throws `LazyInitializationException`.
It says required associations should be fetched before closing the persistence
context, using join fetches or secondary queries depending on association shape.
([User Guide, Fetching lines 28450-28464](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Detach and merge

Detachment means working with data outside any persistence-context scope. Data
becomes detached when the persistence context closes, when the context is
cleared, when a particular entity is evicted/detached, or when data is
serialized and deserialized. Detached data may still be manipulated, but
Hibernate no longer automatically detects those modifications without
application intervention. ([User Guide, Working with detached data lines 13565-13567](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

`merge()` copies state from a transient or detached instance to a persistent
instance. The `merge()` Javadocs specify that if no persistent instance is
currently associated with the session, Hibernate loads one; if the argument is
unsaved, Hibernate saves a copy; and the given detached instance does not itself
become associated with the session. ([Session Javadocs, `merge`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html#merge(T)),
[User Guide, Merging detached data lines 13568-13596](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

## Transaction semantics

### Session scope and transaction scope

Hibernate documents the lifecycle of a `Session` as bounded by the beginning and
end of a logical transaction, while allowing a long logical transaction to span
several database transactions. A session itself is a coarser-grained
conversation with the datastore than a physical database transaction.
([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html),
[Transaction Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html))

Hibernate also documents conversation patterns where a single user-visible unit
of work spans multiple database transactions. In a session-per-conversation
pattern, the `Session` may be disconnected after one database transaction and
reconnected later, and it is not allowed to flush automatically, only
explicitly. ([User Guide, Conversations lines 14854-14873](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Resource-local and JTA integration

The `Transaction` Javadocs define a resource-local transaction as any
transaction under Hibernate's control; the underlying transaction may be JTA or
JDBC depending on Hibernate configuration. Each resource-local transaction is
associated with a `Session`, starts with `beginTransaction()` or
`session.getTransaction().begin()`, and ends with `commit()` or `rollback()`.
([Transaction Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html))

The User Guide says transaction coordination is selected by
`hibernate.transaction.coordinator_class`: `jdbc` manages transactions through
`java.sql.Connection`, and `jta` manages transactions through JTA. If a Jakarta
Persistence application does not set this explicitly, Hibernate chooses based on
the persistence-unit transaction type; for non-Jakarta Persistence applications,
`jdbc` is the default and JTA use must be configured explicitly. ([User Guide, Transactions lines 14605-14616](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The User Guide describes Hibernate's `Transaction` API as an abstraction that
isolates applications from the physical transaction system. It exposes `begin`,
`commit`, `rollback`, rollback-only marking, timeout methods, synchronization
registration, and status, and it keeps synchronizations locally in both JDBC and
JTA environments while registering one synchronization with the JTA
`TransactionManager` in JTA mode. ([User Guide, Transaction API lines 14663-14678](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Flush modes and commit behavior

Hibernate's `FlushMode` enum defines when flush occurs. `AUTO` flushes on
transaction commit and sometimes before query execution so queries do not return
stale state; this is the default. `COMMIT` flushes when the transaction is about
to commit and is not automatically flushed before query execution according to
the Javadocs. `ALWAYS` flushes before every query and at commit. `MANUAL` only
flushes when `Session.flush()` is called explicitly. ([FlushMode Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/FlushMode.html))

The User Guide describes the same modes with one caveat for `COMMIT`: the
session tries to delay flush until the current transaction commits, although it
may flush prematurely. It documents `AUTO` flush triggers before transaction
commit, before overlapping JPQL/HQL queries, and before native SQL queries that
have no registered synchronization. ([User Guide, Flushing lines 14094-14124](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

With `MANUAL` flush mode, Hibernate does not execute pending DML unless
application code calls `flush()`; the User Guide shows an insert not executing
because there was no manual flush call, and says `MANUAL` is useful for
multi-request logical transactions where only the final request should flush.
([User Guide, Manual flush lines 14314-14339](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Rollback and exception behavior

Rollback does not roll back Java object state. The `Transaction` Javadocs state
that when a transaction rolls back, Hibernate makes no attempt to restore the
state of entity instances in memory to their state at the beginning of the
transaction; after rollback the persistence context must be discarded and entity
state assumed inconsistent with the database. ([Transaction Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html))

The `Session` Javadocs give operational restrictions: if `Session` throws an
exception, the current transaction must be rolled back and the session discarded;
at the end of a logical transaction the session must be closed to release JDBC
resources; if a transaction rolls back, the persistence-context and entity state
must be assumed inconsistent with the database; and a `Session` is never
thread-safe. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

The User Guide's session-per-application anti-pattern repeats the same failure
mode: an exception means rollback and immediate session close, and rolling back
the database transaction does not restore business objects to their start-of-
transaction state. ([User Guide, Session-per-application anti-pattern lines 14874-14878](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Nested transactions and savepoints

The Hibernate 7.2 `Session` and `Transaction` Javadocs reviewed here do not
document a Hibernate-level nested transaction or savepoint API. The public
`Transaction` surface documents a single transaction associated with a session,
normal `begin`/`commit`/`rollback`, rollback-only marking, timeout methods,
synchronization callbacks, and status helpers. It also states that at most one
uncommitted transaction is associated with a given `Session` at any time.
([Transaction Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html))

`Session` can execute JDBC work using its JDBC connection and transaction, so an
application may be able to reach lower-level JDBC mechanisms through `doWork()`,
but savepoint semantics are not presented as part of the documented Hibernate
`Session`/`Transaction` contract in the sources reviewed. ([Session Javadocs, JDBC work](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html#doWork(org.hibernate.jdbc.Work)))

## Cache/identity semantics

### First-level cache

Hibernate's first-level cache is the persistence context. The User Guide states
that it provides application-level repeatable reads; it is short-lived and is
cleared when the underlying `EntityManager` closes. ([User Guide, Caching lines 28465-28474](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The first-level cache is not a standalone process-wide caching solution. The
User Guide explicitly says it is not a caching solution "per se" and is more
useful for `READ COMMITTED` isolation support, while the transaction chapter says
Hibernate does not add locking behavior, does not lock objects in memory, and
does not change the database isolation behavior. ([User Guide, Caching lines 28465-28474](https://docs.hibernate.org/orm/7.2/userguide/html_single/),
[User Guide, Transactions lines 14618-14623](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Within a session, lookup by identifier returns the existing associated instance
if present. The `find()` Javadocs state that if the instance is already
associated with the session, that instance is returned. The broader `Session`
Javadocs guarantee one persistent instance per persistent identity per session.
([Session Javadocs, `find`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html#find(java.lang.Class,java.lang.Object)),
[Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

Because distinct sessions may contain distinct instances with the same
persistent identity, the first-level cache does not imply global object identity
or coherence across sessions. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

### Second-level cache

Hibernate's second-level cache is optional and separate from first-level session
semantics. The User Guide says the second-level cache is tied to an
`EntityManagerFactory`, unlike the short-lived first-level cache, and some
providers support clusters. It also says second-level cache entries store
normalized dehydrated entity entries rather than entity aggregates. ([User Guide, Caching lines 28465-28474](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Entity second-level caching is not the default mapping behavior. The User Guide
states that by default entities are not part of the second-level cache and, with
`ENABLE_SELECTIVE`, entities are not cached unless explicitly marked cacheable.
It also provides a `NONE` shared-cache mode that disables entity caching even for
cacheable entities. ([User Guide, Second-level cache mappings lines 16644-16662](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Second-level cache concurrency strategies have weaker or stronger consistency
semantics depending on configuration. The User Guide lists read-only,
read-write, nonstrict-read-write, and transactional strategies, and states that
nonstrict-read-write may allow occasional stale reads while transactional
provides serializable transaction isolation level. ([User Guide, Second-level cache mappings lines 16664-16678](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

### Query cache

The query cache is also optional and separate. Hibernate offers a query cache
for frequently executed queries with fixed parameter values, but the User Guide
states that query result caching adds overhead because Hibernate must track when
results should be invalidated, and that query result caching is disabled by
default because most applications do not benefit from it. After enabling the
query cache globally, each query must still be marked cacheable. ([User Guide, Query cache lines 16793-16808](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Query cache regions include a query-results region and an update-timestamps
region holding timestamps of recent updates to queryable tables; those
timestamps validate cached query results when served. ([User Guide, Query cache regions lines 16828-16840](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Query cache layout is configurable. The User Guide says query cache contents for
entities and collections may store full fetched data or just identifiers/owner
keys, and shallow layouts depend on entity/collection second-level cache hit
rates. ([User Guide, Query cache layout lines 16891-16899](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

## Failure modes and lifecycle edge cases

`Session` is short-lived and not thread-safe. The `Session` Javadocs state that
a persistence context holds hard references to all its entities, preventing
garbage collection, so a session must be discarded as soon as a logical
transaction ends; `clear()` and `detach()` can control memory in extreme cases,
and `StatelessSession` is suggested for processes reading many entities.
([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

Exception handling is fail-closed for a session. If the session throws an
exception, the transaction must be rolled back and the session discarded because
the session's internal state cannot be expected to remain consistent with the
database. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

Rollback does not repair in-memory entity graphs. After rollback, entity state
and persistence-context state must be assumed inconsistent with database state.
([Transaction Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html),
[Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

Lazy access can fail outside an open persistence context. Hibernate fetches
uninitialized proxy state only while the proxy is associated with an open
session, and the User Guide documents `LazyInitializationException` when lazy
associations are accessed before being initialized and after the context is no
longer available. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html),
[User Guide, Fetching lines 28461-28464](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Merge has duplicate-representation edge cases. The User Guide documents that
Hibernate throws `IllegalStateException` by default when merge detects multiple
detached representations of the same persistent entity, controlled by
`hibernate.event.merge.entity_copy_observer`. ([User Guide, Merging gotchas lines 13597-13615](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Refresh has transient-child edge cases. The User Guide documents that cascading
refresh to a transient child can throw `EntityNotFoundException` because
Hibernate cannot locate the transient child in the database. ([User Guide, Refresh gotchas lines 13539-13564](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

Long-lived sessions increase memory pressure because the persistence context
keeps hard references, and session-per-application is an anti-pattern because
`Session`/`EntityManager` are not thread-safe and shared sessions introduce race
conditions and visibility issues. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html),
[User Guide, Session-per-application anti-pattern lines 14874-14878](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

## Implications for Parallax session-cache slice

A Parallax slice that supports session caching but intentionally has no
process-wide cache can still match Hibernate's first-level-cache prior art. In
Hibernate, first-level identity and repeatable-read behavior are scoped to a
session/persistence context, not to a process-wide registry. The session-level
identity rule is "at most one persistent instance with a given persistent
identity associated with a given session"; distinct sessions may use distinct
instances for the same row. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html),
[User Guide, Caching lines 28465-28474](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The Parallax slice can model a session cache as an identity map plus managed
entity registry scoped to one unit of work or logical session. That follows the
Hibernate implementation shape where `SessionImpl` owns a `PersistenceContext`
and `StatefulPersistenceContext` stores loaded entities by identity keys.
([SessionImpl source lines 2505-2519](https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/internal/SessionImpl.java#L2505-L2519),
[StatefulPersistenceContext source lines 2444-2459](https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/engine/internal/StatefulPersistenceContext.java#L2444-L2459))

No process-wide cache means the slice does not need second-level cache regions,
query cache regions, timestamp invalidation, cluster behavior, or cross-session
coherence protocols. Hibernate treats those as optional layers separate from
first-level session semantics: second-level entity caching is not default for
entities, query caching is disabled by default, and query cache validation uses
separate timestamp regions. ([User Guide, Second-level cache mappings lines 16644-16662](https://docs.hibernate.org/orm/7.2/userguide/html_single/),
[User Guide, Query cache lines 16793-16808](https://docs.hibernate.org/orm/7.2/userguide/html_single/),
[User Guide, Query cache regions lines 16828-16840](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

The session-cache slice should keep transaction rollback semantics separate
from object-state repair. Hibernate does not restore in-memory entity state on
rollback and requires discarding the persistence context afterward. Therefore,
session-cache lifecycle rules need explicit invalid/discard behavior after
rollback or session-level exceptions, rather than hidden object graph rewind.
([Transaction Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html),
[Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html))

Flush and dirty-check semantics are separable from session identity caching.
Hibernate's first-level cache holds identity and managed state, while write-
behind execution happens at flush through queued actions. A narrow Parallax
session-cache slice can define identity/managed-instance behavior first and add
write-behind ordering, dirty checking, and flush modes as separate capabilities
if the slice boundary requires them. ([User Guide, Flushing lines 14094-14124](https://docs.hibernate.org/orm/7.2/userguide/html_single/),
[ActionQueue source lines 2336-2345](https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/engine/spi/ActionQueue.java#L2336-L2345))

Lazy/proxy semantics require an open-session association. If Parallax includes
lazy references in the slice, Hibernate prior art ties lazy initialization to an
active persistence context and treats access after detachment/close as a
lifecycle error rather than a cache miss against a global cache. ([Session Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html),
[User Guide, Fetching lines 28461-28464](https://docs.hibernate.org/orm/7.2/userguide/html_single/))

## Source map

- Hibernate ORM 7.2 `Session` Javadocs:
  <https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html>
- Hibernate ORM 7.2 `Transaction` Javadocs:
  <https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Transaction.html>
- Hibernate ORM 7.2 `FlushMode` Javadocs:
  <https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/FlushMode.html>
- Hibernate ORM 7.2 User Guide:
  <https://docs.hibernate.org/orm/7.2/userguide/html_single/>
- Hibernate ORM GitHub repository:
  <https://github.com/hibernate/hibernate-orm>
- `SessionImpl` source, first-level cache and write-behind implementation note:
  <https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/internal/SessionImpl.java#L2505-L2519>
- `StatefulPersistenceContext` source, stateful persistence context and identity
  maps:
  <https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/engine/internal/StatefulPersistenceContext.java#L2381-L2459>
- `ActionQueue` source, queued DML and transactional write-behind:
  <https://github.com/hibernate/hibernate-orm/blob/main/hibernate-core/src/main/java/org/hibernate/engine/spi/ActionQueue.java#L2336-L2345>
