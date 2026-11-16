# An insert answers an immutable keyed value

Every insert answers, at the call, the immutable keyed value its insertion was
stated through, while the row stays buffered until a flush (`m-unit-work`
*Insertion authority*). Python's Typed verb is `insert[E](instance: E) -> E`; for
a supplied key the answer is `instance` itself, carrying the insertion's
authority exactly as before. A Wire insert already answered the frozen node it
opened, and is unchanged. An answered value is final at the call: no flush
writes back into it.

Before this, Typed `insert` answered `None`, and only Wire handed its caller a
carrier. The two interfaces therefore differed in shape at exactly the verb that
opens a row, and an insert whose key the framework chooses would have had no way
to tell its caller which key it chose. One result shape for every insert is what
lets a later key-allocating insert answer a new keyed value without changing the
verb's type, and lets keyed code behave the same whichever key strategy an
Entity declares.

Writing flush-time values back into the answered value was rejected: a value a
caller already holds, compares, or hands to another thread would change under it,
and an edit taken before the flush would disagree with one taken after it. A
result handle, promise, or finalization method resolved at flush was rejected for
the same mutability, and because it adds a second lifecycle beside the
attempt's. Re-reading each inserted row automatically was rejected because it
spends a round trip per insert and defeats grouped inserts, while the ordinary
read a caller already writes gives the same answer only where it is needed.
Manufacturing Read Evidence for an answered value was rejected because no read
produced it: its writes stay licensed by the insertion's authority alone, which
every attempt boundary ends.

## Native pooled allocation

A key a model generates comes from a native database sequence the binding places,
in blocks: the sequence advances by `batchSize × incrementSize` per reservation,
the root hands the block's keys out locally, and a key is allocated at the insert
call, after the row's preparation and before the row names its object
(`m-pk-gen` *Native key sequences*). Presence decides it — a key left unset is
allocated, a set key, zero included, is used as given — so keyed code behaves
the same whichever strategy an Entity declares, and a typed insert that allocated
answers a new value published from the opened row rather than the draft it took.

Allocating at flush was rejected: the caller would hold no key until a flush, a
parent's key could not build its child in the same attempt, and the answered
value would need the write-back this decision already refused. `max(col)+1` and
the simulated registry table were rejected as the generated strategy because
both serialize concurrent writers on stored data and the registry's advance
runs inside the application's transaction; a database identity column read back
through `RETURNING` was rejected because it defers the key to flush and makes
every insert of a batch a round trip. Deciding omission by a sentinel such as
`None` or `0` was rejected because zero is a valid supplied key and `None` is
refused by the key's own type.

A reservation is one statement on the root's own writer connection, committed
outside the application transaction under the deployment's login, so it neither
elevates the application's authority nor is undone by its rollback, and a
transaction holding the root's only application connection can still reserve.
That statement also reads back the live definition and checks it on every
reservation, rather than once per root behind a retained "checked" flag: a
sequence altered under a root that should have been drained is caught at that
root's next reservation, at the cost of a catalog lookup inside a statement that
runs once per block. Reservation state is keyed by physical sequence and
allocation settings, never by allocator name or edition, so tenants binding one
allocator name to different sequences share nothing and a publication that moves
nothing keeps the root's block.

## Prior art

Reladomo's generated `insert()` sets an unset generated key into the object the
caller holds before inserting it, and pushes that key into dependent children
([research notes](../research/reladomo/02-object-metamodel.md)). Parallax
publishes immutable values, so it answers a value rather than mutating one, and
leaves a child to be built from the key its parent's insert answered. Reladomo's
simulated sequence also reserves blocks in a transaction of its own, and
Hibernate's pooled-lo optimizer reads a native sequence's value as the low end
of a block; Parallax keeps both shapes on a native sequence, without Reladomo's
first-use `max(pk)` scan of the sharing tables.
