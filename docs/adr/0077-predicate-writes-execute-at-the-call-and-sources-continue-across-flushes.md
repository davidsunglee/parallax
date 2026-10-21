# Predicate writes execute at the call and sources continue across flushes

A nonempty predicate-selected write executes at its call, inside a
`predicate-write` Flush that first runs what its unit of work buffered before
it, and the verb returns its statement's affected-row count (`m-batch-write`
*A predicate-selected write executes at its call*). This supersedes ADR 0043.
A predicate write no longer enters the buffer, so it no longer partitions
buffered work: the regions it defined, and the compositions chained across
them, are gone. Removal-dependent insertion still starts a region of its own
(`m-unit-work` *Write Group formation*).

Running earlier writes at the call is affordable only if doing so leaves their
sources usable. A source therefore continues across its own successful writes
in any Flush (`m-unit-work` *Observation ownership and lifetime*). The
continuation is narrow: a caller-stated condition stays literal, so a stale
caller still fails as stated rather than being advanced through what the unit
of work wrote.

The count has one meaning on every dialect. PostgreSQL's native report already
counts unchanged matched rows; MariaDB's does only with `CLIENT_FOUND_ROWS`, the
flag that already decides what its temporal unchanged-milestone guards count,
so `m-dialect` *Unchanged-row count* requires it rather than let the public
result depend on the vendor.

The barrier carried a cost into every structure it touched. Its regions,
sealing, follower wrappers, and chained compositions existed only to keep
buffered work on its side of a write the planner could not see into, and
buffering hid both the statement's failure and its count until a later flush.
Executing at the call removes each of these. The accepted cost is batching: a
predicate write flushes the work buffered before it, so a buffer interleaved
with predicate writes reaches the database in more, smaller Flushes than one
barrier-partitioned plan would have used.

Four alternatives were rejected. Keeping the barrier while returning a count
would need a second deferred result, with no failure reported at the call.
Advancing caller-stated revisions through the unit of work's own writes would
turn a stale caller's mismatch into a silent success. Reporting the driver's
vendor-dependent count would give one public verb two meanings. Recovering the
count from lifecycle events or a separate ledger would make an observation
channel a result channel.
