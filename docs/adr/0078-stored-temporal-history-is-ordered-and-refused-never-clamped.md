# Stored temporal history is ordered, and a write that would break it is refused

This refines ADR 0010. One lazy Transaction Instant per attempt, from the Clock
Strategy, stays the only Transaction-Time source; what changes is that Parallax
no longer trusts that instant to follow stored history. Clocks repeat instants
and run behind one another, and an attempt can capture its instant at a forced
flush before another transaction commits a later version that the attempt then
reads and changes. Closing that version at the earlier instant stores an empty
or inverted interval, which reads then mistake for coverage.

Stored temporal history is ordered and non-overlapping per object, and Parallax
refuses a write that would break that rather than adjusting it. Clamping the
instant was rejected: an attempt has one instant, already written by any
earlier flush, so moving it for one row would break the attempt's coherence and
ADR 0010 itself. The refusal is a Temporal Conflict, retried as a new attempt
with a fresh instant and fresh reads, so ordinary retry rides out a briefly
lagging clock while a persistently lagging one surfaces once the bound is
exhausted.

The decision adopts three complementary layers of enforcement. Each becomes a
contract of its owning module when it ships; this record does not claim that a
layer is in force.

- A close of a row the attempt did not open must follow that row's stored
  Transaction-Time start. The comparison uses the predecessor expansion
  already holds, during planning or while binding inside the flush, and adds no
  read (`m-temporal-write` *A close follows its predecessor's start*;
  `m-unit-work` *Closes the instant cannot follow*; `m-auto-retry`).
- A caller-keyed new lineage is not to open before relevant closed history of
  its key ends, guarded inside the insert statement.
- PostgreSQL tables Parallax generates are to constrain interval validity and
  equal-key non-overlap natively, so that writers outside Parallax are refused
  too.

Ownership of rows the attempt opened stays the attempt's address record; equal
timestamps never establish it. Three alternatives were rejected beside
clamping. A database Clock Strategy would not order commits either, since
PostgreSQL's transaction and statement timestamps do not follow commit order.
Deleting rather than closing a row whose start equals the instant, as Reladomo
does, would silently erase another attempt's committed history. Optional native
enforcement would leave the invariant a deployment choice rather than a
guarantee. Reladomo's handling is recorded in
[processing time and temporal ordering](../research/reladomo/33-processing-time-and-temporal-ordering.md).
