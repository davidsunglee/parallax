# The read flow

A read in Parallax is one explicit execution. You hand it an Object Query; it runs a
bounded number of statements and gives back immutable values that never reach the
database again. This page follows a read through its stages, shows where whole-result
and streamed delivery share the work and where they part, and explains which reads
leave values that a later write can stand on.

Each stage names the specification that owns it. This page explains and links; when
it and a specification seem to disagree, the specification is right.

## The flow at a glance

```text
 Object Query                  what to read: target, predicate, ordering, limit,
      │                        temporal selection, includes
      ▼
 validation and resolution     adopt one Model Edition; resolve every name and
      │                        literal; refuse what cannot be answered, before any I/O
      ▼
 where the read runs           standalone, read-only transaction, or read-write
      │                        transaction: which connection, flush, shared lock
      ▼
 planning and SQL              one statement per non-empty relationship level;
      │                        storage layout, inheritance and locks resolved here
      ▼
 judged Page                   rows become identity claims and Entity States;
      │                        stored data that contradicts the model is diagnosed
      ▼
 publication and delivery      each result root becomes Typed or Wire values,
                               all at once (eager) or one root at a time (streamed)
```

## The stages

### Object Query

The request is an [Object Query](../../core/spec/m-object-query.md): one flat value
naming the target Entity, a Predicate, an optional narrowing to subtypes, a temporal
selection per axis, sort keys, a row limit and the Include Paths to load with each
result. Clause order carries no meaning, and the query names no result form and no
paging. The Typed and Wire interfaces spell it differently and produce the same value.

### Validation and resolution

