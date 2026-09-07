# The managed slice drops detach and merge-back

Parallax will not implement the detached-object lifecycle or its merge-back
protocol. The managed slice remains a transaction-scoped identity map together
with query-backed lists: managed objects are interned while their unit of work is
open, mutation is buffered there, and the identity map is discarded when that
unit of work ends. Core makes no portable state or persistence promise for an
object retained beyond that boundary.

This decision supersedes the detach-specific parts of ADR 0019: the proposed
conversation pattern based on detach, offline edit, and merge-back; the
transition of held objects into a detached state when their owning scope ends;
and the claim that a deferred relationship load outside that scope raises a
detach-specific error. ADR 0019 remains the decision that snapshot and managed
object lifecycles are separate slices and that the managed identity scope is the
unit of work rather than a session.

The `m-detach` module, its compatibility cases, its five-state observation
vocabulary, its deliberate-copy and merge-back verbs, and its relationship-load
error are removed together. Optimistic locking continues to protect ordinary
read-then-write flows, and the managed slice continues to claim identity-map
interning and query-backed list behavior without a cross-transaction object
reassociation protocol.
