---
date: 2026-07-09
topic: "SQLAlchemy ORM Session and transaction management"
type: research
tags: [research, prior-art, sqlalchemy, orm, session, transactions, cache]
status: complete
---

# SQLAlchemy ORM Session and Transaction Management

## Summary

SQLAlchemy's ORM `Session` is the application-facing boundary for a database
"conversation": it holds mapped objects associated with that conversation,
routes ORM queries, tracks object changes, and coordinates flush, commit,
rollback, expiration, and detachment. The official Session overview describes
the Session as the place where database conversations occur and as the holder of
loaded or associated objects; those objects are stored in an identity map that
keeps a unique in-memory object per primary-key identity inside that Session
([Session basics: What does the Session do?](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#what-does-the-session-do)).

The Session is also a transaction-coordination facade. It starts in a mostly
stateless form, checks out a connection from an `Engine` when work requires
database access, starts a transaction on that connection, and releases the
connection back to the pool when the transaction ends through commit or rollback
([Session basics: What does the Session do?](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#what-does-the-session-do)).
SQLAlchemy models this at the ORM level with a `SessionTransaction`, a virtual
transaction that can map to one or more real connection-level transactions as
needed ([Transactions and connection management](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)).

The Session is deliberately not a process-wide cache. It provides a
session-local identity map, but ordinary queries still issue SQL and only then
reuse an already-present object by primary key. The docs explicitly state that
the Session does not perform query caching, weakly references instances by
default, and is not designed as a global registry; second-level caching is an
extension/user-code pattern, illustrated by SQLAlchemy's dogpile caching example
([Session cache FAQ](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-a-cache),
[Dogpile caching example](https://docs.sqlalchemy.org/en/20/orm/examples.html#dogpile-caching)).

## Session Responsibilities

### Identity Map And Session Cache

The identity map is central to Session semantics. The docs define it as a data
structure that maintains unique copies of loaded ORM objects where "unique"
means one object with a particular primary key in that Session
([Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#what-does-the-session-do)).
When the same row is loaded twice in one Session, SQLAlchemy returns the same
Python object instance; by default, it does not repopulate attributes on an
already-loaded object unless asked to expire, refresh, or populate existing data
([Expiring / Refreshing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#expiring-refreshing)).

The implementation matches that contract: `Session.__init__` constructs
`self.identity_map = identity.WeakInstanceDict()`
([session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1755)),
`WeakInstanceDict.add()` rejects attaching a second live instance with the same
identity key
([identity.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/identity.py#L181-L205)),
and ORM loading checks the identity map before creating a new mapped instance
([loading.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/loading.py#L1068-L1124)).

`Session.get()` is the direct primary-key lookup API: it checks the current
identity map first, then queries the database for absent values
([Get by Primary Key](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#get-by-primary-key)).
The implementation-level helper `get_from_identity()` performs the same
identity-map lookup and handles expired state if an object is found
([loading.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/loading.py#L450-L472)).

### Unit Of Work And Change Tracking

The Session implements the unit-of-work pattern: mapped objects are
instrumented, attribute and collection changes are recorded, and pending changes
are flushed before ORM queries in autoflush contexts and before commit
([Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#what-does-the-session-do),
[Flushing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#flushing)).
`Session.add()` moves transient instances into pending state so that an INSERT
occurs on the next flush; persistent instances already loaded by the Session do
not need to be added; detached instances may be re-associated
([Adding New or Existing Items](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#adding-new-or-existing-items)).
`Session.delete()` marks an instance for deletion; before flush it appears in
`Session.deleted`, and after the DELETE it is expunged from the Session, becoming
permanent on commit
([Deleting](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#deleting)).

The Session exposes working sets for unit-of-work state: `Session.new` for
pending objects, `Session.dirty` for changed persistent objects,
`Session.deleted` for deletion-marked objects, and `Session.identity_map` for
persistent objects keyed by identity
([State Management: Session Attributes](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#session-attributes)).

### Object State And Lifecycle

SQLAlchemy documents five primary ORM object states. `transient` objects are not
in a Session and have no database identity; `pending` objects were added but not
flushed; `persistent` objects are in the Session and correspond to a database
row; `deleted` objects were deleted within a flush but the transaction has not
completed; `detached` objects have or had a database identity but are not
currently associated with a Session
([Quickie Intro to Object States](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#quickie-intro-to-object-states)).
Detached objects can be used for already-loaded attributes, but cannot load
unloaded or expired attributes because they no longer have a Session
([Quickie Intro to Object States](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#quickie-intro-to-object-states)).

The state of a mapped object can be inspected with `inspect(instance)`, which
returns an `InstanceState` exposing state flags such as `transient`, `pending`,
`persistent`, `deleted`, and `detached`
([Getting the Current State of an Object](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#getting-the-current-state-of-an-object)).

### Query Integration

In SQLAlchemy 2.0 style, the primary ORM query path is `select()` executed by
`Session.execute()` or `Session.scalars()`, with result shapes such as
`Result` and `ScalarResult`
([Querying](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#querying)).
Queries and flush are coupled: with default autoflush, a flush occurs before ORM
SQL-executing methods such as `Session.execute()` and before commit; a flush
also occurs before `Session.begin_nested()` establishes a SAVEPOINT
([Flushing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#flushing)).

The identity map is integrated with query materialization, not with query
memoization. The loader builds a row identity key, asks the Session identity map
for that identity, and either reuses the existing instance or creates and
attaches a new one
([loading.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/loading.py#L1079-L1124)).

### Expiration, Detachment, And Merge

Commit expires all objects in the Session by default so their state will be
loaded again on next access; this can be disabled with `expire_on_commit=False`
([Committing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#committing)).
`Session.expire()` erases selected or all ORM-mapped attributes so access can
lazy-load current database state, while `Session.refresh()` immediately emits a
SELECT to refresh object state
([Expiring / Refreshing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#expiring-refreshing),
[Refreshing / Expiring](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#refreshing-expiring)).
Both `expire()` and `refresh()` discard unflushed changes on affected objects
([Refreshing / Expiring](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#refreshing-expiring)).

`Session.merge()` copies state from a source instance into a corresponding
instance in the target Session. It examines the primary-key attributes, tries to
find the same identity locally, loads it from the database if absent, creates a
new target if necessary, copies source attributes to the target, returns the
target, and leaves the source instance unmodified and unassociated unless it was
already associated
([Merging](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#merging),
[session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L3891-L3923)).
The `load=False` merge mode is intended for clean objects from sources such as a
second-level cache or another worker's Session and avoids database access and
history events, subject to the clean-object caveat documented in the method
docstring
([session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L3917-L3938)).

## Transaction Semantics

### Session Scope Versus Transaction Scope

SQLAlchemy separates Session scope from transaction scope. A Session is
typically constructed for a logical operation; when it first communicates with
the database, it begins a database transaction, which remains in progress until
commit, rollback, or close. The same Session may be reused across multiple
transactions, but only one at a time
([When do I construct a Session?](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it)).
The docs frame Session and transaction lifecycle as external to data-specific
functions so transactional scope is predictable
([When do I construct a Session?](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it)).

The Session and Connection APIs have parallel transaction patterns:
"commit as you go", begin-once context managers, and nested transactions
([Session-level vs. Engine level transaction control](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#session-level-vs-engine-level-transaction-control)).
`sessionmaker.begin()` creates a Session and frames a begin/commit/rollback
block that commits and closes automatically when the context exits successfully
([Session-level vs. Engine level transaction control](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#session-level-vs-engine-level-transaction-control)).

### Autobegin And Explicit Begin

The Session has "autobegin" behavior: as soon as work begins, it ensures a
`SessionTransaction` is present to track ongoing operations, and `commit()`
completes that transaction
([Explicit Begin](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#explicit-begin)).
The Session basics page lists operations that trigger autobegin, including
`Session.add()`, `Session.execute()`, query execution, and modifying a
persistent object's attribute
([Auto Begin](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#auto-begin)).

Applications can call `Session.begin()` explicitly to control exactly where the
transactional state starts; it can also be used as a context manager
([Explicit Begin](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#explicit-begin)).
The implementation records whether a `SessionTransaction` originated from
explicit begin or autobegin, and raises if autobegin is disabled and work starts
without an explicit `begin()`
([session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1877-L1895)).

### Commit, Rollback, And Close

`Session.commit()` first flushes pending changes unconditionally, then commits
the actual database transaction on each connection in play, releases checked-out
connections back to their pools, and expires all objects by default
([Committing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#committing)).
If no transaction is present, `commit()` still runs a logical transaction for
events and expiration rules, but normally does not affect the database unless
pending flush changes exist
([Committing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#committing)).
For multiple bound engines, normal commits are not coordinated across engines
unless two-phase features are enabled
([Committing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#committing),
[Enabling Two-Phase Commit](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#enabling-two-phase-commit)).
The implementation commits each connection transaction whose `should_commit`
flag is true, marks the transaction committed, removes its snapshot, and closes
the transaction object
([session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1313-L1334)).

`Session.rollback()` rolls back the current transaction if one exists and is a
no-op if none exists. After rollback, database transactions are rolled back,
connections are released, pending objects added within the transaction are
expunged, deleted objects are promoted back to persistent state, and all
non-expunged objects are expired regardless of `expire_on_commit`
([Rolling Back](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#rolling-back)).
The implementation rolls back active/prepared connection transactions, restores
the transaction snapshot, closes the transaction object, and dispatches rollback
events
([session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1344-L1403)).

`Session.close()` expunges all ORM objects, ends any transaction in progress,
and releases checked-out connections. By default, close resets the Session to a
reusable clean state rather than making it permanently unusable
([Closing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#closing),
[session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L2490-L2528)).

### Nested Transactions And Savepoints

`Session.begin_nested()` begins a nested transaction using a database SAVEPOINT
and returns a `SessionTransaction` used as a context manager or explicit
savepoint handle
([Using SAVEPOINT](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint),
[session.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1952-L1964)).
SQLAlchemy 2.0 requires committing or rolling back the SAVEPOINT through the
nested transaction object; calling `Session.commit()` always commits the
outermost transaction
([Nested Transaction](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#nested-transaction)).

Before starting a nested transaction, SQLAlchemy flushes all currently pending
state unconditionally, regardless of `autoflush`
([Using SAVEPOINT](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint)).
On SAVEPOINT rollback, in-memory state modified since the savepoint is expired
while unaffected state can remain available, allowing the outer transaction to
continue
([Using SAVEPOINT](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint)).

### Connection And Resource Lifecycle

The Session requests connection resources from bound `Engine` objects when work
requires them, starts transactions on those connections, and releases them to
the pool after commit or rollback
([Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#what-does-the-session-do)).
`Session.connection()` can be used at the start of a transaction to procure a
connection and set per-transaction execution options such as isolation level;
when the transaction completes, the isolation level is reset before the
connection returns to the pool
([Setting Isolation for Individual Transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#setting-isolation-for-individual-transactions)).

A Session can also be bound to an externally managed `Connection` that already
has a transaction, commonly in tests. With `join_transaction_mode="create_savepoint"`,
Session-level begin/commit/rollback operations are implemented with SAVEPOINTs
so the external transaction can be rolled back after the test
([Joining a Session into an External Transaction](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)).

## Cache And Identity Semantics

SQLAlchemy's cache guarantee is identity interning within one Session, not query
memoization. The docs state that the Session is "somewhat" a cache because of
the identity map, but ordinary filtered selects still issue SQL even if a
matching object is already present; after rows return, SQLAlchemy uses primary
keys to find existing local objects
([Session cache FAQ](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-a-cache)).
Only primary-key lookup through `Session.get()` is documented as first checking
the identity map before querying
([Get by Primary Key](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#get-by-primary-key)).

The Session uses weak references for persistent object instances by default, so
objects can fall out of the Session when no external strong references remain.
The documented exceptions are pending objects, deleted objects, and persistent
objects with pending changes; after a full flush those collections are empty and
objects are again weakly referenced
([Session Referencing Behavior](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#session-referencing-behavior)).
`WeakInstanceDict` stores `InstanceState` entries and returns an object only if
the state's weakly referenced object is still present
([identity.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/identity.py#L126-L146),
[identity.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/identity.py#L219-L233)).

SQLAlchemy does not promise process-wide coherence. The docs describe loaded
objects as local proxies to rows in the transaction held by the Session and say
the identity-map design assumes a perfectly isolated transaction; if the
transaction is not isolated enough, the application refreshes objects as needed
([Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#what-does-the-session-do),
[Expiring / Refreshing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#expiring-refreshing)).
The Session FAQ says the Session is not a global object registry and points to
second-level caching as a separate pattern
([Session cache FAQ](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-a-cache)).
The official dogpile example demonstrates second-level/query-result caching by
using `SessionEvents.do_orm_execute()` and custom options to bypass normal
`Session.execute()` and pull from a user-managed cache source
([Dogpile caching example](https://docs.sqlalchemy.org/en/20/orm/examples.html#dogpile-caching)).

The concurrency model reinforces this boundary: a Session is a mutable,
stateful object representing a single logical database transaction and is not
safe to share across concurrent threads or asyncio tasks without synchronization.
The documented model is one Session per thread and one `AsyncSession` per task
([Is the Session thread-safe?](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks)).

## Failure Modes And Lifecycle Edge Cases

Flush failure is a special lifecycle edge. If `Session.flush()` fails, SQLAlchemy
rolls back the database transaction automatically, but the Session enters an
inactive state; the application must still call `Session.rollback()` explicitly
or close/discard the Session before normal use resumes
([Rolling Back](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#rolling-back)).

Rollback has object-state effects that matter to a session cache: pending
objects added in the transaction are expunged, deleted objects return to
persistent state, and remaining objects are expired
([Rolling Back](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#rolling-back)).
Close also affects object reachability: it expunges all ORM objects from the
Session and releases resources, leaving the Session reusable by default
([Closing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#closing)).

Expiration and refresh can discard unflushed changes. The state-management docs
show that calling `Session.expire()` before flushing a changed attribute
discards the pending value and reloads the database value on access
([Refreshing / Expiring](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#refreshing-expiring)).
The same page warns not to mutate ORM-managed `__dict__` entries directly
because SQLAlchemy's descriptors are what track changes
([Refreshing / Expiring](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#refreshing-expiring)).

Detached objects are another edge: commit expires objects by default, and
expired detached objects cannot reload attributes until they are associated with
a Session again; disabling `expire_on_commit` is the documented escape hatch
when post-commit access should not emit refresh SQL
([Opening and Closing a Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#opening-and-closing-a-session),
[Committing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#committing)).
`Session.merge()` is the documented mechanism for reconciling detached object
state into another Session's identity map
([Merging](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#merging)).

Nested transactions have a distinct failure boundary. `begin_nested()` first
flushes pending state, then SAVEPOINT rollback expires only state modified since
the savepoint while preserving unaffected object state for continued outer
transaction use
([Using SAVEPOINT](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint)).

## Implications For Parallax Session-Cache Slice

For a Parallax slice that supports session caching but intentionally excludes
process-wide cache and coherence concerns, SQLAlchemy's prior art separates the
minimal useful guarantee from global caching: a Session-local identity map can
provide one managed object per entity/primary-key identity without promising
query-result reuse, cross-session object identity, or process-wide invalidation
([Session cache FAQ](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-a-cache)).

The slice can treat ordinary queries as database reads that hydrate through the
identity map rather than as cacheable query expressions. SQLAlchemy's loader path
does exactly this: it computes an identity key from each returned row, reuses an
object if the key is already present, and otherwise creates and attaches a new
instance
([loading.py](https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/loading.py#L1079-L1124)).
Only an explicit primary-key lookup needs the stronger "check identity map
before SQL" behavior analogous to `Session.get()`
([Get by Primary Key](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#get-by-primary-key)).

The cache boundary should align with session and transaction lifecycle rather
than process lifetime. SQLAlchemy's commit expires objects by default, rollback
expunges pending objects and expires surviving objects, and close expunges all
objects and releases resources
([Committing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#committing),
[Rolling Back](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#rolling-back),
[Closing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#closing)).
Those lifecycle transitions are the important observable points for a Parallax
session-cache slice, even if Parallax chooses different defaults for expiration.

SQLAlchemy also shows that weak/strong retention is an explicit policy choice,
not inherent to the identity-map contract. SQLAlchemy weakly references clean
persistent objects by default and documents how applications can add strong
references per Session
([Session Referencing Behavior](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#session-referencing-behavior)).
Parallax can specify session-local identity semantics independently from any
future second-level cache or memory-retention policy.

Staleness from other Sessions, other processes, or external writers is outside
the session-cache guarantee in SQLAlchemy. The documented tools are expiration,
refresh, and populate-existing behavior inside a Session; second-level cache
coherence is a separate extension/user-code concern
([Expiring / Refreshing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#expiring-refreshing),
[Dogpile caching example](https://docs.sqlalchemy.org/en/20/orm/examples.html#dogpile-caching)).
That boundary matches a Parallax slice that has no process-wide cache and no
coherence protocol.

Finally, SQLAlchemy ties one Session to one mutable logical transaction and says
the concurrent model is Session-per-thread or AsyncSession-per-task
([Is the Session thread-safe?](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks)).
A Parallax session-cache slice can avoid process-wide coherence by keeping
identity-map mutation and unit-of-work state inside one explicit session object
with a non-shared concurrency model.

## Source Map

- SQLAlchemy 2.0 Session basics:
  <https://docs.sqlalchemy.org/en/20/orm/session_basics.html>
  - Session role, identity map, connection checkout/release, unit of work:
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#what-does-the-session-do>
  - Context manager and commit/expiration caveat:
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#opening-and-closing-a-session>
  - Query integration:
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#querying>
  - Add/delete/flush/get/expire/refresh:
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#adding-new-or-existing-items>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#deleting>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#flushing>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#get-by-primary-key>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#expiring-refreshing>
  - Autobegin, commit, rollback, close:
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#auto-begin>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#committing>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#rolling-back>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#closing>
  - Cache FAQ and concurrency FAQ:
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-a-cache>,
    <https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks>
- SQLAlchemy 2.0 State Management:
  <https://docs.sqlalchemy.org/en/20/orm/session_state_management.html>
  - Object states:
    <https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#quickie-intro-to-object-states>
  - Session collections and identity map attribute:
    <https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#session-attributes>
  - Weak reference behavior:
    <https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#session-referencing-behavior>
  - Merge:
    <https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#merging>
  - Refresh/expire:
    <https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#refreshing-expiring>
- SQLAlchemy 2.0 Transactions and Connection Management:
  <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html>
  - SAVEPOINT / nested transactions:
    <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint>
  - Session-level and engine-level transaction control:
    <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#session-level-vs-engine-level-transaction-control>
  - Explicit begin:
    <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#explicit-begin>
  - Two-phase commit:
    <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#enabling-two-phase-commit>
  - Isolation per transaction:
    <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#setting-isolation-for-individual-transactions>
  - External transactions:
    <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites>
- SQLAlchemy ORM examples, Dogpile caching:
  <https://docs.sqlalchemy.org/en/20/orm/examples.html#dogpile-caching>
- SQLAlchemy GitHub source, commit
  `fb213ed536336a71759259a1ee15f021b1c7903c`:
  - `Session.__init__` identity map construction:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1755>
  - Autobegin implementation:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1877-L1895>
  - `begin_nested()` docstring:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1952-L1964>
  - Transaction commit/rollback internals:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L1313-L1403>
  - `Session.close()` docstring:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L2490-L2528>
  - `Session.merge()` docstring:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/session.py#L3891-L3938>
  - Weak identity map behavior:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/identity.py#L126-L146>,
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/identity.py#L181-L233>
  - Identity map lookup during loading:
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/loading.py#L450-L472>,
    <https://github.com/sqlalchemy/sqlalchemy/blob/fb213ed536336a71759259a1ee15f021b1c7903c/lib/sqlalchemy/orm/loading.py#L1068-L1124>