The read first adopts one [Model Edition](../../core/spec/m-execution.md#model-editions)
and keeps it to the end; a stream keeps it for every page it reads. Next the
lifecycle prepares the [Publication](../../core/spec/m-read-delivery.md#publication) that
will turn results into values, which is where a representation the model cannot
produce is refused. Then the query is resolved against the adopted model: every name
becomes an exact identity and every literal a managed value, and a feature the
implementation does not yet offer is refused.

What comes out is a resolved query that nothing downstream interprets again
([planning boundary](../../core/spec/m-object-query.md#planning-boundary)). Every
refusal so far happens before a connection is acquired, SQL is generated or pending
writes are flushed, so a query that cannot be answered has no side effects
([reads under an Attempt or a scope](../../core/spec/m-execution.md#reads-under-an-attempt-or-a-scope)).

### Where the read runs

A read runs in one of three places. A standalone read goes through an Execution Scope
and opens no transaction. The other two run inside a Transaction Attempt, read-only or
read-write ([read-only transactions](../../core/spec/m-execution.md#read-only-transactions),
[`m-read-lock`](../../core/spec/m-read-lock.md)):

|  | standalone | read-only transaction | read-write transaction |
| -- | -- | -- | -- |
| Connection | its own lease; a stream leases one per page | the attempt's | the attempt's |
| Pending writes | none to see | none to see | flushed before the read |
| Shared row lock | never | never | where the Entity's effective strategy is Locking |
| Read Evidence on its values | none | none | on eligible values |

A standalone read made inside a transaction's callback stays standalone: it is never
redirected into the active attempt.

### Planning and SQL

[Deep fetch](../../core/spec/m-deep-fetch.md) plans the root query and one level for
each relationship hop the Include Paths name. Each non-empty level is one statement
over the keys the level above gathered, so a read issues at most `1 + L` statements for
`L` hops however many rows come back. [SQL generation](../../core/spec/m-sql.md)
lowers each level for the dialect, and this is where the Storage Layout, the
inheritance mapping and each level's read lock are resolved.

Planning is reusable: a [Database Root](../../core/spec/m-execution.md#database-root)
owns one read-plan cache that every read through its scopes plans through
([`m-read-delivery`](../../core/spec/m-read-delivery.md)).

### Judged Page

The statements' rows land in a [Page](../../core/spec/m-read-delivery.md#entity-state-and-the-page).
Each row makes an identity claim: its concrete Entity and its logical key, which is the
family, the primary key and the as-of coordinate on each axis. The rest of the row is
judged at most once per logical state, when publication first needs it. Stored data
that contradicts the model, such as a missing required member or an unknown subtype
tag, becomes a finding in one closed
[vocabulary](../../core/spec/m-read-delivery.md#invalid-stored-data); it is never
repaired or replaced by a default.

### Publication and delivery

Publication is the lifecycle's part of the read
([`m-snapshot-read`](../../core/spec/m-snapshot-read.md)). For each result root it forms
a [Root View](../../core/spec/m-snapshot-read.md#root-view) of what that root reaches,
checks those rows agree with each other, classifies the root, and builds its values:

- Within one root, one logical row is one object. Two Include Paths that reach the same
  row share it, and a back-reference makes a real cycle.
- Every temporal value in the graph stands at the query's own coordinates
  ([the whole-graph pin](../../core/spec/m-snapshot-read.md#the-whole-graph-pin)).
- A root whose stored data contradicts the model keeps its place in the result as
  invalid data, rather than disappearing or failing the read
  ([classified roots](../../core/spec/m-snapshot-read.md#classified-roots)).
- The graph is [closed](../../core/spec/m-snapshot-read.md#closed-world): following a
  relationship the read did not include finds it absent, and never runs a query.

## Eager and streamed delivery

Both deliveries run the same flow up to the Page. They differ in how many Pages they
read and when a root's values reach you
([streamed delivery](../../core/spec/m-read-delivery.md#streamed-delivery)):

```text
                       Object Query
                            │
            validation and resolution, once
                            │
             ┌──────────────┴───────────────┐
             ▼                              ▼
           eager                          stream
   one Page for the whole          bounded Pages in the Continuation
   result                          Order; each Page reads one root more
             │                     than it delivers, to know if more follow
             │                              │
             │                     every Page: the same planning, SQL
             │                     and Page assembly an eager read uses
             ▼                              ▼
   prepare every root, then        publish each root as soon as it is
   return them all together        ready; earlier roots stay delivered
                                   if a later one fails
```

Where they part:

- **Boundary.** An eager read publishes nothing until every root is prepared, so a
  failure publishes nothing. A stream publishes root by root, so a failure keeps the
  prefix already delivered
  ([whole-result delivery](../../core/spec/m-read-delivery.md#whole-result-delivery)).
- **Order.** A stream always delivers in the Continuation Order: your sort keys, then
  the primary key, then, for a milestone set, the milestone edge. An unordered limit is
  therefore a specified first `n` on a stream and an unspecified subset on an eager read
  ([where a stream diverges](../../core/spec/m-read-delivery.md#where-a-stream-diverges-from-a-whole-result-read)).
- **Resources.** What a stream holds does not grow with the number of matching roots: a
  page's converted rows and the current root's graph
  ([what a delivery costs](../../core/spec/m-read-delivery.md#what-a-delivery-costs)).
  A standalone stream holds a connection only while it reads a page
  ([the connection a delivery holds](../../core/spec/m-read-delivery.md#the-connection-a-delivery-holds)).
- **Concurrent writes.** Each page takes its own view of the data. Inside a
  transaction, the isolation level adds what it adds. If the query orders by a member a
  write can change, a concurrent write, including your own loop's, can make a root
  appear twice or not at all; the default primary-key order cannot
  ([stability under concurrent writing](../../core/spec/m-read-delivery.md#stability-under-concurrent-writing)).
- **Retries.** A transaction that retries runs its callback again, and a stream inside
  it starts again from the first root.

A read that scans an axis, such as a history or an as-of range, returns one root per
milestone. Eager or streamed, those roots arrive as one flat sequence in the
Continuation Order, each standing at its own milestone edge, and the result as a whole
stands at no single instant ([`m-temporal-read`](../../core/spec/m-temporal-read.md)).

## Typed and Wire share execution

Typed and Wire are [peer interfaces](../adr/0057-typed-and-wire-are-peer-interfaces-over-one-transaction.md)
over one execution. They hand the read the same Object Query value, and the read
validates, plans, executes, judges and classifies it in exactly the same way. Only the
last step differs: Typed publication builds instances of your Entity classes, and Wire
publication builds immutable mappings whose leaves use the one canonical spelling the
[Neutral Wire Codec](../../core/spec/m-wire.md) owns. Wire needs no classes, so it can
serve a model described only by data.

Because the shared work decides everything that matters, the same row read both ways
gets the same verdict and the same write evidence. Inside one transaction, Typed and
Wire reads and writes share the same Unit of Work, locks and flushes.

## Storage layout stays below the caller

An Entity can be stored in ordinary Columns or as one document per row, and
[nothing above the physical seam can tell which](../../core/spec/m-storage-layout.md#storage-layout-transparency).
The layout is resolved in one place in the read flow: planning and SQL generation
locate each logical member in a Column or at a document path, and Page conversion
reads it back from that same placement. Stored-data judgement uses the same logical
roots under either layout.

So the Object Query names logical members only, and the Page, the published values,
the order of results and the stored-data findings come out the same under either
layout. What differs is physical: the tables and Columns, the SQL text and the stored
documents.

## Who owns write evidence

Every published value records its publication provenance: which Entity it is, the
coordinates it was read at, and whether its root conformed. Only a read inside a
read-write Transaction Attempt also attaches
[Read Evidence](../../core/spec/m-unit-work.md#write-value-provenance): the facts a
later write of that value is checked against, such as the version or Transaction-Time
start the read saw, or the shared lock it took.

| The value came from | Read Evidence | Can it license a source write? |
| -- | -- | -- |
| a standalone read | none | no; state its revision in a target write instead |
| a read-only transaction | none | no; the same |
| a read-write transaction, reading one instant | on each value of a conforming root | yes, in the same attempt, while the evidence still holds |
| a history or as-of range read | none | no; every milestone is read-only |
| a read-write transaction, reading at a past Transaction-Time instant | does not matter | no; the Transaction-Time past is read-only |
| a root classified as invalid data | none, on any node reached only through it | no |

Read Evidence is not authority by itself. The write verb decides what it licenses: the
evidence must come from a read of the current attempt, and the Entity's effective
strategy then asks for the shared lock under Locking or the observed revision under
Optimistic ([current-attempt source admission](../../core/spec/m-unit-work.md#current-attempt-source-admission)).
A retried attempt re-runs its reads, so a value from an earlier attempt licenses
nothing in the next one. [The write flow](write-flow.md#admitted-write) follows the
write from there.

## Common use cases

- **Look something up once.** A standalone read is enough; no transaction is needed.
- **Show several reads that agree.** Run them in one read-only transaction at
  Repeatable Read, so they share one snapshot.
- **Read, then change what you read.** Read inside the read-write transaction that
  writes. The read flushes your pending writes first and leaves the evidence the write
  needs.
- **Write a value read earlier**, such as one shown in a form. State the revision it
  carries in a target write; the write fails rather than overwriting a newer change.
- **Process a large result.** Stream it. Keep the default order if the loop writes to
  the rows it reads.
- **Ask what was known, or what changed.** Read as of a past Transaction-Time instant,
  or read the history.
- **Serve data as JSON.** Read through Wire, inside the same transaction as Typed work
  if you need both.

## Do it →

- [Where a read runs](../../languages/python/docs/guide/03-reading.md#where-a-read-runs)
- [Predicates, ordering and limits](../../languages/python/docs/guide/03-reading.md#predicates-ordering-and-limits)
- [Loading a graph](../../languages/python/docs/guide/03-reading.md#loading-a-graph)
- [Result shapes](../../languages/python/docs/guide/03-reading.md#result-shapes)
- [Eager and streaming delivery](../../languages/python/docs/guide/03-reading.md#eager-and-streaming-delivery)
- [Transaction-Time-Only reads](../../languages/python/docs/guide/03-reading.md#transaction-time-only-reads)
- [Bitemporal reads](../../languages/python/docs/guide/03-reading.md#bitemporal-reads)
- [The Wire API](../../languages/python/docs/guide/03-reading.md#the-wire-api)

How the Python implementation builds this flow, type by type:
[Read flow architecture](../../languages/python/docs/architecture/read-flow.md).
