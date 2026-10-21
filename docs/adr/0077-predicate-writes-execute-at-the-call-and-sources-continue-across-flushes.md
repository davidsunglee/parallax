# Predicate writes execute at the call and sources continue across flushes

A nonempty predicate-selected write executes at its call. It runs inside one
`predicate-write` Flush, which first runs the writes its unit of work buffered
before it, and the verb returns the affected-row count its one statement
reported (`m-batch-write`). An empty amendment or a key-only replacement runs no
statement, opens no Flush, and returns `0`. Statement failures surface at the
call and doom the attempt; deferred constraints still fail at commit. This
supersedes ADR 0043. Since a predicate write never enters the buffer, nothing
partitions the buffer into regions: the planner orders, coalesces, and groups
what is buffered as one stream, and a predicate step is planned on its own.

Running earlier writes at the call is affordable only if doing so leaves their
sources usable. A source therefore continues across its own successful writes,
in any Flush. It authorizes the surviving state that those writes produced,
until a known destruction ends it (`m-unit-work`, `m-temporal-write`). The
continuation is narrow. The source's values and original evidence stay as
observed. A caller-addressed condition, a stated `version` or `tx_start`,
remains literal and never advances through what earlier writes of the unit of
work derived. A stale condition fails as its caller stated it. A row a
predicate write deleted was identified by nothing, so a later keyed write of it
fails its ordinary affected-row expectation rather than being refused as ended
evidence.

The count is the same everywhere: an update counts every row it matched,
unchanged ones included, and a delete counts the rows it deleted. That is
PostgreSQL's native report. MariaDB reports only changed rows unless a
connection sets `CLIENT_FOUND_ROWS`, so `m-dialect` requires that flag on every
MariaDB connection rather than let the public result depend on the vendor.
The same flag already decides which rows the temporal unchanged-milestone
guards count. Cascades and trigger side effects are never counted.

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
