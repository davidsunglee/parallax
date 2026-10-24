# The temporal model

A temporal Entity keeps its history as part of the model. Instead of overwriting a row,
a write closes the state it replaces and opens the state that follows, so you can later
ask what the database held at any instant, and, for a Bitemporal Entity, what was true
in the world at any date. This page explains the two time axes, the milestones that
record history along them, how reads choose milestones, and how a write composes over
the coverage it changes.

Each section names the specification that owns it. This page explains and links; when
it and a specification seem to disagree, the specification is right.

## Two axes

Parallax tracks time along two independent axes
([canonical terminology](../../core/spec/m-temporal-read.md#canonical-terminology)):

|  | Transaction Time | Valid Time |
| -- | -- | -- |
| What it records | when a fact was present in the database | when a fact is true in the modeled world |
| Who supplies the instant a write uses | the Database Root's clock, never the caller | the caller, as a write's `validFrom` and optional `until` |
| What it answers | "what did we have on record at T?" | "what was true on date V?" |
| Can its past change? | never: it is what the system knew | yes: a correction under current Transaction Time |

Every write in one transaction attempt that needs a Transaction-Time instant uses the
same one, captured the first time it is needed
([the Transaction Instant](../../core/spec/m-unit-work.md#the-transaction-instant)).

## Three profiles

Each Inheritance Family has one temporality profile, declared by its root:

| Profile | Axes | What the database keeps |
| -- | -- | -- |
| Non-Temporal | none | the current state only |
| Transaction-Time-Only | Transaction Time | every state the object held, and when it was on record |
| Bitemporal | Valid Time and Transaction Time | every state, when each was true in the world, and when it was on record |

A fourth combination, Valid Time without Transaction Time, is deferred
([`m-validtime-only`](../../core/spec/m-validtime-only.md)). The supported profiles all
include Transaction Time, which is also what makes a temporal Entity's optimistic
version: the Transaction-Time start of the milestone a read observed
([temporal versions](../../core/spec/m-opt-lock.md#temporal-entities-derive-the-version-from-transaction-time)).

## Milestones

A **milestone** is one stored state of one object. On each axis it covers a half-open
interval `[start, end)`
([interval model](../../core/spec/m-temporal-read.md#interval-and-metadata-model)). The
start and end are framework-owned members, `txStart` and `txEnd`, plus `validStart` and
`validEnd` on a Bitemporal Entity: you read them, and you never declare or assign them.

A milestone is **current** on an axis when its end is **infinity**. Infinity is a real
value rather than a missing one, so a current milestone compares and sorts like any
other ([temporal infinity](../../core/spec/m-core.md#temporal-infinity)). On a
Bitemporal Entity a milestone is a rectangle in Valid Time × Transaction Time, and an
object's **current coverage** is the set of its milestones that are current on
Transaction Time.

Milestones of one object never overlap on every axis at once
([non-overlap](../../core/spec/m-temporal-write.md#milestones-of-one-object-never-overlap)).
Overlap on one axis is normal:

```text
 Bitemporal object, Valid Time across, Transaction Time down

            Jan       Apr
 tx [T0,T1) ├──────── 100 ──────────────────────→      closed on Transaction Time
 tx [T1,∞)  ├── 100 ───┼──── 120 ───────────────→      current: two rectangles
```

The two current rectangles share a Transaction-Time interval and are adjacent on Valid
Time. Each overlaps the closed milestone on Valid Time and not on Transaction Time.

## Reading at a point, across history, and over a range

A read selects milestones on each axis its Entity has
([selections](../../core/spec/m-temporal-read.md#selections)):

- **As of an instant.** It returns the milestone whose interval contains the instant.
  Transaction Time defaults to **Latest**, the database's current knowledge, when a read
  does not say. Valid Time has no default on a Bitemporal Entity, because choosing one
  would be a claim about the world
  ([Latest and Now](../../core/spec/m-temporal-read.md#latest-and-now)).
- **History.** It returns every milestone along that axis.
- **A range.** It returns every milestone whose interval overlaps `[start, end)`.

The axes are chosen independently, so a Bitemporal read can ask "at Transaction Time T,
what was valid at V?". A read as of an instant stands at that instant: every value it
returns, and every related value it loads along a matching axis, sits at the same
coordinates. A history or
range read returns one value per milestone, each standing at its own milestone's start
([pinning and edges](../../core/spec/m-temporal-read.md#pinning-edges-and-relationships)).
[The read flow](read-flow.md) shows what such a read can and cannot license.

## How a write composes over coverage

A temporal write never edits a stored milestone in place. It closes the milestones it
changes at the Transaction Instant and opens their **successors** in the same statement
sequence ([`m-temporal-write`](../../core/spec/m-temporal-write.md)).

### Transaction-Time-Only: close and chain

An amendment closes the current row and chains a new current row with the new values.
A termination closes it and chains nothing, so the object has no current row
([milestone chaining](../../core/spec/m-temporal-write.md#transaction-time-only-milestone-chaining-writes)):

```text
 insert at T0         [T0, ∞)  credit 100
 amend to 150 at T1   [T0, T1) credit 100     closed: what was on record until T1
                      [T1, ∞)  credit 150     current
 terminate at T2      [T1, T2) credit 150     closed; no current row remains
```

### Bitemporal: the rectangle split

A Bitemporal write changes a Valid-Time window `[validFrom, until)`, or from
`validFrom` onward when `until` is omitted. The rectangle it reaches is closed on
Transaction Time, and the parts of it before and after the window reopen unchanged
around the changed middle
([the rectangle split](../../core/spec/m-temporal-write.md#the-rectangle-split),
[unbounded writes](../../core/spec/m-temporal-write.md#plain-unbounded-bitemporal-writes)):

```text
 stored        tx [T0,∞)  ├──────────────── price 10 ────────────────→
                          Jan                                        ∞

 amend [Jun, Sep) to 8 at T1:
               tx [T0,T1) ├──────────────── price 10 ────────────────→   closed
               tx [T1,∞)  ├─── 10 head ───┼─ 8 middle ─┼─ 10 tail ───→
                          Jan             Jun          Sep           ∞

 the other forms, at T1:
   amend from Jun         head [Jan, Jun) 10 │ changed [Jun, ∞) 8
   terminate [Jun, Sep)   head [Jan, Jun) 10 │ nothing in [Jun, Sep) │ tail [Sep, ∞) 10
   terminate from Jun     head [Jan, Jun) 10 │ nothing from Jun on
```

A head or tail that would cover no Valid Time is not opened, so a write starting exactly
where a rectangle starts opens no head.

### Coverage, predecessors and successors

A write's window can reach several rectangles, and gaps where no rectangle exists.
Parallax treats this uniformly
([temporal expansion](../../core/spec/m-temporal-write.md#temporal-expansion)):

- The object's composed writes form one
  [**Coverage Transform**](../../core/spec/m-temporal-write.md#coverage-transform): an
  ordered list of **Coverage Segments**, each a Valid-Time window that assigns members or
  destroys coverage. Where two writes' windows overlap, the later one wins member by
  member.
- Each existing milestone the transform reaches is a **predecessor**. Applying the
  transform to it yields its successors: parts outside every segment carried unchanged,
  parts inside a segment changed or destroyed
  ([predecessor expansion](../../core/spec/m-temporal-write.md#predecessor-expansion)).
- A **gap** stays a gap for an amendment or a termination. A replacement fills every gap
  in its window with its complete state, as a **Coverage Gap** that opens a new lineage.
- Adjacent produced rows with identical stored state open as one row
  ([merging](../../core/spec/m-temporal-write.md#merging-produced-successors)).

```text
 stored     P1 [Jan, Apr) 100 │ P2 [Apr, Jul) 200
 amend [Feb, Jun) assigning 150
 current    [Jan, Feb) 100 │ [Feb, Jun) 150 │ [Jun, Jul) 200
 history    P1 and P2 each closed, each under its own proof
```

A milestone the write leaves exactly as it was is **unchanged** and is kept rather than
closed and reopened in equal pieces, so its history gains nothing
([unchanged milestones](../../core/spec/m-temporal-write.md#unchanged-milestones)):

```text
 stored     [Jan, Apr) 100 │ gap │ [May, Aug) 180 │ [Aug, Dec) 100
 amend [Mar, Oct) assigning 100
 result     first and last rectangles kept as they were; only [May, Aug) is rewritten;
            the gap stays a gap
```

Under Optimistic, keeping a stored milestone unchanged still issues a guard that proves
nobody changed it since it was read. On a database that cannot report such a proof, the
milestone is closed and reopened as if it had changed.

### Rows the same transaction opened

A row this attempt opened is not yet anyone's history. A later write of the same attempt
revises or removes it in place instead of closing it, so the transaction leaves no empty
`[T, T)` milestones behind
([rows the attempt opened](../../core/spec/m-temporal-write.md#rectangles-the-attempt-opened)).
And writes of an object that is still only buffered compose before anything executes:
insert-then-amend opens one row with the final values
([same-transaction coalescing](../../core/spec/m-unit-work.md#same-transaction-write-coalescing)).

### Terminate, not delete

A temporal object is removed with `terminate`, which closes its current coverage over a
window and keeps every milestone. `delete` is refused for temporal Entities: physically
deleting history is not a write the required surface offers
([plain writes](../../core/spec/m-temporal-write.md#plain-unbounded-bitemporal-writes)).

## Why a past Transaction-Time view is read-only

The Transaction-Time past records what the system knew, and Parallax never rewrites it.
Every write reaches its new state by closing current milestones and opening successors,
never by editing or removing a milestone that is already closed
([the Transaction-Time past is never rewritten](../../core/spec/m-temporal-write.md#the-transaction-time-past-is-never-rewritten)).
That is also what makes a read of the past stable while others write.

So a value read as of a finite Transaction-Time instant is read-only, even inside a
read-write transaction: handing it to a write verb fails at the call, before anything is
buffered. Read the current state, at Transaction Time Latest, to change it. Valid Time is
different. A value read at a finite Valid-Time instant is writable, and the write is a
retroactive correction: it changes what is recorded as true at those dates, under current
Transaction Time, while the previous belief stays readable as history.

## Common use cases

- **Audit trail.** Make an Entity Transaction-Time-Only, then read it as of any past
  instant, or read its history, to see what was on record and when it changed.
- **Reproduce a past report.** Run the report's reads as of the instant it was produced.
- **Schedule a change.** On a Bitemporal Entity, amend from a future Valid-Time date; the
  current state stays as it is until then.
- **A temporary change.** Amend a bounded window with `until`, such as a seasonal price;
  the values before and after the window are unchanged.
- **Correct the past.** Read the Bitemporal value at the date that was wrong and amend it
  there. Reads at Transaction Time Latest see the correction; reads at an earlier
  Transaction-Time instant still see what was believed then.
- **End an object without losing it.** Terminate it; its history stays readable.

## Do it →

- [Choosing a temporality profile](../../languages/python/docs/guide/02-modeling.md#choosing-a-temporality-profile)
- [Transaction-Time-Only reads](../../languages/python/docs/guide/03-reading.md#transaction-time-only-reads)
- [Bitemporal reads](../../languages/python/docs/guide/03-reading.md#bitemporal-reads)
- [Transaction-Time-Only writes](../../languages/python/docs/guide/04-writing.md#transaction-time-only-entities)
- [Bitemporal writes](../../languages/python/docs/guide/04-writing.md#bitemporal-entities)
