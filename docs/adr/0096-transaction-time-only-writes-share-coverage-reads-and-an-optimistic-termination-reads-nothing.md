# Transaction-Time-Only writes share coverage reads, and an Optimistic termination reads nothing

A deferred settled write of a Transaction-Time-Only Entity now joins an
acquisition span under the rule a Bitemporal one already followed: same mutation
phase, Entity, key attribute, and shared-lock requirement, distinct objects,
consecutive, within the span bound (`m-unit-work` *Shared coverage
acquisition*). No condition names a verb or a temporal shape; span formation
asks only whether a write's coverage must be read. Its one uncovered part is its
current row, counted once against the per-read bound beside Valid-Time
intervals, covered by a row the unit already holds, and ready once every
statement naming it has succeeded (`m-sql` *Requested ranges*). Several such
parts are read by `m-sql`'s canonical key membership with the current
Transaction-Time selection, `= any(cast(? as T[]))` with array binding and
`in (?, …)` without, and one part keeps key equality.

Under Optimistic, a Transaction-Time-Only target write that needs no cell of its
current row beyond the key and Transaction-Time start its caller states binds
from that stated start at planning and reads nothing (`m-temporal-write` *A
target write*). Today that is a termination. Its close is gated on the stated
`ifTxStart`, groups with the Entity's other planned closes up to the Write
Group bound, and a missing ordinal raises that write's own Write Precondition
Error. The close-follows-start check compares the gate's start, the only stored
start whose row that close can change; where no row stands there, the check
decides only which failure comes first. The carve-out is phrased by the data a
write needs, not by its verb: an amendment or replacement still reads, because
its successor copies unassigned members and the unchanged-milestone rule
compares stored values, and a Bitemporal termination still reads, because the
rectangle it splits reopens with the old values.

Before this, every deferred Transaction-Time-Only write read and executed
alone, so N target amendments cost 3N statements and N terminations 2N, while
the same batch on a Bitemporal Entity cost three. Nothing beyond the span rule
depended on that serialization: Write Group formation already admits grouped
effects of distinct objects, and `m-sql` *Grouped effects* already gives the
Transaction-Time-Only grouped close and guard. Failures keep their
classification and only move. A stale or missing start is the same
non-retried precondition, raised by the close's affected-row enforcement rather
than before any statement. Cardinality Corruption cannot arise on the unread
path, since the `(key, out_z)` primary key refuses two current rows. A stated
start at or after the attempt's instant that no row holds becomes a Temporal
Conflict, whose retry takes a later instant and then fails its precondition:
one extra attempt in a rare case. Because the unread close is checked at
planning, a caught Temporal Conflict no longer dooms its attempt; the
termination stays buffered and the next flush refuses it again.

Spans admitting only target writes were rejected for putting a write's origin
into acquisition. A separate Transaction-Time-Only acquisition rule, or no
bound on its parts, was rejected: the first duplicates packing, readiness, and
bound logic, and the second breaks the coupling by which a Write Group holds a
full span's ready writes. Reading several keys as an `or`-chain of equalities
was rejected because its text grows with the key count, defeating statement
preparation, and needs the multi-term planner to accept terms with no
Valid-Time axis. Keeping the termination's read, batched, was rejected because
it permanently doubles the cheapest correct form's statements, including for
the common single termination. Dropping the close-follows-start check and
letting the `in_z < out_z` constraint refuse was rejected because it would
misclassify a conflict a fresh instant resolves as a non-retried constraint
violation. Recognizing that constraint's violation as a Temporal Conflict, as
[ADR 0079](0079-postgresql-storage-refuses-overlapping-history-and-its-conflicts-are-retried.md)
recognizes the exclusion, was rejected for adding a recognition mechanism to
save one retry in a rare case. The span, group, and per-read bounds stay each
implementation's
([ADR 0086](0086-write-plans-are-meanings-and-write-groups-promise-outcomes.md)).

## Prior art

Reladomo buffers audit-only updates and terminations per object and combines
operations of distinct objects at flush into multi-row or batched updates and
batched inserts, enrolling an object by a per-object read unless optimistic
participation finds it cached
([research notes](../research/reladomo/09-transactions-locking.md),
[blind-write prevention](../research/reladomo/29-blind-write-prevention-for-deletes-and-terminates.md)).
That is evidence that flush-time grouping of such writes is established
practice, not the source of these semantics.
