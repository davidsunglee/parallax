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

## Prior art

Reladomo's generated `insert()` sets an unset generated key into the object the
caller holds before inserting it, and pushes that key into dependent children
([research notes](../research/reladomo/02-object-metamodel.md)). Parallax
publishes immutable values, so it answers a value rather than mutating one, and
leaves a child to be built from the key its parent's insert answered.
